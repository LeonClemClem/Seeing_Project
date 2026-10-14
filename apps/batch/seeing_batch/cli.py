"""`seeing-batch run [--run-time ISO] [--keep-gribs]`"""

from __future__ import annotations

import argparse
import logging
import os
import resource
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from seeing_core import compute_from_extracted
from seeing_db import RunStatus, make_engine, make_session_factory
from sqlalchemy.orm import sessionmaker

from seeing_batch import persist
from seeing_batch.logs import setup_logging

logger = logging.getLogger("seeing_batch")


def parse_run_time(value: str) -> datetime:
    """ISO 8601 (`2026-10-13T00:00Z`, `2026-10-13T00`, ...) -> tz-aware UTC datetime."""
    v = value.strip()
    if v.endswith(("Z", "z")):
        v = v[:-1] + "+00:00"
    dt = datetime.fromisoformat(v)
    dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    if dt.minute or dt.second or dt.microsecond or dt.hour % 3:
        raise argparse.ArgumentTypeError(f"not an AROME cycle (00, 03, ..., 21 UTC): {value}")
    return dt


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def run_batch(
    session_factory: sessionmaker,
    run_time: datetime | None = None,
    keep_gribs: bool = False,
    grib_dir: Path | None = None,
    forecast_hours: int | None = None,
    retention_days: int | None = None,
    find_cycle=None,
    fetch=None,
) -> int:
    """Whole job; returns the process exit code. `find_cycle` / `fetch` are injectable for tests."""
    from seeing_batch import arome

    grib_dir = grib_dir or Path(os.environ.get("GRIB_DIR", "/tmp/arome"))
    forecast_hours = forecast_hours if forecast_hours is not None else int(os.environ.get("FORECAST_HOURS", "51"))
    retention_days = retention_days if retention_days is not None else int(os.environ.get("RETENTION_DAYS", "14"))
    find_cycle = find_cycle or arome.latest_complete_cycle
    fetch = fetch or arome.download_and_extract

    if run_time is None:
        run_time = find_cycle()
    rt = run_time.isoformat().replace("+00:00", "Z")
    logger.info("AROME cycle %s", rt, extra={"run_time": rt})

    with session_factory() as session:
        status = persist.run_status(session, run_time)
        site_rows = persist.load_sites(session)
    if status == RunStatus.success:
        logger.info("Run %s already stored with success, nothing to do", rt, extra={"run_time": rt})
        return 0
    if not site_rows:
        logger.error("No active site in the database")
        return 1

    run_id = persist.start_run(session_factory, run_time)
    t_start = time.monotonic()
    try:
        sites = [spec for _, spec in site_rows]
        extracted, stats = fetch(run_time, sites, grib_dir, forecast_hours=forecast_hours, keep_gribs=keep_gribs)
        t0 = time.monotonic()
        forecasts = compute_from_extracted(extracted, sites, forecast_hours)
        compute_s = time.monotonic() - t0
        if not any(fc.hours for fc in forecasts.values()):
            raise RuntimeError("No lead hour could be computed for any site")
        n = persist.store_results(session_factory, run_id, forecasts, {spec.slug: sid for sid, spec in site_rows})
    except Exception as exc:
        logger.exception("Run %s failed", rt, extra={"run_time": rt})
        persist.mark_failed(session_factory, run_id, f"{type(exc).__name__}: {exc}")
        return 1

    logger.info(
        "Run %s stored: %d forecast rows", rt, n,
        extra={
            "run_time": rt, "sites": len(site_rows), "rows": n,
            "total_s": round(time.monotonic() - t_start, 1), "compute_s": round(compute_s, 2),
            "download_gb": round(stats.get("bytes", 0) / 1e9, 2),
            "download_s": round(stats.get("download_s", 0.0), 1),
            "extract_s": round(stats.get("extract_s", 0.0), 1),
            "max_file_mb": round(stats.get("max_file_bytes", 0) / 1e6, 1),
            "peak_rss_mb": round(_peak_rss_mb(), 1),
        },
    )
    deleted = persist.apply_retention(session_factory, retention_days)
    if deleted:
        logger.info("Retention: deleted %d run(s) older than %d days", deleted, retention_days)
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="seeing-batch", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Download an AROME run, compute all active sites, store the forecasts.")
    run.add_argument("--run-time", type=parse_run_time, default=None,
                     help="AROME cycle, ISO 8601 UTC (e.g. 2026-10-13T00:00Z). Default: latest complete cycle.")
    run.add_argument("--keep-gribs", action="store_true", help="Keep the downloaded GRIB files in GRIB_DIR.")
    args = parser.parse_args(argv)

    setup_logging(os.environ.get("LOG_LEVEL", "INFO"))
    engine = make_engine()
    try:
        code = run_batch(make_session_factory(engine), run_time=args.run_time, keep_gribs=args.keep_gribs)
    except Exception:
        logger.exception("seeing-batch failed")
        code = 1
    finally:
        engine.dispose()
    sys.exit(code)


if __name__ == "__main__":
    main()
