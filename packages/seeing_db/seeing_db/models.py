import enum
from datetime import datetime

from sqlalchemy import (
    REAL,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RunStatus(enum.StrEnum):
    running = "running"
    success = "success"
    failed = "failed"


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    altitude_m: Mapped[float | None] = mapped_column(Float)
    # Empirical coefficients of the three Cn2 models (convective, TKE, wind shear).
    k_tke_conv: Mapped[float] = mapped_column(Float, default=0.1)  # K_conv = 0.1 everywhere
    #: Calibration settings of the place {pics, courtes, top, out: [nights left out]} (Calibrer), NULL = defaults.
    calib: Mapped[dict | None] = mapped_column(JSONB)
    k_tke: Mapped[float] = mapped_column(Float, default=3.0)
    k_cis: Mapped[float] = mapped_column(Float, default=30.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # public (observatories), shared (by a team or a user with the community), hidden (computed, not
    # offered) or private (a user's own place).
    visibility: Mapped[str] = mapped_column(String(16), default="public", server_default="public")
    # Account owning a personal place (NULL for the curated sites).
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # AROME orography of the 5 x 5 grid cells around the site, full resolution (written by the batch):
    # {"lat0", "lon0": centre of the site's cell, "step": degrees, "alt": rows north to south, metres}.
    cells: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), unique=True)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status", values_callable=lambda e: [m.value for m in e])
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)

    forecasts: Mapped[list["Forecast"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    cn2_profiles: Mapped[list["Cn2Profile"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    map_frames: Mapped[list["MapFrame"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class MapFrame(Base):
    """Seeing map of one lead hour over the (subsampled) AROME grid: row r / column c is at
    (lat0 + r * dlat, lon0 + c * dlon); `data` = zlib(uint8 log-scale codes), seeing_core.grid."""

    __tablename__ = "map_frames"
    __table_args__ = (UniqueConstraint("run_id", "lead_hour"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id", ondelete="CASCADE"), index=True)
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lead_hour: Mapped[int] = mapped_column(Integer)
    ny: Mapped[int] = mapped_column(Integer)
    nx: Mapped[int] = mapped_column(Integer)
    lat0: Mapped[float] = mapped_column(Float)
    lon0: Mapped[float] = mapped_column(Float)
    dlat: Mapped[float] = mapped_column(Float)
    dlon: Mapped[float] = mapped_column(Float)
    k_tke: Mapped[float] = mapped_column(Float)
    k_cis: Mapped[float] = mapped_column(Float)
    k_conv: Mapped[float] = mapped_column(Float)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    # zlib(3 uint8 planes): share of the low (boundary-layer) turbulence, heights of the low and high
    # parts (seeing_core.grid.encode_split), for the fisheye; then, since the cloud option, 3 planes of
    # low / medium / high cloud cover in %. NULL for older frames.
    extra: Mapped[bytes | None] = mapped_column(LargeBinary)

    run: Mapped[ModelRun] = relationship(back_populates="map_frames")


class Forecast(Base):
    __tablename__ = "forecasts"
    __table_args__ = (UniqueConstraint("run_id", "site_id", "lead_hour"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id", ondelete="CASCADE"), index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lead_hour: Mapped[int] = mapped_column(Integer)
    seeing_arcsec: Mapped[float | None] = mapped_column(Float)
    r0_m: Mapped[float | None] = mapped_column(Float)
    integral_cn2: Mapped[float | None] = mapped_column(Float)
    h_coulim_m: Mapped[float | None] = mapped_column(Float)
    model_altitude_m: Mapped[float | None] = mapped_column(Float)
    # V2bd terms at K = 1: integral of Cn2 = K_TKE * i_tke + K_conv * i_conv + K_CIS * i_cis.
    i_tke: Mapped[float | None] = mapped_column(Float)
    i_conv: Mapped[float | None] = mapped_column(Float)
    i_cis: Mapped[float | None] = mapped_column(Float)
    # Model variables of the hour {t2, dth, u10, u100, u500, shl, shj, tke} (seeing_core.variables).
    variables: Mapped[dict | None] = mapped_column(JSONB)

    run: Mapped[ModelRun] = relationship(back_populates="forecasts")
    site: Mapped[Site] = relationship()


class Cn2Profile(Base):
    __tablename__ = "cn2_profiles"
    __table_args__ = (UniqueConstraint("run_id", "site_id", "lead_hour"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id", ondelete="CASCADE"), index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lead_hour: Mapped[int] = mapped_column(Integer)
    heights_m: Mapped[list[float]] = mapped_column(ARRAY(REAL))
    cn2: Mapped[list[float | None]] = mapped_column(ARRAY(REAL))
    #: True on the levels filled by the convective closure (hatched on the panel); NULL for older profiles.
    conv: Mapped[list[bool] | None] = mapped_column(ARRAY(Boolean))

    run: Mapped[ModelRun] = relationship(back_populates="cn2_profiles")
    site: Mapped[Site] = relationship()


class SiteHistory(Base):
    """History of a monitored site as computed by the research scripts (research/export_lieux_site.py):
    periods with forecast and measurements, hourly pairs, K = 1 integrals. Shown by the website."""

    __tablename__ = "site_history"

    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    data: Mapped[dict] = mapped_column(JSONB)


class Measurement(Base):
    """A seeing measurement of a site (seeing monitor, CSV upload), time in UTC."""

    __tablename__ = "measurements"
    __table_args__ = (UniqueConstraint("site_id", "time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    seeing_arcsec: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserRole(enum.StrEnum):
    """Account types: an individual user, the shared CosmoDrôme team account, or an administrator."""

    user = "user"
    team = "team"
    admin = "admin"


class User(Base):
    """An app account. E-mails are stored lower-cased; the password is an Argon2id hash."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="users_email_lowercase"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e]),
        default=UserRole.user,
        server_default=UserRole.user.value,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: When the address was confirmed through the e-mailed link (None: not confirmed yet).
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class UserSession(Base):
    """A login session. `id` is the SHA-256 hex digest of the cookie token, never the token itself."""

    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="sessions")


class EmailToken(Base):
    """A single-use link sent by e-mail (purpose "verify": confirm the address). `id` is the SHA-256 hex
    digest of the token in the link, never the token itself."""

    __tablename__ = "email_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthEvent(Base):
    """A rate-limited auth action (failed login, sign-up, confirmation e-mail), by e-mail and client IP.
    Only the last day is kept."""

    __tablename__ = "auth_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    ip: Mapped[str | None] = mapped_column(String(64), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
