"""App accounts: Argon2id password hashing, server-side sessions in an httpOnly cookie, and the
/api/auth endpoints (sign-up, login, logout).

The cookie holds a random token; the database stores only its SHA-256 (`user_sessions.id`), so a
database leak cannot be replayed as a session. CSRF: the cookie is SameSite=Lax and every auth POST
must be `application/json`, which a cross-site form cannot send without a CORS preflight (no CORS is
configured).

Settings (environment variables, read at request time):
- SESSION_DAYS: session lifetime in days (default 30); sessions slide when used past half-life.
- COOKIE_SECURE: "false" to allow the cookie over plain HTTP in local dev (default true).
- SIGNUP_ENABLED: "false" to refuse new sign-ups (default true).
"""

import hashlib
import os
import secrets
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeing_api.db import get_session_factory
from seeing_db import User, UserRole, UserSession

SESSION_COOKIE = "seeing_session"
MIN_PASSWORD_LENGTH = 10
#: Upper bound so a huge password cannot be used to burn CPU in Argon2.
MAX_PASSWORD_LENGTH = 1024
NO_STORE = "no-store"
LOGIN_FAILED = "Invalid e-mail or password"

_hasher = PasswordHasher()


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() not in {"0", "false", "no", "off"}


def session_lifetime() -> timedelta:
    return timedelta(days=float(os.environ.get("SESSION_DAYS", "30")))


def cookie_secure() -> bool:
    return _env_flag("COOKIE_SECURE", True)


def signup_enabled() -> bool:
    return _env_flag("SIGNUP_ENABLED", True)


# ---- passwords and tokens ------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Argon2id hash (salt and parameters are encoded in the returned string)."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@cache
def _dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))


def normalize_email(email: str) -> str:
    return email.strip().lower()


def token_id(token: str) -> str:
    """Database key of a session token: its SHA-256 hex digest."""
    return hashlib.sha256(token.encode()).hexdigest()


def now() -> datetime:
    return datetime.now(UTC)


# ---- database session for writes ----------------------------------------------------------------


def get_write_session() -> Iterator[Session]:
    """FastAPI dependency: a session committed when the request handler succeeds."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


WriteSessionDep = Annotated[Session, Depends(get_write_session)]


# ---- sessions and cookies -----------------------------------------------------------------------


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(session_lifetime().total_seconds()),
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=cookie_secure(), samesite="lax")


def start_session(db: Session, user: User, response: Response) -> None:
    """Create a session row for `user`, drop their expired ones, and set the cookie."""
    t = now()
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at <= t))
    token = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            id=token_id(token), user_id=user.id, created_at=t, last_seen_at=t, expires_at=t + session_lifetime()
        )
    )
    set_session_cookie(response, token)


def current_user(request: Request, response: Response, db: WriteSessionDep) -> User | None:
    """FastAPI dependency: the logged-in user, or None. Extends the session when past half-life."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    row = db.get(UserSession, token_id(token))
    t = now()
    if row is None or row.expires_at <= t or not row.user.is_active:
        if row is not None:
            db.delete(row)
        clear_session_cookie(response)
        return None
    lifetime = session_lifetime()
    if row.expires_at - t < lifetime / 2:
        row.expires_at = t + lifetime
        row.last_seen_at = t
        set_session_cookie(response, token)
    return row.user


CurrentUser = Annotated[User | None, Depends(current_user)]


def require_role(*roles: UserRole) -> Callable[[User | None], User]:
    """Dependency factory for endpoints that need a logged-in user (with one of `roles` if given)."""

    def dependency(user: CurrentUser) -> User:
        if user is None:
            raise HTTPException(401, "Not logged in")
        if roles and user.role not in roles:
            raise HTTPException(403, "Not allowed for this account")
        return user

    return dependency


def require_json(request: Request) -> None:
    """CSRF guard for cookie-authenticated POSTs: only application/json bodies are accepted."""
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Expected application/json")


# ---- schemas and endpoints ----------------------------------------------------------------------


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str | None
    role: UserRole


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, display_name=user.display_name, role=user.role)


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    display_name: str | None = Field(default=None, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


router = APIRouter(prefix="/api/auth", dependencies=[Depends(require_json)])


@router.post("/signup", response_model=UserOut, status_code=201)
def signup(body: SignupIn, response: Response, db: WriteSessionDep) -> UserOut:
    response.headers["Cache-Control"] = NO_STORE
    if not signup_enabled():
        raise HTTPException(403, "Sign-up is disabled")
    name = (body.display_name or "").strip() or None
    user = User(email=normalize_email(body.email), password_hash=hash_password(body.password), display_name=name)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account already exists for this e-mail") from None
    user.last_login_at = now()
    start_session(db, user, response)
    return user_out(user)


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response, db: WriteSessionDep) -> UserOut:
    response.headers["Cache-Control"] = NO_STORE
    user = db.scalar(select(User).where(User.email == normalize_email(body.email)))
    if user is None:
        verify_password(_dummy_hash(), body.password)  # same work as a real check: no e-mail enumeration by timing
        raise HTTPException(401, LOGIN_FAILED)
    if not verify_password(user.password_hash, body.password) or not user.is_active:
        raise HTTPException(401, LOGIN_FAILED)
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    user.last_login_at = now()
    start_session(db, user, response)
    return user_out(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: WriteSessionDep) -> None:
    response.headers["Cache-Control"] = NO_STORE
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(UserSession).where(UserSession.id == token_id(token)))
    clear_session_cookie(response)
