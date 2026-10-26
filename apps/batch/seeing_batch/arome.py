"""AROME 0.025 cycle discovery and file-by-file download (meteofetch).

A full run of the 6 packages is ~15 GB (HP1 ~6 GB, HP2 ~4.3 GB, IP1 ~3.5 GB), far too much to
hold at once on Cloud Run's in-memory disk. Every file (one package x one lead-hour group, at
most ~0.8 GB) is therefore downloaded, read for all sites by `seeing_core.RunExtractor`, and
deleted, with one file downloaded ahead while the previous one is being read.

With a `GridExtractor` (global map), files are read by lead-hour group, so that every night lead
hour is computed and freed as soon as its packages are read. A map failure only disables the map.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
from meteofetch import Arome0025
from meteofetch._misc import are_downloadable

from seeing_core import ExtractedRun, RunExtractor, SiteSpec
from seeing_core.grid import GridExtractor, order_by_group

logger = logging.getLogger(__name__)

PACKAGES = ("SP2", "SP3", "HP1", "HP2", "IP1", "IP4")
# Every AROME 0.025 cycle (00, 03, ..., 21 UTC) is published up to H+51 (group 49H51H).
CYCLE_HOURS = Arome0025.freq_update


def _date_str(run_time: datetime) -> str:
    return f"{run_time:%Y-%m-%dT%H}"


def cycle_urls(run_time: datetime, package: str) -> list[str]:
    return Arome0025._get_urls(paquet=package, date=_date_str(run_time))


def cycle_complete(run_time: datetime, packages: Sequence[str] = PACKAGES) -> bool:
    """All files (all lead-hour groups up to 49H51H) of all packages are published."""
    return all(are_downloadable(cycle_urls(run_time, p)) for p in packages)


def latest_complete_cycle(packages: Sequence[str] = PACKAGES, max_back: int = Arome0025.past_runs_) -> datetime:
    """Most recent cycle whose packages are all published. Starts from meteofetch's latest
    available cycle for the slowest-checked package and steps back if another one is incomplete."""
    latest = Arome0025.get_latest_forecast_time(paquet=packages[0])
    if latest is None:
        raise RuntimeError("No AROME 0.025 cycle available")
    candidate = pd.Timestamp(latest).to_pydatetime().astimezone(UTC)
    for _ in range(max_back):
        if cycle_complete(candidate, packages):
            return candidate
        logger.info("AROME cycle %s incomplete, trying the previous one", candidate.isoformat())
        candidate -= timedelta(hours=CYCLE_HOURS)
    raise RuntimeError("No complete AROME 0.025 cycle found")


def _download(url: str, grib_dir: Path, num_retries: int) -> tuple[Path, float, int, bool]:
    """Download `url` into grib_dir (via a .part directory so that a file present in grib_dir is
    always complete). Reuses an existing complete file."""
    final = grib_dir / Path(url).name.replace(":", "-")
    if final.exists():
        return final, 0.0, final.stat().st_size, True
    part_dir = grib_dir / ".part"
    part_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    tmp = Arome0025._url_to_file(url, str(part_dir), num_retries=num_retries)
    if not tmp:
        raise RuntimeError(f"Download failed: {url}")
    os.replace(tmp, final)
    return final, time.monotonic() - t0, final.stat().st_size, False


def _cleanup(grib_dir: Path, pending: Future | None) -> None:
    """On failure: wait for the in-flight download and remove every GRIB file of grib_dir."""
    if pending is not None:
        try:
            pending.result()
        except Exception:
            pass
    for path in [*grib_dir.glob("arome__0025__*.grib2"), *(grib_dir / ".part").glob("*")]:
        path.unlink(missing_ok=True)


def download_and_extract(
    run_time: datetime,
    sites: Sequence[SiteSpec],
    grib_dir: Path,
    forecast_hours: int = 51,
    keep_gribs: bool = False,
    packages: Sequence[str] = PACKAGES,
    num_retries: int = 3,
    grid: GridExtractor | None = None,
) -> tuple[ExtractedRun, dict]:
    """Download every file of the cycle, extract the site point data (and the map fields when
    `grid` is given), delete the file. If the map fails, `grid.failed` is set and the run goes on."""
    grib_dir.mkdir(parents=True, exist_ok=True)
    extractor = RunExtractor(sites, forecast_hours)
    urls = [(p, u) for p in packages for u in cycle_urls(run_time, p)]
    if grid is not None:
        urls = order_by_group(urls)
    stats = {"files": 0, "bytes": 0, "download_s": 0.0, "extract_s": 0.0, "max_file_bytes": 0, "map_s": 0.0}

    with ThreadPoolExecutor(max_workers=1) as pool:
        # One download in flight while the previous file is read: at most 2 files on disk.
        pending: Future | None = pool.submit(_download, urls[0][1], grib_dir, num_retries)
        for i, (package, _url) in enumerate(urls):
            try:
                path, dl_s, size, reused = pending.result()
                pending = None
                if i + 1 < len(urls):
                    pending = pool.submit(_download, urls[i + 1][1], grib_dir, num_retries)
                t0 = time.monotonic()
                extractor.add_file(path, package)
                ex_s = time.monotonic() - t0
                if grid is not None and not grid.failed:
                    t1 = time.monotonic()
                    try:
                        grid.add_file(path, package)
                        grid.compute_ready()
                    except Exception:
                        logger.exception("Global map failed, run continues without it")
                        grid.failed = True
                        grid.frames.clear()
                    stats["map_s"] += time.monotonic() - t1
            except BaseException:
                if not keep_gribs:
                    _cleanup(grib_dir, pending)
                raise
            if not keep_gribs:
                path.unlink(missing_ok=True)
            stats["files"] += 1
            stats["bytes"] += size
            stats["download_s"] += dl_s
            stats["extract_s"] += ex_s
            stats["max_file_bytes"] = max(stats["max_file_bytes"], size)
            logger.info(
                "Processed %s", path.name,
                extra={"package": package, "size_mb": round(size / 1e6, 1), "download_s": round(dl_s, 1),
                       "extract_s": round(ex_s, 1), "reused": reused},
            )

    run = extractor.result()
    if run.run_time is not None and run.run_time != run_time:
        raise RuntimeError(f"GRIB cycle {run.run_time.isoformat()} != requested {run_time.isoformat()}")
    return run, stats
