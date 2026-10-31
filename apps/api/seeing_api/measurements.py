"""Seeing measurements of a site and the V2bd terms used to calibrate its K.

Writing: the owner of a personal place, the administrator for every site, and the team account for its
site. Reading: the same, plus every logged-in user for the sites without owner, and everyone, even without an
account, for the public sites (their monitors are public). Calibration itself runs in the browser (the K fit is
a small grid search).
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from seeing_api.api import TEAM_SITE, SessionDep, utc
from seeing_api.auth import CurrentUser, require_json, require_role
from seeing_db import Forecast, Measurement, ModelRun, RunStatus, Site, User, UserRole

router = APIRouter(prefix="/api/sites")
LoggedIn = Annotated[User, Depends(require_role())]

MAX_POINTS = 20000  # per upload
SEEING_RANGE = (0.05, 20.0)


def editable_site(session, slug: str, user: User) -> Site:
    site = session.scalar(select(Site).where(Site.slug == slug, Site.active.is_(True)))
    ok = site is not None and (
        site.owner_id == user.id
        or user.role == UserRole.admin
        or (user.role == UserRole.team and site.slug == TEAM_SITE)
    )
    if not ok:
        raise HTTPException(404, f"Unknown site '{slug}'")
    return site


def readable_site(session, slug: str, user: User) -> Site:
    """Public sites (no owner) are readable by everyone logged in; other sites as `editable_site`."""
    site = session.scalar(select(Site).where(Site.slug == slug, Site.active.is_(True)))
    if site is not None and site.owner_id is None:
        return site
    return editable_site(session, slug, user)


def public_site(session, slug: str) -> Site | None:
    """Site readable without an account: a public site (visibility "public", no owner)."""
    site = session.scalar(select(Site).where(Site.slug == slug, Site.active.is_(True)))
    return site if site is not None and site.owner_id is None and site.visibility == "public" else None


class CalibSettings(BaseModel):
    """Calibration settings of a place (Calibrer): filters and nights left out by hand. Nothing is deleted:
    the measurements of a night left out stay stored."""

    pics: bool = False
    courtes: bool = False
    top: int = Field(default=0, ge=0, le=50)
    out: list[Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]] = Field(default_factory=list, max_length=2000)


class KIn(BaseModel):
    """K of a site, used by the batch from its next run (Calibrer, "Enregistrer pour ce lieu")."""

    k_tke: float = Field(gt=0, le=150)
    k_cis: float = Field(gt=0, le=150)
    k_conv: float = Field(ge=0, le=150)


class MeasurementsIn(BaseModel):
    # [[ISO 8601 UTC time, seeing arcsec], ...]
    points: list[tuple[datetime, float]] = Field(min_length=1, max_length=MAX_POINTS)


class MeasurementsOut(BaseModel):
    times: list[datetime]
    seeing_arcsec: list[float]


class TermsOut(BaseModel):
    """For each valid hour, the V2bd terms of the latest run issued before it (shortest lead)."""

    valid_times: list[datetime]
    lead_hours: list[int]
    i_tke: list[float | None]
    i_conv: list[float | None]
    i_cis: list[float | None]


@router.post("/{slug}/measurements", dependencies=[Depends(require_json)])
def add_measurements(slug: str, body: MeasurementsIn, session: SessionDep, user: LoggedIn) -> dict:
    site = editable_site(session, slug, user)
    rows = {}
    for t, v in body.points:
        if SEEING_RANGE[0] <= v <= SEEING_RANGE[1]:
            t = t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)
            rows[t] = v
    if rows:
        stmt = pg_insert(Measurement).values([dict(site_id=site.id, time=t, seeing_arcsec=v) for t, v in rows.items()])
        session.execute(stmt.on_conflict_do_update(index_elements=["site_id", "time"], set_={"seeing_arcsec": stmt.excluded.seeing_arcsec}))
        session.commit()
    return {"stored": len(rows), "rejected": len(body.points) - len(rows)}


@router.get("/{slug}/measurements", response_model=MeasurementsOut)
def get_measurements(
    slug: str, session: SessionDep, user: CurrentUser,
    start: Annotated[datetime | None, Query(alias="from")] = None, end: Annotated[datetime | None, Query(alias="to")] = None,
) -> MeasurementsOut:
    if user is None:  # without an account: the public sites only
        site = public_site(session, slug)
        if site is None:
            raise HTTPException(401, "Not logged in")
    else:
        site = readable_site(session, slug, user)
    q = select(Measurement.time, Measurement.seeing_arcsec).where(Measurement.site_id == site.id)
    if start:
        q = q.where(Measurement.time >= start)
    if end:
        q = q.where(Measurement.time < end)
    rows = session.execute(q.order_by(Measurement.time)).all()
    return MeasurementsOut(times=[utc(r.time) for r in rows], seeing_arcsec=[r.seeing_arcsec for r in rows])


@router.delete("/{slug}/measurements", status_code=204, dependencies=[Depends(require_json)])
def delete_measurements(
    slug: str, session: SessionDep, user: LoggedIn, night: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
) -> Response:
    """Delete every measurement of the site, or those of one night (12h UTC of `night` to 12h the next day)."""
    site = editable_site(session, slug, user)
    q = delete(Measurement).where(Measurement.site_id == site.id)
    if night:
        t0 = datetime.fromisoformat(night).replace(hour=12, tzinfo=UTC)
        q = q.where(Measurement.time >= t0, Measurement.time < t0 + timedelta(days=1))
    session.execute(q)
    session.commit()
    return Response(status_code=204)


@router.put("/{slug}/k", status_code=204, dependencies=[Depends(require_json)])
def put_k(slug: str, body: KIn, session: SessionDep, user: LoggedIn) -> Response:
    """Save the K of a site: its owner, the administrator for every site, the team for its site."""
    site = editable_site(session, slug, user)
    site.k_tke, site.k_cis, site.k_tke_conv = body.k_tke, body.k_cis, body.k_conv
    session.commit()
    return Response(status_code=204)


@router.get("/{slug}/calib", response_model=CalibSettings)
def get_calib(slug: str, session: SessionDep, user: LoggedIn) -> CalibSettings:
    site = editable_site(session, slug, user)
    return CalibSettings(**(site.calib or {}))


@router.put("/{slug}/calib", status_code=204, dependencies=[Depends(require_json)])
def put_calib(slug: str, body: CalibSettings, session: SessionDep, user: LoggedIn) -> Response:
    site = editable_site(session, slug, user)
    site.calib = body.model_dump() | {"out": sorted(set(body.out))}
    session.commit()
    return Response(status_code=204)


@router.get("/{slug}/terms", response_model=TermsOut)
def get_terms(
    slug: str, session: SessionDep, user: LoggedIn,
    start: Annotated[datetime, Query(alias="from")], end: Annotated[datetime, Query(alias="to")],
) -> TermsOut:
    site = editable_site(session, slug, user)
    if end - start > timedelta(days=400):
        raise HTTPException(422, "At most 400 days at once")
    ranked = (
        select(
            Forecast.valid_time, Forecast.lead_hour, Forecast.i_tke, Forecast.i_conv, Forecast.i_cis,
            # main runs (00/06/12/18Z) first, then the shortest lead; a secondary run (research history) only for the
            # hours no main run covers: its integrals at K = 1 are as valid for the calibration
            func.row_number().over(
                partition_by=Forecast.valid_time,
                order_by=(func.mod(func.extract("hour", ModelRun.run_time), 6) != 0, Forecast.lead_hour),
            ).label("rk"),
        )
        .join(ModelRun, ModelRun.id == Forecast.run_id)
        .where(
            Forecast.site_id == site.id, ModelRun.status == RunStatus.success, Forecast.i_tke.is_not(None),
            Forecast.valid_time >= start, Forecast.valid_time < end,
        )
        .subquery()
    )
    rows = session.execute(select(ranked).where(ranked.c.rk == 1).order_by(ranked.c.valid_time)).all()
    return TermsOut(
        valid_times=[utc(r.valid_time) for r in rows], lead_hours=[r.lead_hour for r in rows],
        i_tke=[r.i_tke for r in rows], i_conv=[r.i_conv for r in rows], i_cis=[r.i_cis for r in rows],
    )
