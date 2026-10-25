"""JSON endpoints under /api (see docs/architecture.md, section API)."""

import math
import os
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from seeing_api.auth import NO_STORE, CurrentUser, user_out
from seeing_api.db import get_session
from seeing_api.schemas import Cn2Out, ForecastOut, ForecastPoint, MeOut, RunOut, SiteOut
from seeing_db import Cn2Profile, Forecast, ModelRun, RunStatus, Site

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
RunParam = Annotated[str, Query(description="`latest` or an ISO 8601 run time, e.g. 2026-10-13T12:00Z")]

IAP_EMAIL_HEADER = "X-Goog-Authenticated-User-Email"


def clean(value: float | None) -> float | None:
    """NaN/inf -> None so the JSON encoder emits null."""
    if value is None or not math.isfinite(value):
        return None
    return float(value)


def utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def site_out(site: Site) -> SiteOut:
    return SiteOut(
        slug=site.slug, name=site.name, lat=site.lat, lon=site.lon, altitude_m=clean(site.altitude_m),
        visibility=site.visibility,
    )


def get_site(session: Session, slug: str) -> Site:
    site = session.scalar(select(Site).where(Site.slug == slug, Site.active.is_(True), Site.visibility != "hidden"))
    if site is None:
        raise HTTPException(404, f"Unknown site '{slug}'")
    return site


def resolve_run(session: Session, run: str) -> ModelRun:
    """Only successful runs are ever visible."""
    query = select(ModelRun).where(ModelRun.status == RunStatus.success)
    if run == "latest":
        found = session.scalar(query.order_by(ModelRun.run_time.desc()).limit(1))
        if found is None:
            raise HTTPException(404, "No successful model run yet")
        return found
    try:
        run_time = utc(datetime.fromisoformat(run))
    except ValueError:
        raise HTTPException(422, f"Invalid run '{run}': expected 'latest' or an ISO 8601 datetime") from None
    found = session.scalar(query.where(ModelRun.run_time == run_time))
    if found is None:
        raise HTTPException(404, f"No successful model run at {run_time.isoformat()}")
    return found


@router.get("/me", response_model=MeOut)
def me(request: Request, response: Response, user: CurrentUser) -> MeOut:
    response.headers["Cache-Control"] = NO_STORE
    raw = request.headers.get(IAP_EMAIL_HEADER)
    email = raw.split(":", 1)[-1] if raw else None
    return MeOut(email=email or None, env=os.environ.get("ENV", "dev"), user=user_out(user) if user else None)


@router.get("/sites", response_model=list[SiteOut])
def list_sites(session: SessionDep) -> list[SiteOut]:
    sites = session.scalars(
        select(Site).where(Site.active.is_(True), Site.visibility != "hidden").order_by(Site.name)
    )
    return [site_out(s) for s in sites]


@router.get("/runs/latest", response_model=RunOut)
def latest_run(session: SessionDep) -> RunOut:
    run = resolve_run(session, "latest")
    return RunOut(
        run_time=utc(run.run_time),
        finished_at=utc(run.finished_at) if run.finished_at else None,
        status=run.status.value,
    )


@router.get("/sites/{slug}/forecast", response_model=ForecastOut)
def site_forecast(slug: str, session: SessionDep, run: RunParam = "latest") -> ForecastOut:
    site = get_site(session, slug)
    model_run = resolve_run(session, run)
    rows = session.scalars(
        select(Forecast)
        .where(Forecast.run_id == model_run.id, Forecast.site_id == site.id)
        .order_by(Forecast.lead_hour)
    )
    points = [
        ForecastPoint(
            lead_hour=f.lead_hour,
            valid_time=utc(f.valid_time),
            seeing_arcsec=clean(f.seeing_arcsec),
            r0_m=clean(f.r0_m),
            integral_cn2=clean(f.integral_cn2),
            h_coulim_m=clean(f.h_coulim_m),
        )
        for f in rows
    ]
    return ForecastOut(site=site_out(site), run_time=utc(model_run.run_time), points=points)


def _height_key(h: float) -> float:
    # heights are stored as REAL: round to the decimetre so that 100.0 and 100.00001 coincide.
    return round(float(h), 1)


@router.get("/sites/{slug}/cn2", response_model=Cn2Out)
def site_cn2(slug: str, session: SessionDep, run: RunParam = "latest") -> Cn2Out:
    site = get_site(session, slug)
    model_run = resolve_run(session, run)
    profiles = list(
        session.scalars(
            select(Cn2Profile)
            .where(Cn2Profile.run_id == model_run.id, Cn2Profile.site_id == site.id)
            .order_by(Cn2Profile.lead_hour)
        )
    )
    heights = sorted({_height_key(h) for p in profiles for h in p.heights_m if h is not None and math.isfinite(h)})
    index = {h: i for i, h in enumerate(heights)}
    matrix: list[list[float | None]] = []
    for p in profiles:
        row: list[float | None] = [None] * len(heights)
        for h, v in zip(p.heights_m, p.cn2, strict=False):
            if h is None or not math.isfinite(h):
                continue
            row[index[_height_key(h)]] = clean(v)
        matrix.append(row)
    return Cn2Out(
        site=site_out(site),
        run_time=utc(model_run.run_time),
        valid_times=[utc(p.valid_time) for p in profiles],
        heights_m=heights,
        cn2=matrix,
    )
