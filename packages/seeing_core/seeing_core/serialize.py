"""Save / load an ExtractedRun as a compact .npz (test fixtures, debugging without GRIB files)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import numpy as np

from seeing_core.grib import ExtractedRun


def save_extracted(
    run: ExtractedRun,
    path: Path,
    slugs: Iterable[str] | None = None,
    hours: Iterable[int] | None = None,
) -> None:
    slugs = list(slugs) if slugs is not None else list(run.slugs)
    hours = set(hours) if hours is not None else None
    names: list[str] = []
    arrays: dict[str, np.ndarray] = {}
    for pkg, by_site in run.data.items():
        rows = []
        for si, slug in enumerate(slugs):
            for step, by_name in by_site.get(slug, {}).items():
                if hours is not None and step not in hours:
                    continue
                for name, by_level in by_name.items():
                    if name not in names:
                        names.append(name)
                    for level, value in by_level.items():
                        rows.append((si, step, names.index(name), level, value))
        rec = np.array(rows, dtype=float).reshape(-1, 5)
        arrays[f"pkg_{pkg}_idx"] = rec[:, :3].astype(np.int16)
        arrays[f"pkg_{pkg}_val"] = rec[:, 3:]  # level, value (float64: exact round trip)
    np.savez_compressed(
        path,
        slugs=np.array(slugs),
        names=np.array(names),
        run_time=np.array(run.run_time.isoformat() if run.run_time else ""),
        surface_h=np.array([run.surface_h.get(s, np.nan) for s in slugs]),
        grid_points=np.array([run.grid_points.get(s, (np.nan, np.nan)) for s in slugs]),
        **arrays,
    )


def load_extracted(path: Path) -> ExtractedRun:
    with np.load(path) as f:
        slugs = [str(s) for s in f["slugs"]]
        names = [str(s) for s in f["names"]]
        rt = str(f["run_time"])
        data: dict = {}
        for key in f.files:
            if not (key.startswith("pkg_") and key.endswith("_idx")):
                continue
            pkg = key[4:-4]
            by_site: dict = {slug: {} for slug in slugs}
            for (si, step, ni), (level, value) in zip(f[key], f[f"pkg_{pkg}_val"]):
                by_site[slugs[si]].setdefault(int(step), {}).setdefault(names[ni], {})[float(level)] = float(value)
            data[pkg] = by_site
        return ExtractedRun(
            run_time=datetime.fromisoformat(rt) if rt else None,
            slugs=slugs,
            data=data,
            surface_h={s: float(v) for s, v in zip(slugs, f["surface_h"])},
            grid_points={s: (float(a), float(b)) for s, (a, b) in zip(slugs, f["grid_points"])},
        )
