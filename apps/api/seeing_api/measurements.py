"""Seeing measurements of a site and the V2bd terms used to calibrate its K.

Writing: the owner of a personal place, the administrator for every site, and the team account for its
site. Reading: the same, plus every logged-in user for the sites without owner, and everyone, even without an
account, for the public sites (their monitors are public). Calibration itself runs in the browser (the K fit is
a small grid search).
"""

import bisect
import math
import statistics
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from seeing_api.api import TEAM_SITE, SessionDep, utc
from seeing_api.auth import CurrentUser, require_json, require_role
from seeing_api.history import seeing_of
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


class SkillBin(BaseModel):
    """Forecasts issued `age_from` to `age_to` hours before the hour they forecast (lead), against the measurements."""

    age_from: int
    age_to: int
    n_hours: int
    n_nights: int
    r: float | None
    bias: float | None  # mean (forecast - measured), arcsec
    mae: float | None  # mean |forecast - measured|, arcsec
    sd: float | None  # standard deviation of forecast - measured (band around the bias)
    rmse: float | None


class SkillNight(BaseModel):
    """Night precision: for each run and night, median of its forecast hours against the median of the measured ones
    (as the night points of the correlation), grouped by the age of the run at 00h UTC (the middle of the night) in
    classes of SKILL_NIGHT_BIN_H hours, `age` to `age_to`: several nights per class, hence a band."""

    age: int
    age_to: int
    n_nights: int
    bias: float | None
    mae: float | None
    sd: float | None  # standard deviation of forecast - measured between the nights (band around the bias)


class SkillOut(BaseModel):
    bins: list[SkillBin]
    nights: list[SkillNight] = Field(default_factory=list)


SKILL_BIN_H = 1  # hourly error: one class per hour of age
SKILL_NIGHT_BIN_H = 6  # night error: classes of 6 h of age (runs every 6 h)
MEAS_HALF = timedelta(minutes=30)  # measured value of an hour: median of the measurements within +/- 30 min


def _measured(session, site_id: int, t0: datetime, t1: datetime):
    """Measured value of each hour from t0 to t1: median of the measurements within +/- 30 min of the hour, as the
    hourly medians of Calibrer and of the history (same value on every panel)."""
    ms = session.execute(
        select(Measurement.time, Measurement.seeing_arcsec)
        .where(Measurement.site_id == site_id, Measurement.time >= t0 - MEAS_HALF, Measurement.time <= t1 + MEAS_HALF)
        .order_by(Measurement.time)
    ).all()
    times = [utc(r.time) for r in ms]
    vals = [r.seeing_arcsec for r in ms]
    cache: dict[datetime, float | None] = {}

    def at(t: datetime) -> float | None:
        if t not in cache:
            w = vals[bisect.bisect_left(times, t - MEAS_HALF):bisect.bisect_right(times, t + MEAS_HALF)]
            cache[t] = statistics.median(w) if w else None
        return cache[t]

    return at


def _is_night(t: datetime) -> bool:
    """Night hours, 17h30-06h UTC, as on every chart of the site."""
    m = t.hour * 60 + t.minute
    return m >= 17 * 60 + 30 or m < 6 * 60


def _sd(x: list[float]) -> float | None:
    return statistics.stdev(x) if len(x) >= 2 else None


def _pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx, syy = sum((a - mx) ** 2 for a in x), sum((b - my) ** 2 for b in y)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else None


