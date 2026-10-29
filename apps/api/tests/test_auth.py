from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from seeing_api import auth
from seeing_api.auth import SESSION_COOKIE, now, token_id, verify_password
from seeing_api.db import get_session_factory
from seeing_api.main import create_app
from seeing_api.passwords import password_problem
from seeing_db import EmailToken, User, UserRole, UserSession

PASSWORD = "Correct horse battery 7"


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


def test_hidden_sites_only_for_the_admin(client):
    signup(client)
    slugs = {s["slug"] for s in client.get("/api/sites").json()}
    assert "copernic-gap" not in slugs and "verclause" not in slugs
    with get_session_factory()() as s:
        s.scalar(select(User)).role = UserRole.admin
        s.commit()
    sites = {s["slug"]: s for s in client.get("/api/sites").json()}
    assert sites["copernic-gap"]["visibility"] == "hidden" and sites["verclause"]["name"] == "Drôme"


def test_validation_errors_do_not_echo_the_password(client):
    r = signup(client, email="bob@example.org", password="secret1")
    assert r.status_code == 422 and "secret1" not in r.text
    r = client.post("/api/auth/login", json={"email": "not-an-email", "password": "hunter2hunter2"})
    assert r.status_code == 422 and "hunter2hunter2" not in r.text and "not-an-email" not in r.text


# ---- password rules, rate limits, e-mail confirmation ---------------------------------------------


@pytest.mark.parametrize(
    ("password", "code"),
    [
        ("Short1!", "password_too_short"),
        ("only lower case words", "password_too_simple"),
        ("Azerty123456!", "password_too_common"),
        ("P@ssw0rd2026", "password_too_common"),
        ("Ada-is-my-name-42", "password_contains_email"),
    ],
)
def test_signup_password_rules(client, password, code):
    r = signup(client, password=password)
    assert r.status_code == 422 and r.json()["detail"] == code and password not in r.text


def test_password_problem_accepts_good_passwords():
    assert password_problem("Correct horse battery 7", "ada@example.org") is None
    assert password_problem("Tr0ub4dor&3xyz") is None


def test_failed_logins_are_limited_per_email(client):
    signup(client)
    client.cookies.clear()
    bad = {"email": "ada@example.org", "password": "wrong password!"}
    assert [client.post("/api/auth/login", json=bad).status_code for _ in range(5)] == [401] * 5
    r = client.post("/api/auth/login", json={"email": "ada@example.org", "password": PASSWORD})
    assert r.status_code == 429 and "retry-after" in r.headers
    # another address from the same client is not blocked
    assert client.post("/api/auth/login", json={"email": "bob@example.org", "password": PASSWORD}).status_code == 401


def test_successful_login_clears_the_failures(client):
    signup(client)
    client.cookies.clear()
    bad = {"email": "ada@example.org", "password": "wrong password!"}
    for _ in range(4):
        client.post("/api/auth/login", json=bad)
    assert client.post("/api/auth/login", json={"email": "ada@example.org", "password": PASSWORD}).status_code == 200
    assert client.post("/api/auth/login", json=bad).status_code == 401


def test_signups_are_limited_per_ip(client):
    codes = [signup(client, email=f"u{k}@example.org").status_code for k in range(6)]
    assert codes == [201] * 5 + [429]


def test_client_ip_is_the_last_forwarded_entry(client):
    for k in range(5):
        signup(client, email=f"v{k}@example.org")
    # the client can prepend a fake address, the front end's entry is the last one
    r = client.post(
        "/api/auth/signup",
        json={"email": "w@example.org", "password": PASSWORD},
        headers={"x-forwarded-for": "1.2.3.4, 203.0.113.9"},
    )
    assert r.status_code == 201


@pytest.fixture
def mails(monkeypatch) -> list[tuple[str, str]]:
    """E-mail confirmation on, e-mails captured instead of sent: (recipient, link)."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setenv("EMAIL_VERIFICATION", "true")
    monkeypatch.setattr(auth, "send_mail", lambda to, subject, text, link, label: sent.append((to, link)) or True)
    return sent


def test_signup_with_confirmation_sends_a_link_and_no_session(client, mails):
    r = signup(client)
    assert r.status_code == 202 and r.json() == {"email": "ada@example.org", "pending": True, "sent": True}
    assert SESSION_COOKIE not in client.cookies
    assert len(mails) == 1 and mails[0][0] == "ada@example.org" and "/compte?verif=" in mails[0][1]
    with get_session_factory()() as s:
        token = mails[0][1].split("verif=")[1]
        assert s.scalar(select(EmailToken.id)) == token_id(token)  # only the hash is stored


def test_login_before_confirmation_is_refused_after_the_password_check(client, mails):
    signup(client)
    wrong = client.post("/api/auth/login", json={"email": "ada@example.org", "password": "wrong password!"})
    assert wrong.status_code == 401
    r = client.post("/api/auth/login", json={"email": "ada@example.org", "password": PASSWORD})
    assert r.status_code == 403 and r.json()["detail"] == "email_not_verified"


def test_the_link_confirms_logs_in_and_works_once(client, mails):
    signup(client)
    token = mails[0][1].split("verif=")[1]
    r = client.post("/api/auth/verify", json={"token": token})
    assert r.status_code == 200 and r.json()["email"] == "ada@example.org"
    assert client.get("/api/me").json()["user"]["email"] == "ada@example.org"
    assert client.post("/api/auth/verify", json={"token": token}).status_code == 400
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"email": "ada@example.org", "password": PASSWORD}).status_code == 200


def test_expired_link_is_refused(client, mails):
    signup(client)
    with get_session_factory()() as s:
        s.scalar(select(EmailToken)).expires_at = now() - timedelta(seconds=1)
        s.commit()
    token = mails[0][1].split("verif=")[1]
    assert client.post("/api/auth/verify", json={"token": token}).status_code == 400


def test_resend_tells_nothing_and_is_limited(client, mails):
    signup(client)
    assert client.post("/api/auth/resend", json={"email": "nobody@example.org"}).status_code == 204
    assert len(mails) == 1
    for _ in range(4):
        assert client.post("/api/auth/resend", json={"email": "ada@example.org"}).status_code == 204
    assert len(mails) == 3  # at most 3 e-mails per hour for one address (the sign-up one included)
    # the newest link is the only valid one
    assert client.post("/api/auth/verify", json={"token": mails[0][1].split("verif=")[1]}).status_code == 400
    assert client.post("/api/auth/verify", json={"token": mails[-1][1].split("verif=")[1]}).status_code == 200


def test_confirmation_off_without_a_mail_key(client, monkeypatch):
    monkeypatch.delenv("EMAIL_VERIFICATION", raising=False)
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    assert signup(client).status_code == 201 and SESSION_COOKIE in client.cookies
