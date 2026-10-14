import enum
from datetime import datetime

from sqlalchemy import (
    REAL,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
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
    k_tke_conv: Mapped[float] = mapped_column(Float, default=0.3)
    k_tke: Mapped[float] = mapped_column(Float, default=3.0)
    k_cis: Mapped[float] = mapped_column(Float, default=30.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
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


class Forecast(Base):
    __tablename__ = "forecasts"
    __table_args__ = (UniqueConstraint("run_id", "site_id", "lead_hour"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id", ondelete="CASCADE"), index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), index=True)
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lead_hour: Mapped[int] = mapped_column(Integer)
    seeing_arcsec: Mapped[float | None] = mapped_column(Float)
    r0_m: Mapped[float | None] = mapped_column(Float)
    integral_cn2: Mapped[float | None] = mapped_column(Float)
    h_coulim_m: Mapped[float | None] = mapped_column(Float)
    model_altitude_m: Mapped[float | None] = mapped_column(Float)

    run: Mapped[ModelRun] = relationship(back_populates="forecasts")
    site: Mapped[Site] = relationship()


class Cn2Profile(Base):
    __tablename__ = "cn2_profiles"
    __table_args__ = (UniqueConstraint("run_id", "site_id", "lead_hour"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id", ondelete="CASCADE"), index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), index=True)
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lead_hour: Mapped[int] = mapped_column(Integer)
    heights_m: Mapped[list[float]] = mapped_column(ARRAY(REAL))
    cn2: Mapped[list[float | None]] = mapped_column(ARRAY(REAL))

    run: Mapped[ModelRun] = relationship(back_populates="cn2_profiles")
    site: Mapped[Site] = relationship()
