from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from seeing_api.auth import SESSION_COOKIE, now, token_id, verify_password
from seeing_api.db import get_session_factory
from seeing_api.main import create_app
from seeing_db import User, UserRole, UserSession

PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def no_users() -> Iterator[None]:
    def wipe() -> None:
        with get_session_factory()() as s:
            s.execute(delete(User))
            s.commit()

    wipe()
    yield
    wipe()


@pytest.fixture
def client() -> TestClient:
    # https: the session cookie is Secure by default and would not be sent back over http.
    return TestClient(create_app(static_dir="/nonexistent"), base_url="https://testserver")


def signup(client: TestClient, email: str = "Ada@Example.org", password: str = PASSWORD, **extra):
    return client.post("/api/auth/signup", json={"email": email, "password": password, **extra})


def test_signup_logs_in_and_me_returns_the_user(client):
    r = signup(client, display_name="  Ada  ")
    assert r.status_code == 201
    assert r.json() == {"id": r.json()["id"], "email": "ada@example.org", "display_name": "Ada", "role": "user"}
    assert r.headers["cache-control"] == "no-store"
    me = client.get("/api/me")
    assert me.headers["cache-control"] == "no-store"
    assert me.json()["user"]["email"] == "ada@example.org"


def test_cookie_flags_and_stored_session_is_a_hash(client):
    r = signup(client)
    cookie = r.headers["set-cookie"].lower()
    assert f"{SESSION_COOKIE}=" in cookie
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" in cookie and "path=/" in cookie
    token = client.cookies[SESSION_COOKIE]
    with get_session_factory()() as s:
        ids = list(s.scalars(select(UserSession.id)))
        user = s.scalar(select(User))
    assert ids == [token_id(token)] and token not in ids
    assert user.password_hash.startswith("$argon2id$") and PASSWORD not in user.password_hash
    assert verify_password(user.password_hash, PASSWORD)


def test_cookie_not_secure_when_disabled(client, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "false")
    assert "secure" not in signup(client).headers["set-cookie"].lower()


def test_signup_rejects_duplicates_short_passwords_and_bad_emails(client):
    assert signup(client).status_code == 201
    assert signup(client, email="ADA@example.org").status_code == 409
    assert signup(client, email="bob@example.org", password="short").status_code == 422
    assert signup(client, email="not-an-email").status_code == 422


def test_signup_can_be_disabled(client, monkeypatch):
    monkeypatch.setenv("SIGNUP_ENABLED", "false")
    assert signup(client).status_code == 403


def test_login_failures_look_the_same(client):
    signup(client)
    client.cookies.clear()
    wrong = client.post("/api/auth/login", json={"email": "ada@example.org", "password": "wrong password!"})
    unknown = client.post("/api/auth/login", json={"email": "nobody@example.org", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert SESSION_COOKIE not in client.cookies


def test_login_logout_cycle(client):
    signup(client)
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"email": " ADA@example.org ", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["email"] == "ada@example.org"
    assert client.get("/api/me").json()["user"] is not None
    token = client.cookies[SESSION_COOKIE]
    assert client.post("/api/auth/logout", json={}).status_code == 204
    assert client.get("/api/me").json()["user"] is None
    with get_session_factory()() as s:
        # Only this login's session is removed; the sign-up session (cookie cleared above) is untouched.
        assert s.get(UserSession, token_id(token)) is None
        assert len(list(s.scalars(select(UserSession)))) == 1


def test_old_token_is_useless_after_logout(client):
    signup(client)
    token = client.cookies[SESSION_COOKIE]
    client.post("/api/auth/logout", json={})
    client.cookies.set(SESSION_COOKIE, token, domain="testserver")
    assert client.get("/api/me").json()["user"] is None


def test_expired_and_inactive_sessions_are_ignored(client):
    signup(client)
    with get_session_factory()() as s:
        s.scalar(select(UserSession)).expires_at = now() - timedelta(seconds=1)
        s.commit()
    assert client.get("/api/me").json()["user"] is None

    client.post("/api/auth/login", json={"email": "ada@example.org", "password": PASSWORD})
    with get_session_factory()() as s:
        s.scalar(select(User)).is_active = False
        s.commit()
    assert client.get("/api/me").json()["user"] is None
    assert client.post("/api/auth/login", json={"email": "ada@example.org", "password": PASSWORD}).status_code == 401


def test_session_slides_after_half_life(client, monkeypatch):
    signup(client)
    with get_session_factory()() as s:
        s.scalar(select(UserSession)).expires_at = now() + timedelta(days=1)
        s.commit()
    me = client.get("/api/me")
    assert me.json()["user"] is not None and SESSION_COOKIE in me.headers.get("set-cookie", "")
    with get_session_factory()() as s:
        assert s.scalar(select(UserSession)).expires_at > now() + timedelta(days=29)


def test_auth_posts_require_json(client):
    r = client.post("/api/auth/login", content="email=a@b.org&password=x", headers={"content-type": "text/plain"})
    assert r.status_code == 415
    assert client.post("/api/auth/logout").status_code == 415


def test_role_comes_from_the_database(client):
    signup(client)
    with get_session_factory()() as s:
        s.scalar(select(User)).role = UserRole.admin
        s.commit()
    assert client.get("/api/me").json()["user"]["role"] == "admin"