@router.get("/{slug}/skill", response_model=SkillOut)
def get_skill(slug: str, session: SessionDep, user: CurrentUser) -> SkillOut:
    """Precision of the AROME forecast with the age of the run (lead), night hours only. Every run that has the
    integrals at K = 1 of the hour (main or research secondary run) is recomputed with the site's current K, so that
    every age is compared with the same K; the hours without integrals are left out."""
    if user is None:
        site = public_site(session, slug)
        if site is None:
            raise HTTPException(401, "Not logged in")
    else:
        site = readable_site(session, slug, user)
    fc = session.execute(
        select(Forecast.valid_time, Forecast.lead_hour, Forecast.i_tke, Forecast.i_conv, Forecast.i_cis, ModelRun.run_time)
        .join(ModelRun, ModelRun.id == Forecast.run_id)
        .where(Forecast.site_id == site.id, ModelRun.status == RunStatus.success, Forecast.i_tke.is_not(None),
               Forecast.i_conv.is_not(None), Forecast.i_cis.is_not(None), Forecast.lead_hour >= 0)
    ).all()
    fc = [r for r in fc if _is_night(utc(r.valid_time))]
    if not fc:
        return SkillOut(bins=[])
    measured_at = _measured(session, site.id, utc(min(r.valid_time for r in fc)), utc(max(r.valid_time for r in fc)))

    groups: dict[int, list[tuple[float, float, datetime]]] = {}
    per_night: dict[tuple[datetime, object], list[tuple[float, float]]] = {}
    for r in fc:
        t = utc(r.valid_time)
        m = measured_at(t)
        if m is None:
            continue
        seeing, _ = seeing_of(site.k_tke * r.i_tke + site.k_tke_conv * r.i_conv + site.k_cis * r.i_cis)
        if seeing is None:
            continue
        groups.setdefault(r.lead_hour // SKILL_BIN_H, []).append((seeing, m, t))
        per_night.setdefault((utc(r.run_time), (t - timedelta(hours=12)).date()), []).append((seeing, m))
    bins = []
    for b in sorted(groups):
        g = groups[b]
        p, o = [x[0] for x in g], [x[1] for x in g]
        d = [a - c for a, c in zip(p, o)]
        bins.append(SkillBin(
            age_from=b * SKILL_BIN_H, age_to=(b + 1) * SKILL_BIN_H, n_hours=len(g),
            n_nights=len({(x[2] - timedelta(hours=12)).date() for x in g}), r=_pearson(p, o),
            bias=statistics.fmean(d), mae=statistics.fmean(abs(x) for x in d), sd=_sd(d),
            rmse=math.sqrt(statistics.fmean(x * x for x in d)),
        ))
    by_age: dict[int, list[float]] = {}
    for (run_time, night), g in per_night.items():
        if len(g) < 2:  # as the night points of the correlation
            continue
        midnight = datetime.combine(night + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        age = round((midnight - run_time).total_seconds() / 3600)
        by_age.setdefault(age // SKILL_NIGHT_BIN_H * SKILL_NIGHT_BIN_H, []).append(statistics.median(x[0] for x in g) - statistics.median(x[1] for x in g))
    nights = [SkillNight(age=a, age_to=a + SKILL_NIGHT_BIN_H, n_nights=len(d), bias=statistics.fmean(d), mae=statistics.fmean(abs(x) for x in d),
                         sd=_sd(d))
              for a, d in sorted(by_age.items())]
    return SkillOut(bins=bins, nights=nights)


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


def _hour_terms(session, site_id: int, start: datetime | None = None, end: datetime | None = None):
    """Integrals at K = 1 of each valid hour, from one run: main runs first, then the shortest lead; a secondary run
    (research history) only for the hours no main run covers. The same selection for Calibrer and the history."""
    where = [Forecast.site_id == site_id, ModelRun.status == RunStatus.success, Forecast.i_tke.is_not(None),
             Forecast.i_conv.is_not(None), Forecast.i_cis.is_not(None)]
    if start is not None:
        where.append(Forecast.valid_time >= start)
    if end is not None:
        where.append(Forecast.valid_time < end)
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
        .where(*where)
        .subquery()
    )
    return session.execute(select(ranked).where(ranked.c.rk == 1).order_by(ranked.c.valid_time)).all()


class VerifOut(BaseModel):
    """Forecast of each hour that has its integrals at K = 1, recomputed with the site's current K (the run chosen as
    for Calibrer), and the measured value of the hour (median +/- 30 min) where there are measurements."""

    valid_times: list[datetime]
    seeing_arcsec: list[float | None]
    measured_arcsec: list[float | None]


@router.get("/{slug}/verif", response_model=VerifOut)
def get_verif(slug: str, session: SessionDep, user: CurrentUser) -> VerifOut:
    """History and correlation of the Prévision tab: one forecast per hour, at the current K, hours without integrals
    left out. The K stay on the server."""
    if user is None:
        site = public_site(session, slug)
        if site is None:
            raise HTTPException(401, "Not logged in")
    else:
        site = readable_site(session, slug, user)
    rows = _hour_terms(session, site.id)
    if not rows:
        return VerifOut(valid_times=[], seeing_arcsec=[], measured_arcsec=[])
    at = _measured(session, site.id, utc(rows[0].valid_time), utc(rows[-1].valid_time))
    see = [seeing_of(site.k_tke * r.i_tke + site.k_tke_conv * r.i_conv + site.k_cis * r.i_cis)[0] for r in rows]
    return VerifOut(valid_times=[utc(r.valid_time) for r in rows], seeing_arcsec=[round(v, 3) if v else None for v in see],
                    measured_arcsec=[at(utc(r.valid_time)) for r in rows])


@router.get("/{slug}/terms", response_model=TermsOut)
def get_terms(
    slug: str, session: SessionDep, user: LoggedIn,
    start: Annotated[datetime, Query(alias="from")], end: Annotated[datetime, Query(alias="to")],
) -> TermsOut:
    site = editable_site(session, slug, user)
    if end - start > timedelta(days=400):
        raise HTTPException(422, "At most 400 days at once")
    rows = _hour_terms(session, site.id, start, end)
    return TermsOut(
        valid_times=[utc(r.valid_time) for r in rows], lead_hours=[r.lead_hour for r in rows],
        i_tke=[r.i_tke for r in rows], i_conv=[r.i_conv for r in rows], i_cis=[r.i_cis for r in rows],
    )
