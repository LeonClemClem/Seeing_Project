"""JSON endpoints under /api (see docs/architecture.md, section API)."""

import hashlib
import math
from datetime import timedelta
import os
import zlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from seeing_api.auth import NO_STORE, CurrentUser, user_out
from seeing_api.db import get_session
from seeing_api.schemas import Cn2Out, ForecastOut, ForecastPoint, MapFrameOut, MapGridOut, MapOut, MeOut, RunOut, SiteOut
from seeing_db import Cn2Profile, Forecast, MapFrame, ModelRun, RunStatus, Site, User, UserRole

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
RunParam = Annotated[str, Query(description="`latest` or an ISO 8601 run time, e.g. 2026-10-13T12:00Z")]
ViewParam = Annotated[
    str,
    Query(pattern="^(run|week)$", description="`run`: the run only; `week`: up to 7 days of main runs stitched, then the run"),
]
WEEK = timedelta(days=7)


def stitched(session: Session, model, site_id: int, run: ModelRun):
    """Rows of `model` (Forecast or Cn2Profile) for every valid hour from 7 days before `run` to the end
    of `run`: for each hour, the main run (00/06/12/18Z) issued last before it, i.e. the shortest lead,
    other runs only to fill gaps; runs after `run` are ignored."""
    ranked = (
        select(model.id, func.row_number().over(
            partition_by=model.valid_time,
            order_by=(func.mod(func.extract("hour", ModelRun.run_time), 6) != 0, model.lead_hour),
        ).label("rk"))
        .join(ModelRun, ModelRun.id == model.run_id)
        .where(model.site_id == site_id, ModelRun.status == RunStatus.success, ModelRun.run_time <= run.run_time,
               model.valid_time >= run.run_time - WEEK)
        .subquery()
    )
    return session.scalars(
        select(model).join(ranked, ranked.c.id == model.id).where(ranked.c.rk == 1).order_by(model.valid_time)
    ).all()

IAP_EMAIL_HEADER = "X-Goog-Authenticated-User-Email"


def clean(value: float | None) -> float | None:
    """NaN/inf -> None so the JSON encoder emits null."""
    if value is None or not math.isfinite(value):
        return None
    return float(value)


def utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


# Site of the shared "CosmoDrôme team" account: its team sees its K.
TEAM_SITE = "cosmodrome"


def blur(slug: str, lat: float, lon: float) -> tuple[float, float]:
    """Position moved by 5-11 km in a direction fixed by the slug (shared personal places)."""
    h = hashlib.sha256(slug.encode()).digest()
    d = 5.0 + 6.0 * h[0] / 255.0
    b = 2.0 * math.pi * int.from_bytes(h[1:3], "big") / 65536.0
    return lat + d / 111.2 * math.cos(b), lon + d / (111.32 * math.cos(math.radians(lat))) * math.sin(b)


def site_out(site: Site, user: User | None = None) -> SiteOut:
    owned = user is not None and site.owner_id == user.id
    admin = user is not None and user.role == UserRole.admin
    team = user is not None and user.role == UserRole.team and site.slug == TEAM_SITE
    lat, lon, name, alt = site.lat, site.lon, site.name, clean(site.altitude_m)
    if site.owner_id is not None and not owned:
        # Another member's shared place: no name, approximate position (also for the administrator).
        lat, lon = blur(site.slug, site.lat, site.lon)
        name, alt = "Lieu partagé", None
    return SiteOut(
        slug=site.slug, name=name, lat=lat, lon=lon, altitude_m=alt, visibility=site.visibility, owned=owned,
        k=[site.k_tke, site.k_cis, site.k_tke_conv] if owned or team or (admin and site.owner_id is None) else None,
    )


def site_filter(user: User | None) -> list:
    """Active public and shared sites, the account's own places, and the hidden sites (computed, not
    offered) for the administrator. Other members' private places are never served."""
    allowed = Site.visibility.in_(["public", "shared"])
    if user is not None:
        allowed = or_(allowed, Site.owner_id == user.id)
        if user.role == UserRole.admin:
            allowed = or_(allowed, Site.visibility == "hidden")
    return [Site.active.is_(True), allowed]


def get_site(session: Session, slug: str, user: User | None = None) -> Site:
    site = session.scalar(select(Site).where(Site.slug == slug, *site_filter(user)))
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
def list_sites(session: SessionDep, user: CurrentUser) -> list[SiteOut]:
    sites = session.scalars(select(Site).where(*site_filter(user)).order_by(Site.name))
    return [site_out(s, user) for s in sites]


@router.get("/runs/latest", response_model=RunOut)
def latest_run(session: SessionDep) -> RunOut:
    run = resolve_run(session, "latest")
    return RunOut(
        run_time=utc(run.run_time),
        finished_at=utc(run.finished_at) if run.finished_at else None,
        status=run.status.value,
    )


