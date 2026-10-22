from collections.abc import Iterator

import pytest
from sqlalchemy import delete, select

from seeing_api.auth import verify_password
from seeing_api.create_user import main
from seeing_api.db import get_session_factory
from seeing_db import User, UserRole, UserSession

PASSWORD = "an admin password"


@pytest.fixture(autouse=True)
def no_users(monkeypatch) -> Iterator[None]:
    monkeypatch.setenv("SEEING_USER_PASSWORD", PASSWORD)

    def wipe() -> None:
        with get_session_factory()() as s:
            s.execute(delete(User))
            s.commit()

    wipe()
    yield
    wipe()


def get_user() -> User:
    with get_session_factory()() as s:
        return s.scalar(select(User))


def test_creates_an_admin():
    main(["--email", "Admin@Example.org", "--role", "admin", "--display-name", "Admin"])
    user = get_user()
    assert (user.email, user.role, user.display_name) == ("admin@example.org", UserRole.admin, "Admin")
    assert verify_password(user.password_hash, PASSWORD)


def test_refuses_duplicates_unless_update(monkeypatch):
    main(["--email", "team@example.org", "--role", "team"])
    with pytest.raises(SystemExit):
        main(["--email", "team@example.org"])
    monkeypatch.setenv("SEEING_USER_PASSWORD", "a new team password")
    main(["--email", "team@example.org", "--role", "admin", "--update"])
    user = get_user()
    assert user.role == UserRole.admin and verify_password(user.password_hash, "a new team password")


def test_rejects_short_passwords_and_unknown_updates(monkeypatch):
    with pytest.raises(SystemExit):
        main(["--email", "x@example.org", "--update"])
    monkeypatch.setenv("SEEING_USER_PASSWORD", "short")
    with pytest.raises(SystemExit):
        main(["--email", "x@example.org"])
    assert get_user() is None


def test_update_keeps_role_unless_given_and_ends_sessions():
    main(["--email", "boss@example.org", "--role", "admin"])
    with get_session_factory()() as s:
        user = s.scalar(select(User))
        s.add(UserSession(id="0" * 64, user_id=user.id, expires_at=user.created_at.replace(year=2100)))
        s.commit()
    main(["--email", "boss@example.org", "--update"])
    assert get_user().role == UserRole.admin
    with get_session_factory()() as s:
        assert s.scalar(select(UserSession)) is None
