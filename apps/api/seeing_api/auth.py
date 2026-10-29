"""App accounts: Argon2id password hashing, server-side sessions in an httpOnly cookie, and the
/api/auth endpoints (sign-up, login, logout, e-mail confirmation).

New passwords follow the rules of `seeing_api.passwords`. Rate limits (table auth_events, by e-mail
and client IP): failed logins, sign-ups and confirmation e-mails; past the limit the API answers 429.

E-mail confirmation (when EMAIL_VERIFICATION is on): sign-up creates the account without a session
and e-mails a single-use link (`/compte?verif=<token>`, valid TOKEN_HOURS); opening it confirms the
address and logs in. Until then, login answers 403 "email_not_verified" (only after a correct
password, so it does not tell which e-mails have an account).

The cookie holds a random token; the database stores only its SHA-256 (`user_sessions.id`), so a
database leak cannot be replayed as a session. CSRF: the cookie is SameSite=Lax and every auth POST
must be `application/json`, which a cross-site form cannot send without a CORS preflight (no CORS is
configured).

Settings (environment variables, read at request time):
- SESSION_DAYS: session lifetime in days (default 30); sessions slide when used past half-life.
- COOKIE_SECURE: "false" to allow the cookie over plain HTTP in local dev (default true).
- SIGNUP_ENABLED: "false" to refuse new sign-ups (default true).
- EMAIL_VERIFICATION: "true" / "false" to require the e-mail confirmation (default: on when
  BREVO_API_KEY is set, see `seeing_api.mail`).
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
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeing_api.db import get_session_factory
from seeing_api.mail import public_url, send_mail
from seeing_api.passwords import MIN_LENGTH, password_problem
from seeing_db import AuthEvent, EmailToken, User, UserRole, UserSession

SESSION_COOKIE = "seeing_session"
MIN_PASSWORD_LENGTH = MIN_LENGTH
#: Upper bound so a huge password cannot be used to burn CPU in Argon2.
MAX_PASSWORD_LENGTH = 1024
NO_STORE = "no-store"
LOGIN_FAILED = "Invalid e-mail or password"
TOO_MANY = "Too many attempts, try again later"
#: Rate limits: (maximum count, window). Failed logins per e-mail and per IP, sign-ups per IP,
#: confirmation e-mails per address and requests for one per IP.
LOGIN_FAILS_PER_EMAIL = (5, timedelta(minutes=15))
LOGIN_FAILS_PER_IP = (30, timedelta(minutes=15))
SIGNUPS_PER_IP = (5, timedelta(hours=1))
MAILS_PER_EMAIL = (3, timedelta(hours=1))
MAIL_REQUESTS_PER_IP = (10, timedelta(hours=1))
TOKEN_HOURS = 48

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


def email_verification() -> bool:
    return _env_flag("EMAIL_VERIFICATION", bool(os.environ.get("BREVO_API_KEY")))


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


# ---- rate limits ---------------------------------------------------------------------------------


def client_ip(request: Request) -> str | None:
    """Client address: the last X-Forwarded-For entry, the one added by Google's front end (earlier
    entries can be written by the client), else the socket peer."""
    fwd = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if fwd:
        return fwd[-1][:64]
    return request.client.host if request.client else None


def record_event(kind: str, email: str | None, ip: str | None) -> None:
    """Store an auth event in its own transaction (kept even when the request then fails), and drop
    the events older than a day."""
    with get_session_factory()() as s:
        s.add(AuthEvent(kind=kind, email=email, ip=ip, at=now()))
        s.execute(delete(AuthEvent).where(AuthEvent.at < now() - timedelta(days=1)))
        s.commit()


def over_limit(
    db: Session, kind: str, limit: tuple[int, timedelta], email: str | None = None, ip: str | None = None
) -> bool:
    if email is None and ip is None:
        return False
    q = select(func.count()).select_from(AuthEvent).where(AuthEvent.kind == kind, AuthEvent.at > now() - limit[1])
    q = q.where(AuthEvent.email == email) if email is not None else q.where(AuthEvent.ip == ip)
    return (db.scalar(q) or 0) >= limit[0]


def too_many(limit: tuple[int, timedelta]) -> HTTPException:
    return HTTPException(429, TOO_MANY, headers={"Retry-After": str(int(limit[1].total_seconds()))})


# ---- e-mail confirmation ------------------------------------------------------------------------


def send_verification(db: Session, user: User) -> bool:
    """New single-use confirmation link for `user` (older ones are dropped), sent by e-mail."""
    db.execute(delete(EmailToken).where(EmailToken.user_id == user.id, EmailToken.purpose == "verify"))
    token = secrets.token_urlsafe(32)
    db.add(
        EmailToken(id=token_id(token), user_id=user.id, purpose="verify", expires_at=now() + timedelta(hours=TOKEN_HOURS))
    )
    db.flush()
    link = f"{public_url()}/compte?verif={token}"
    text = (
        "Bonjour,\n\n"
        "Pour activer ton compte Seeing AROME, confirme ton adresse e-mail en ouvrant ce lien "
        f"(valable {TOKEN_HOURS} heures) :\n\n{link}\n\n"
        "Si tu n'as pas créé de compte, ignore ce message : rien ne sera activé."
    )
    return send_mail(user.email, "Confirme ton adresse e-mail · Seeing AROME", text, link, "Confirmer mon adresse")


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
    # length and the other rules: checked by password_problem() for a precise error code
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    display_name: str | None = Field(default=None, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class PendingOut(BaseModel):
    """Sign-up waiting for the e-mail confirmation: no session yet."""

    email: str
    pending: bool = True
    #: False when the e-mail could not be sent (the page offers to send it again).
    sent: bool


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class EmailIn(BaseModel):
    email: EmailStr


router = APIRouter(prefix="/api/auth", dependencies=[Depends(require_json)])


@router.post("/signup", response_model=UserOut | PendingOut, status_code=201)
def signup(body: SignupIn, request: Request, response: Response, db: WriteSessionDep) -> UserOut | PendingOut:
    response.headers["Cache-Control"] = NO_STORE
    if not signup_enabled():
        raise HTTPException(403, "Sign-up is disabled")
    email = normalize_email(body.email)
    problem = password_problem(body.password, email)
    if problem:
        raise HTTPException(422, f"password_{problem}")
    ip = client_ip(request)
    if over_limit(db, "signup", SIGNUPS_PER_IP, ip=ip):
        raise too_many(SIGNUPS_PER_IP)
    record_event("signup", None, ip)
    name = (body.display_name or "").strip() or None
    user = User(email=email, password_hash=hash_password(body.password), display_name=name)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account already exists for this e-mail") from None
    if email_verification():
        record_event("mail", email, ip)
        response.status_code = 202
        return PendingOut(email=email, sent=send_verification(db, user))
    user.last_login_at = now()
    start_session(db, user, response)
    return user_out(user)


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: WriteSessionDep) -> UserOut:
    response.headers["Cache-Control"] = NO_STORE
    email, ip = normalize_email(body.email), client_ip(request)
    if over_limit(db, "login_fail", LOGIN_FAILS_PER_EMAIL, email=email):
        raise too_many(LOGIN_FAILS_PER_EMAIL)
    if over_limit(db, "login_fail", LOGIN_FAILS_PER_IP, ip=ip):
        raise too_many(LOGIN_FAILS_PER_IP)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        verify_password(_dummy_hash(), body.password)  # same work as a real check: no e-mail enumeration by timing
        record_event("login_fail", email, ip)
        raise HTTPException(401, LOGIN_FAILED)
    if not verify_password(user.password_hash, body.password) or not user.is_active:
        record_event("login_fail", email, ip)
        raise HTTPException(401, LOGIN_FAILED)
    if email_verification() and user.email_verified_at is None:
        raise HTTPException(403, "email_not_verified")
    db.execute(delete(AuthEvent).where(AuthEvent.kind == "login_fail", AuthEvent.email == email))
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


@router.post("/verify", response_model=UserOut)
def verify(body: TokenIn, response: Response, db: WriteSessionDep) -> UserOut:
    """Open the e-mailed link: confirm the address and log in. The link works once."""
    response.headers["Cache-Control"] = NO_STORE
    row = db.get(EmailToken, token_id(body.token))
    if row is None or row.purpose != "verify" or row.expires_at <= now():
        raise HTTPException(400, "invalid_or_expired")
    user = db.get(User, row.user_id)
    db.execute(delete(EmailToken).where(EmailToken.user_id == row.user_id, EmailToken.purpose == "verify"))
    if user is None or not user.is_active:
        raise HTTPException(400, "invalid_or_expired")
    t = now()
    user.email_verified_at = user.email_verified_at or t
    user.last_login_at = t
    start_session(db, user, response)
    return user_out(user)


@router.post("/resend", status_code=204)
def resend(body: EmailIn, request: Request, response: Response, db: WriteSessionDep) -> None:
    """Send the confirmation e-mail again. Always 204 (whether the account exists or is already
    confirmed is not told); at most MAILS_PER_EMAIL e-mails per address."""
    response.headers["Cache-Control"] = NO_STORE
    email, ip = normalize_email(body.email), client_ip(request)
    if over_limit(db, "mail_request", MAIL_REQUESTS_PER_IP, ip=ip):
        raise too_many(MAIL_REQUESTS_PER_IP)
    record_event("mail_request", None, ip)
    if not email_verification() or over_limit(db, "mail", MAILS_PER_EMAIL, email=email):
        return
    user = db.scalar(select(User).where(User.email == email))
    if user is None or user.email_verified_at is not None or not user.is_active:
        return
    record_event("mail", email, ip)
    send_verification(db, user)