@router.get("/sites/{slug}/forecast", response_model=ForecastOut)
def site_forecast(
    slug: str, session: SessionDep, user: CurrentUser, run: RunParam = "latest", view: ViewParam = "run"
) -> ForecastOut:
    site = get_site(session, slug, user)
    model_run = resolve_run(session, run)
    if view == "week":
        rows = stitched(session, Forecast, site.id, model_run)
    else:
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
            model_altitude_m=clean(f.model_altitude_m),
            variables=f.variables,
        )
        for f in rows
    ]
    return ForecastOut(site=site_out(site, user), run_time=utc(model_run.run_time), points=points)


def _height_key(h: float) -> float:
    # heights are stored as REAL: round to the decimetre so that 100.0 and 100.00001 coincide.
    return round(float(h), 1)


@router.get("/sites/{slug}/cn2", response_model=Cn2Out)
def site_cn2(
    slug: str, session: SessionDep, user: CurrentUser, run: RunParam = "latest", view: ViewParam = "run"
) -> Cn2Out:
    site = get_site(session, slug, user)
    model_run = resolve_run(session, run)
    if view == "week":
        profiles = list(stitched(session, Cn2Profile, site.id, model_run))
    else:
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
        site=site_out(site, user),
        run_time=utc(model_run.run_time),
        valid_times=[utc(p.valid_time) for p in profiles],
        heights_m=heights,
        cn2=matrix,
    )


# Same scale as seeing_core.grid.SEE_MIN / SEE_MAX (the API does not depend on seeing_core).
MAP_SEE_MIN, MAP_SEE_MAX = 0.2, 10.0
RELIEF_LEAD = -1  # map_frames row of the orography (seeing_core.grid.RELIEF_LEAD)


def _map_run(session: Session, run: str) -> ModelRun:
    """`latest` = the newest successful run that has a map."""
    if run != "latest":
        return resolve_run(session, run)
    found = session.scalar(
        select(ModelRun)
        .where(ModelRun.status == RunStatus.success, ModelRun.id.in_(select(MapFrame.run_id).where(MapFrame.lead_hour >= 0)))
        .order_by(ModelRun.run_time.desc())
        .limit(1)
    )
    if found is None:
        raise HTTPException(404, "No global map yet")
    return found


@router.get("/map", response_model=MapOut)
def global_map(session: SessionDep, run: RunParam = "latest") -> MapOut:
    model_run = _map_run(session, run)
    rows = session.execute(
        select(MapFrame.lead_hour, MapFrame.valid_time, MapFrame.ny, MapFrame.nx, MapFrame.lat0, MapFrame.lon0,
               MapFrame.dlat, MapFrame.dlon)
        .where(MapFrame.run_id == model_run.id, MapFrame.lead_hour >= 0)
        .order_by(MapFrame.lead_hour)
    ).all()
    if not rows:
        raise HTTPException(404, f"No global map for the run {utc(model_run.run_time).isoformat()}")
    r = rows[0]
    return MapOut(
        run_time=utc(model_run.run_time),
        grid=MapGridOut(ny=r.ny, nx=r.nx, lat0=r.lat0, lon0=r.lon0, dlat=r.dlat, dlon=r.dlon),
        see_min=MAP_SEE_MIN,
        see_max=MAP_SEE_MAX,
        frames=[MapFrameOut(lead_hour=x.lead_hour, valid_time=utc(x.valid_time)) for x in rows],
        relief=session.scalar(select(MapFrame.id).where(MapFrame.run_id == model_run.id, MapFrame.lead_hour == RELIEF_LEAD))
        is not None,
    )


@router.get("/map/relief")
def global_map_relief(session: SessionDep, run: RunParam = "latest") -> Response:
    """Model orography of the map grid: ny * nx little-endian uint16, altitude = value - 500 m, 65535 = none."""
    model_run = _map_run(session, run)
    data = session.scalar(select(MapFrame.data).where(MapFrame.run_id == model_run.id, MapFrame.lead_hour == RELIEF_LEAD))
    if data is None:
        raise HTTPException(404, "No relief for this map")
    return Response(zlib.decompress(data), media_type="application/octet-stream",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/map/frame")
def global_map_frame(session: SessionDep, lead: int, run: RunParam = "latest") -> Response:
    model_run = _map_run(session, run)
    data = session.scalar(select(MapFrame.data).where(MapFrame.run_id == model_run.id, MapFrame.lead_hour == lead))
    if data is None:
        raise HTTPException(404, f"No map frame at H+{lead}")
    # A run's frames never change: cacheable for a day.
    return Response(zlib.decompress(data), media_type="application/octet-stream",
                    headers={"Cache-Control": "public, max-age=86400"})
