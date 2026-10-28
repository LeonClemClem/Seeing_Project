"""Database writes of the batch job (through seeing_db models)."""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from seeing_core import SiteForecast, SiteSpec
from seeing_db import Cn2Profile, Forecast, MapFrame, ModelRun, RunStatus, Site

logger = logging.getLogger(__name__)


def _num(x) -> float | None:
    """NaN / inf -> None (SQL NULL)."""
    if x is None:
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def load_sites(session: Session) -> list[tuple[int, SiteSpec]]:
    rows = session.scalars(select(Site).where(Site.active.is_(True)).order_by(Site.id)).all()
    return [
        (s.id, SiteSpec(slug=s.slug, lat=s.lat, lon=s.lon, k_tke_conv=s.k_tke_conv, k_tke=s.k_tke, k_cis=s.k_cis))
        for s in rows
    ]


def store_cells(session_factory: sessionmaker, grid, site_rows: list[tuple[int, SiteSpec]]) -> int:
    """AROME orography of the 5 x 5 grid cells around each active site (full resolution), for the
    "Mailles AROME autour du lieu" panel. Returns the number of sites updated."""
    from seeing_core.grid import cells_around

    n = 0
    with session_factory() as session:
        for sid, spec in site_rows:
            cells = cells_around(grid.surface_h_full, grid.geometry_full, spec.lat, spec.lon)
            if cells is not None:
                session.execute(update(Site).where(Site.id == sid).values(cells=cells))
                n += 1
        session.commit()
    return n


def run_status(session: Session, run_time: datetime) -> RunStatus | None:
    return session.scalar(select(ModelRun.status).where(ModelRun.run_time == run_time))


def start_run(session_factory: sessionmaker, run_time: datetime) -> int:
    """Upsert the model_runs row of `run_time` as `running`; returns its id."""
    with session_factory.begin() as session:
        session.execute(
            pg_insert(ModelRun)
            .values(run_time=run_time, status=RunStatus.running)
            .on_conflict_do_nothing(index_elements=["run_time"])
        )
        run = session.scalars(select(ModelRun).where(ModelRun.run_time == run_time).with_for_update()).one()
        run.status = RunStatus.running
        run.started_at = datetime.now(UTC)
        run.finished_at = None
        run.error = None
        return run.id


def store_results(
    session_factory: sessionmaker,
    run_id: int,
    forecasts: Mapping[str, SiteForecast],
    site_ids: Mapping[str, int],
    map_frames: Sequence[Mapping] = (),
) -> int:
    """Replace all rows of the run (and its map frames, MapFrame columns without run_id) and flip it
    to `success`, in one transaction. Returns the number of forecast rows written."""
    n = 0
    with session_factory.begin() as session:
        session.execute(delete(Forecast).where(Forecast.run_id == run_id))
        session.execute(delete(Cn2Profile).where(Cn2Profile.run_id == run_id))
        session.execute(delete(MapFrame).where(MapFrame.run_id == run_id))
        if map_frames:
            session.execute(pg_insert(MapFrame), [dict(f, run_id=run_id) for f in map_frames])
        forecast_rows, profile_rows = [], []
        for slug, fc in forecasts.items():
            site_id = site_ids[slug]
            for h in fc.hours:
                forecast_rows.append(dict(
                    run_id=run_id, site_id=site_id, valid_time=h.valid_time, lead_hour=h.lead_hour,
                    seeing_arcsec=_num(h.seeing_arcsec), r0_m=_num(h.r0_m), integral_cn2=_num(h.integral_cn2),
                    h_coulim_m=_num(h.h_coulim_m), model_altitude_m=_num(h.model_altitude_m),
                    i_tke=_num(getattr(h, "i_tke", None)), i_conv=_num(getattr(h, "i_conv", None)),
                    i_cis=_num(getattr(h, "i_cis", None)),
                    variables=getattr(h, "variables", None),
                ))
                profile_rows.append(dict(
                    run_id=run_id, site_id=site_id, valid_time=h.valid_time, lead_hour=h.lead_hour,
                    heights_m=[float(z) for z in h.heights_m], cn2=[_num(c) for c in h.cn2],
                ))
        if forecast_rows:
            session.execute(pg_insert(Forecast), forecast_rows)
            session.execute(pg_insert(Cn2Profile), profile_rows)
        n = len(forecast_rows)
        run = session.get(ModelRun, run_id, with_for_update=True)
        run.status = RunStatus.success
        run.finished_at = datetime.now(UTC)
        run.error = None
    return n


def map_frame_rows(grid, run_time: datetime, k) -> list[dict]:
    """MapFrame rows (without run_id) of a GridExtractor's computed frames, plus one row with
    lead_hour = RELIEF_LEAD holding the model orography (contour lines of the website map)."""
    from seeing_core.grid import RELIEF_LEAD, encode_relief

    g = grid.geometry
    common = dict(ny=g.ny, nx=g.nx, lat0=g.lat0, lon0=g.lon0, dlat=g.dlat, dlon=g.dlon, k_tke=k[0], k_cis=k[1], k_conv=k[2])
    rows = [
        dict(valid_time=run_time + timedelta(hours=step), lead_hour=step, data=data,
             extra=getattr(grid, "extras", {}).get(step), **common)
        for step, data in sorted(grid.frames.items())
    ]
    if rows and getattr(grid, "surface_h", None) is not None:
        rows.append(dict(valid_time=run_time, lead_hour=RELIEF_LEAD, data=encode_relief(grid.surface_h), extra=None, **common))
    return rows


def mark_failed(session_factory: sessionmaker, run_id: int, error: str) -> None:
    with session_factory.begin() as session:
        run = session.get(ModelRun, run_id)
        if run is not None:
            run.status = RunStatus.failed
            run.finished_at = datetime.now(UTC)
            run.error = error[:10000]


def apply_retention(session_factory: sessionmaker, retention_days: int, now: datetime | None = None) -> int:
    """Delete model runs (and, by cascade, their rows) older than `retention_days`."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    with session_factory.begin() as session:
        result = session.execute(delete(ModelRun).where(ModelRun.run_time < cutoff))
        return result.rowcount or 0
