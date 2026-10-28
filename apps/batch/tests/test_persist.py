from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy import func, select

from seeing_batch import persist
from seeing_batch.cli import parse_run_time, run_batch
from seeing_core import ExtractedRun, HourResult, SiteForecast
from seeing_db import Cn2Profile, Forecast, ModelRun, RunStatus, Site

RUN = datetime(2026, 10, 13, 0, tzinfo=UTC)


def fake_forecasts(sites, run_time=RUN, n_hours=3, seeing=1.0):
    out = {}
    for spec in sites:
        hours = []
        for h in range(n_hours):
            heights = np.arange(10.0, 510.0, 100.0)
            cn2 = np.array([1e-15, np.nan, 3e-16, 2e-17, np.nan])
            hours.append(HourResult(
                lead_hour=h, valid_time=run_time + timedelta(hours=h),
                seeing_arcsec=seeing + h if h != 1 else np.nan, r0_m=0.1, integral_cn2=1e-13,
                h_coulim_m=800.0, model_altitude_m=1234.5, heights_m=heights, cn2=cn2,
            ))
        out[spec.slug] = SiteForecast(slug=spec.slug, run_time=run_time, hours=hours)
    return out


def count(session_factory, model, **where):
    with session_factory() as s:
        q = select(func.count()).select_from(model)
        for k, v in where.items():
            q = q.where(getattr(model, k) == v)
        return s.scalar(q)


def test_load_sites_uses_db_coefficients(db):
    with db() as s:
        sites = dict((spec.slug, spec) for _, spec in persist.load_sites(s))
    assert {"copernic-gap", "saint-veran", "verclause", "cosmodrome", "pic-du-midi"} <= set(sites)
    # calibrated V2bd K of migration 0006
    assert sites["verclause"].k_tke == 3.94 and sites["verclause"].k_cis == 49.7 and sites["verclause"].k_tke_conv == 0.1


def test_store_replace_and_nan_to_null(db):
    with db() as s:
        site_rows = persist.load_sites(s)
    sites = [spec for _, spec in site_rows]
    ids = {spec.slug: sid for sid, spec in site_rows}

    run_id = persist.start_run(db, RUN)
    n = persist.store_results(db, run_id, fake_forecasts(sites, n_hours=3), ids)
    assert n == 3 * len(sites)
    with db() as s:
        run = s.get(ModelRun, run_id)
        assert run.status == RunStatus.success and run.finished_at is not None
        f1 = s.scalars(select(Forecast).where(Forecast.lead_hour == 1)).first()
        assert f1.seeing_arcsec is None and f1.r0_m == pytest.approx(0.1)
        prof = s.scalars(select(Cn2Profile)).first()
        assert prof.cn2[1] is None and prof.cn2[0] == pytest.approx(1e-15, rel=1e-6)
        assert prof.heights_m[:2] == [10.0, 110.0]

    # Re-running the same run_time replaces its rows (idempotent).
    run_id2 = persist.start_run(db, RUN)
    assert run_id2 == run_id
    with db() as s:
        assert s.get(ModelRun, run_id).status == RunStatus.running
    persist.store_results(db, run_id, fake_forecasts(sites, n_hours=2, seeing=2.0), ids)
    assert count(db, Forecast, run_id=run_id) == 2 * len(sites)
    assert count(db, Cn2Profile, run_id=run_id) == 2 * len(sites)
    assert count(db, ModelRun) == 1


def test_mark_failed(db):
    run_id = persist.start_run(db, RUN)
    persist.mark_failed(db, run_id, "boom")
    with db() as s:
        run = s.get(ModelRun, run_id)
        assert run.status == RunStatus.failed and run.error == "boom" and run.finished_at


def test_retention_cascades(db):
    with db() as s:
        site_rows = persist.load_sites(s)
    sites = [spec for _, spec in site_rows]
    ids = {spec.slug: sid for sid, spec in site_rows}
    now = datetime(2026, 10, 30, tzinfo=UTC)
    old = persist.start_run(db, now - timedelta(days=20))
    persist.store_results(db, old, fake_forecasts(sites, run_time=now - timedelta(days=20)), ids)
    new = persist.start_run(db, now - timedelta(days=1))
    persist.store_results(db, new, fake_forecasts(sites, run_time=now - timedelta(days=1)), ids)

    assert persist.apply_retention(db, 14, now=now) == 1
    assert count(db, ModelRun) == 1
    assert count(db, Forecast, run_id=old) == 0
    assert count(db, Cn2Profile, run_id=old) == 0
    assert count(db, Forecast, run_id=new) > 0


