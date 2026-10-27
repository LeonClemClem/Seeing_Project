"""Research history of the monitored sites.

- `PUT /api/admin/sites/{slug}/history` (administrator): the site's entry of research/export_lieux_site.py
  (periods, hourly pairs, K = 1 integrals), shown as is by the website.
- `POST /api/admin/sites/{slug}/forecasts` (administrator): forecast runs computed by the research scripts
  (V2bd terms at K = 1 per lead hour), stored as model runs so that calibration uses them. Rows that the
  batch already computed are never replaced.
- `POST /api/admin/sites/{slug}/cn2` (administrator): Cn2 profiles of research runs (display grid), so
  that the week view of the Cn2 panel goes back to the research runs. Existing profiles are kept.
- `GET /api/sites/{slug}/history`: the stored history; K and integrals only for those who may calibrate.
"""

import math
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from seeing_api.api import TEAM_SITE, SessionDep, get_site
from seeing_api.auth import CurrentUser, require_json, require_role
from seeing_db import Cn2Profile, Forecast, ModelRun, RunStatus, Site, SiteHistory, User, UserRole

admin = APIRouter(prefix="/api/admin", dependencies=[Depends(require_json)])
public = APIRouter(prefix="/api/sites")
Admin = Annotated[User, Depends(require_role(UserRole.admin))]

LAMBDA = 500e-9


def _site(session, slug: str) -> Site:
    site = session.scalar(select(Site).where(Site.slug == slug))
    if site is None:
        raise HTTPException(404, f"Unknown site '{slug}'")
    return site


@admin.put("/sites/{slug}/history")
def put_history(slug: str, body: dict[str, Any], session: SessionDep, user: Admin) -> dict:
    site = _site(session, slug)
    stmt = pg_insert(SiteHistory).values(site_id=site.id, data=body, generated_at=datetime.now(UTC))
    session.execute(stmt.on_conflict_do_update(index_elements=["site_id"], set_={"data": stmt.excluded.data, "generated_at": stmt.excluded.generated_at}))
    session.commit()
    return {"site": slug, "episodes": len(body.get("episodes", [])), "pairs": len(body.get("paires", []))}


class RunIn(BaseModel):
    run_time: datetime
    # [lead_hour, h_coulim_m | null, i_tke, i_conv, i_cis]
    hours: list[tuple[int, float | None, float, float, float]] = Field(max_length=200)


class RunsIn(BaseModel):
    runs: list[RunIn] = Field(min_length=1, max_length=500)


def seeing_of(integral: float) -> tuple[float | None, float | None]:
    if not (integral > 0 and math.isfinite(integral)):
        return None, None
    r0 = (0.423 * (2 * math.pi / LAMBDA) ** 2 * integral) ** (-3 / 5)
    return 0.98 * LAMBDA / r0 * 206265.0, r0


@admin.post("/sites/{slug}/forecasts")
def post_forecasts(slug: str, body: RunsIn, session: SessionDep, user: Admin) -> dict:
    site = _site(session, slug)
    added_runs = rows = skipped = too_recent = 0
    # A research run newer than every stored run would become the "latest" run of the website: skipped.
    newest = session.scalar(select(func.max(ModelRun.run_time)))
    for r in body.runs:
        rt = r.run_time.replace(tzinfo=UTC) if r.run_time.tzinfo is None else r.run_time.astimezone(UTC)
        run = session.scalar(select(ModelRun).where(ModelRun.run_time == rt))
        if run is None and newest is not None and rt > newest:
            too_recent += 1
            continue
        if run is None:
            run = ModelRun(run_time=rt, status=RunStatus.success, started_at=rt, finished_at=rt)
            session.add(run)
            session.flush()
            added_runs += 1
        values = []
        for lead, h, it, ic, isx in r.hours:
            integral = site.k_tke * it + site.k_tke_conv * ic + site.k_cis * isx
            seeing, r0 = seeing_of(integral)
            values.append(dict(run_id=run.id, site_id=site.id, valid_time=rt + timedelta(hours=lead), lead_hour=lead,
                               seeing_arcsec=seeing, r0_m=r0, integral_cn2=integral if seeing else None,
                               h_coulim_m=h, i_tke=it, i_conv=ic, i_cis=isx))
        if values:
            # rowcount is not reliable for multi-row inserts: count the inserted ids
            inserted = len(session.execute(pg_insert(Forecast).values(values).on_conflict_do_nothing(
                index_elements=["run_id", "site_id", "lead_hour"]).returning(Forecast.id)).all())
            rows += inserted
            skipped += len(values) - inserted
    session.commit()
    return {"site": slug, "new_runs": added_runs, "rows": rows, "kept_existing": skipped, "too_recent_runs": too_recent}


class Cn2RunIn(BaseModel):
    run_time: datetime
    # [lead_hour, [Cn2 on heights_m, null where undefined]]
    hours: list[tuple[int, list[float | None]]] = Field(max_length=200)


class Cn2In(BaseModel):
    heights_m: list[float] = Field(min_length=2, max_length=400)
    runs: list[Cn2RunIn] = Field(min_length=1, max_length=50)


@admin.post("/sites/{slug}/cn2")
def post_cn2(slug: str, body: Cn2In, session: SessionDep, user: Admin) -> dict:
    site = _site(session, slug)
    newest = session.scalar(select(func.max(ModelRun.run_time)))
    rows = skipped = too_recent = 0
    for r in body.runs:
        rt = r.run_time.replace(tzinfo=UTC) if r.run_time.tzinfo is None else r.run_time.astimezone(UTC)
        run = session.scalar(select(ModelRun).where(ModelRun.run_time == rt))
        if run is None and newest is not None and rt > newest:
            too_recent += 1
            continue
        if run is None:
            run = ModelRun(run_time=rt, status=RunStatus.success, started_at=rt, finished_at=rt)
            session.add(run)
            session.flush()
        values = [
            dict(run_id=run.id, site_id=site.id, valid_time=rt + timedelta(hours=lead), lead_hour=lead,
                 heights_m=body.heights_m, cn2=[v if v is None or math.isfinite(v) else None for v in cn2])
            for lead, cn2 in r.hours if len(cn2) == len(body.heights_m)
        ]
        if values:
            inserted = len(session.execute(pg_insert(Cn2Profile).values(values).on_conflict_do_nothing(
                index_elements=["run_id", "site_id", "lead_hour"]).returning(Cn2Profile.id)).all())
            rows += inserted
            skipped += len(values) - inserted
    session.commit()
    return {"site": slug, "profiles": rows, "kept_existing": skipped, "too_recent_runs": too_recent}


@public.get("/{slug}/history")
def get_history(slug: str, session: SessionDep, user: CurrentUser) -> dict:
    site = get_site(session, slug, user)
    row = session.get(SiteHistory, site.id)
    if row is None:
        raise HTTPException(404, f"No history for '{slug}'")
    may_calibrate = user is not None and (
        site.owner_id == user.id or user.role == UserRole.admin or (user.role == UserRole.team and site.slug == TEAM_SITE)
    )
    data = dict(row.data)
    if not may_calibrate:  # the K stay confidential (the integrals would give them back)
        for key in ("K", "integ", "cn2", "cn2w"):
            data.pop(key, None)
    data["generated_at"] = row.generated_at.astimezone(UTC).isoformat()
    return data