def _fake_fetch(calls):
    def fetch(run_time, sites, grib_dir, forecast_hours, keep_gribs, grid=None):
        calls.append(run_time)
        if grid is not None:  # two fake map frames on a 2 x 3 grid
            from seeing_core.grid import GridGeometry, encode_seeing

            grid.geometry = GridGeometry(ny=2, nx=3, lat0=51.0, lon0=-5.0, dlat=-0.05, dlon=0.05)
            grid.frames = {s: encode_seeing(np.full((2, 3), 1.0 + s / 10)) for s in grid.steps[:2]}
        return ExtractedRun(run_time=run_time, slugs=[s.slug for s in sites], data={}, surface_h={}, grid_points={}), {}
    return fetch


def test_run_batch_success_then_idempotent(db, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("seeing_batch.cli.compute_from_extracted",
                        lambda run, sites, fh: fake_forecasts(sites, run_time=run.run_time))
    kw = dict(grib_dir=tmp_path, find_cycle=lambda: RUN, fetch=_fake_fetch(calls), retention_days=10**5)

    assert run_batch(db, **kw) == 0
    assert calls == [RUN]
    with db() as s:
        assert s.scalar(select(ModelRun.status)) == RunStatus.success
        n_sites = s.scalar(select(func.count()).select_from(Site).where(Site.active.is_(True)))
    assert count(db, Forecast) == 3 * n_sites

    # Already stored with success: cheap exit 0, nothing downloaded.
    assert run_batch(db, **kw) == 0
    assert calls == [RUN]
    # --force: recomputed and replaced (no duplicate rows)
    assert run_batch(db, **kw, force=True) == 0
    assert calls == [RUN, RUN]
    assert count(db, Forecast) == 3 * n_sites


def test_run_batch_failure_marks_failed(db, tmp_path):
    def fetch(*a, **k):
        raise RuntimeError("download exploded")

    assert run_batch(db, run_time=RUN, grib_dir=tmp_path, fetch=fetch) == 1
    with db() as s:
        run = s.scalars(select(ModelRun)).one()
        assert run.status == RunStatus.failed and "download exploded" in run.error

    # A failed run is retried on the next invocation.
    calls = []
    import seeing_batch.cli as cli

    orig = cli.compute_from_extracted
    cli.compute_from_extracted = lambda run, sites, fh: fake_forecasts(sites)
    try:
        assert run_batch(db, run_time=RUN, grib_dir=tmp_path, fetch=_fake_fetch(calls), retention_days=10**5) == 0
    finally:
        cli.compute_from_extracted = orig
    with db() as s:
        run = s.scalars(select(ModelRun)).one()
        assert run.status == RunStatus.success and run.error is None


def test_run_batch_no_hours_is_failure(db, monkeypatch, tmp_path):
    monkeypatch.setattr("seeing_batch.cli.compute_from_extracted",
                        lambda run, sites, fh: fake_forecasts(sites, n_hours=0))
    assert run_batch(db, run_time=RUN, grib_dir=tmp_path, fetch=_fake_fetch([]), retention_days=10**5) == 1


def test_parse_run_time():
    assert parse_run_time("2026-10-13T00:00Z") == RUN
    assert parse_run_time("2026-10-13T02:00+02:00") == RUN
    assert parse_run_time("2026-10-13T03") == RUN + timedelta(hours=3)
    with pytest.raises(Exception):
        parse_run_time("2026-10-13T04:00Z")


def test_run_batch_stores_map_frames(db, monkeypatch, tmp_path):
    from seeing_db import MapFrame

    monkeypatch.setattr("seeing_batch.cli.compute_from_extracted",
                        lambda run, sites, fh: fake_forecasts(sites, run_time=run.run_time))
    assert run_batch(db, run_time=RUN, grib_dir=tmp_path, fetch=_fake_fetch([]), map_enabled=True,
                     retention_days=10**5) == 0
    with db() as s:
        frames = s.scalars(select(MapFrame).order_by(MapFrame.lead_hour)).all()
        assert [f.lead_hour for f in frames] == [19, 20]
        assert (frames[0].ny, frames[0].nx, frames[0].k_tke, frames[0].k_cis) == (2, 3, 2.0, 35.0)
        assert frames[0].valid_time == RUN + timedelta(hours=19)


def test_store_cells(db):
    from seeing_core.grid import GridGeometry

    class Grid:
        geometry_full = GridGeometry(ny=400, nx=400, lat0=48.0, lon0=3.0, dlat=-0.025, dlon=0.025)
        surface_h_full = np.full((400, 400), 1234.0)

    with db() as s:
        rows = persist.load_sites(s)
    n = persist.store_cells(db, Grid(), rows)
    assert n >= 1
    with db() as s:
        site = s.scalar(select(Site).where(Site.slug == "ohp"))
        assert site.cells["alt"][2][2] == 1234 and len(site.cells["alt"]) == 5
