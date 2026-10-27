"""GRIB2 reading with ecCodes: extract the point values of every site in a single pass.

Each GRIB message is decoded once and the values at the nearest grid point of every site are
picked from it. Nearest grid indices are computed once per grid geometry (all AROME 0.025
packages share the same grid, so in practice once per run).

The result of the extraction is an `ExtractedRun`: tiny per-site dictionaries
``data[package][slug][step][shortName][level] = value``, i.e. the same structure as
``read_grib_package`` in the V2 research script, which the physics pipeline consumes.
GRIB files can be deleted as soon as they have been passed to `RunExtractor.add_file`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from eccodes import codes_get, codes_get_array, codes_grib_new_from_file, codes_release

logger = logging.getLogger(__name__)

DEFAULT_LEVEL_TYPES = frozenset({"heightAboveGround", "isobaricInhPa", "surface"})


@dataclass(frozen=True)
class PackageSpec:
    variables: frozenset[str]
    level_types: frozenset[str] = DEFAULT_LEVEL_TYPES


# What is read from each AROME 0.025 package (identical to the V2 script).
#   HP1: T, U, V, P on heightAboveGround levels 10-3000 m (+ 10 m wind 10u / 10v, model variables only)
#   HP2: TKE on heightAboveGround levels
#   IP1: T, U, V, Z on isobaric levels 1000-100 hPa (above 3000 m AGL)
#   IP4: TKE on the same isobaric levels (TKE model above 3000 m when H_COULIM > 3000 m)
#   SP2: H_COULIM (boundary-layer height) + h (model orography, read separately)
#   SP3: sshf (accumulated sensible heat flux, convective closure)
PACKAGES: dict[str, PackageSpec] = {
    # 10u / 10v (10 m wind) only feed the model variables, not the seeing physics.
    "HP1": PackageSpec(frozenset({"t", "u", "v", "pres", "10u", "10v"})),
    "HP2": PackageSpec(frozenset({"tke"})),
    "IP1": PackageSpec(frozenset({"t", "u", "v", "z"}), frozenset({"isobaricInhPa"})),
    "IP4": PackageSpec(frozenset({"tke"}), frozenset({"isobaricInhPa"})),
    "SP2": PackageSpec(frozenset({"blh", "h_coulim"}), frozenset({"surface"})),
    "SP3": PackageSpec(frozenset({"sshf"})),
}
REQUIRED_PACKAGES = ("HP1", "HP2", "IP1", "IP4", "SP2")
OPTIONAL_PACKAGES = ("SP3",)

_FILE_RE = re.compile(r"arome__0025__(?P<pkg>[A-Z]+\d)__(?P<start>\d{2})H(?P<end>\d{2})H__")

# data[step][shortName][level] = value
SitePoints = dict[int, dict[str, dict[float, float]]]


def parse_grib_filename(path: Path) -> tuple[str, int, int]:
    """`arome__0025__HP1__07H12H__2026-10-13T00-00-00Z.grib2` -> ("HP1", 7, 12)."""
    match = _FILE_RE.search(Path(path).name)
    if not match:
        raise ValueError(f"Not an AROME 0.025 package file name: {Path(path).name}")
    return match["pkg"], int(match["start"]), int(match["end"])


def find_grib_files(grib_dir: Path) -> dict[str, list[Path]]:
    """AROME files of `grib_dir`, grouped by package and sorted by forecast range."""
    out: dict[str, list[Path]] = {}
    for path in sorted(Path(grib_dir).glob("arome__0025__*.grib2")):
        try:
            pkg, start, _ = parse_grib_filename(path)
        except ValueError:
            continue
        out.setdefault(pkg, []).append(path)
    for files in out.values():
        files.sort(key=lambda p: parse_grib_filename(p)[1])
    return out


def _get(gid, key, default=None):
    try:
        return codes_get(gid, key)
    except Exception:
        return default


def _message_step(gid) -> int | None:
    for key in ("step", "endStep", "forecastTime"):
        value = _get(gid, key, None)
        if value is not None:
            try:
                return int(round(float(value)))
            except Exception:
                pass
    return None


def _message_cycle(gid) -> datetime | None:
    data_date = _get(gid, "dataDate", None)
    data_time = _get(gid, "dataTime", None)
    if data_date is None or data_time is None:
        return None
    time_int = int(round(float(data_time)))
    return datetime.strptime(
        f"{int(data_date)} {time_int // 100:02d}{time_int % 100:02d}", "%Y%m%d %H%M"
    ).replace(tzinfo=UTC)


_GEOMETRY_KEYS = (
    "gridType", "Ni", "Nj",
    "latitudeOfFirstGridPointInDegrees", "longitudeOfFirstGridPointInDegrees",
    "latitudeOfLastGridPointInDegrees", "longitudeOfLastGridPointInDegrees",
)


@dataclass
class _NearestIndex:
    lats: np.ndarray  # (n_sites,)
    lons: np.ndarray
    _cache: dict[tuple, tuple[np.ndarray, np.ndarray, np.ndarray]] = field(default_factory=dict)

    def get(self, gid) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(indices, grid_lats, grid_lons) of the nearest grid point of every site."""
        key = tuple(_get(gid, k) for k in _GEOMETRY_KEYS)
        if key not in self._cache:
            lats = np.asarray(codes_get_array(gid, "latitudes"), dtype=float)
            lons = np.asarray(codes_get_array(gid, "longitudes"), dtype=float)
            lons_norm = ((lons + 180.0) % 360.0) - 180.0
            idx = np.empty(len(self.lats), dtype=np.int64)
            for i, (lat, lon) in enumerate(zip(self.lats, self.lons)):
                target_lon = ((lon + 180.0) % 360.0) - 180.0
                dist2 = (lats - lat) ** 2 + (lons_norm - target_lon) ** 2
                idx[i] = int(np.nanargmin(dist2))
            self._cache[key] = (idx, lats[idx], lons_norm[idx])
        return self._cache[key]


@dataclass
class ExtractedRun:
    """Per-site point data of one AROME run (everything the physics needs, a few hundred kB)."""

    run_time: datetime | None
    slugs: list[str]
    # data[package][slug] -> SitePoints
    data: dict[str, dict[str, SitePoints]]
    # Model orography SP2:h [m] per site.
    surface_h: dict[str, float]
    # Nearest grid point (lat, lon) per site.
    grid_points: dict[str, tuple[float, float]]


class RunExtractor:
    """Accumulate site point values from AROME files, one file at a time.

    >>> ex = RunExtractor(sites)
    >>> for path in files: ex.add_file(path); path.unlink()
    >>> run = ex.result()
    """

    def __init__(self, sites: Sequence, forecast_hours: int = 51):
        self.slugs = [s.slug for s in sites]
        if len(set(self.slugs)) != len(self.slugs):
            raise ValueError("Duplicate site slugs")
        self.forecast_hours = forecast_hours
        self._nearest = _NearestIndex(
            np.array([s.lat for s in sites], dtype=float), np.array([s.lon for s in sites], dtype=float)
        )
        self._data: dict[str, dict[str, SitePoints]] = {}
        self._surface_h: dict[str, float] = {}
        self._surface_h_start: int | None = None
        self._grid_points: dict[str, tuple[float, float]] = {}
        self.run_time: datetime | None = None

    def _check_cycle(self, cycle: datetime | None, path: Path) -> None:
        if cycle is None:
            return
        if self.run_time is None:
            self.run_time = cycle
        elif cycle != self.run_time:
            raise ValueError(f"{path.name} belongs to cycle {cycle:%Y-%m-%dT%H:%MZ}, expected {self.run_time:%Y-%m-%dT%H:%MZ}")

    def add_file(self, path: Path, package: str | None = None) -> None:
        """Read one GRIB file. Only steps inside the file's forecast range (from its name) are kept,
        which reproduces the V2 hour -> file mapping."""
        path = Path(path)
        pkg, start, end = parse_grib_filename(path)
        package = package or pkg
        spec = PACKAGES[package]
        lo, hi = max(0, start), min(self.forecast_hours, end)
        # SP2:h is static; V2 reads it from the first SP2 file (sorted by range).
        want_h = package == "SP2" and (self._surface_h_start is None or start < self._surface_h_start)
        pkg_data = self._data.setdefault(package, {slug: {} for slug in self.slugs})
        found_steps: set[int] = set()
        n_messages = 0

        with open(path, "rb") as f:
            while True:
                try:
                    gid = codes_grib_new_from_file(f)
                except Exception as exc:
                    # Truncated download: keep the valid messages already read.
                    logger.warning("Premature end of GRIB file %s (message ~%d): %s", path.name, n_messages + 1, exc)
                    break
                if gid is None:
                    break
                n_messages += 1
                try:
                    if n_messages == 1:
                        self._check_cycle(_message_cycle(gid), path)
                    short_name = _get(gid, "shortName")
                    type_of_level = _get(gid, "typeOfLevel")
                    level = _get(gid, "level")

                    if want_h and short_name == "h" and type_of_level == "surface" and (
                        level is None or float(level) == 0.0
                    ):
                        idx, glat, glon = self._nearest.get(gid)
                        values = np.asarray(codes_get_array(gid, "values"), dtype=float)
                        for i, slug in enumerate(self.slugs):
                            self._surface_h[slug] = float(values[idx[i]])
                        self._surface_h_start = start
                        want_h = False
                        continue

                    if short_name not in spec.variables or type_of_level not in spec.level_types:
                        continue
                    step = _message_step(gid)
                    if step is None:
                        continue
                    found_steps.add(step)
                    if not lo <= step <= hi:
                        continue
                    level = 0.0 if level is None else float(level)

                    idx, glat, glon = self._nearest.get(gid)
                    values = np.asarray(codes_get_array(gid, "values"), dtype=float)
                    picked = values[idx]
                    for i, slug in enumerate(self.slugs):
                        pkg_data[slug].setdefault(step, {}).setdefault(short_name, {})[level] = float(picked[i])
                        if slug not in self._grid_points:
                            self._grid_points[slug] = (float(glat[i]), float(glon[i]))
                finally:
                    codes_release(gid)

        if not found_steps:
            logger.warning("No usable message in %s (empty or corrupted file?)", path.name)
        else:
            logger.debug("%s: steps %s", path.name, sorted(found_steps))

    def add_files(self, paths: Iterable[Path]) -> None:
        for path in paths:
            self.add_file(path)

    def result(self) -> ExtractedRun:
        return ExtractedRun(
            run_time=self.run_time,
            slugs=list(self.slugs),
            data=self._data,
            surface_h=dict(self._surface_h),
            grid_points=dict(self._grid_points),
        )


def extract_dir(grib_dir: Path, sites: Sequence, forecast_hours: int = 51) -> ExtractedRun:
    """Extract all AROME package files found in `grib_dir`."""
    files = find_grib_files(grib_dir)
    ex = RunExtractor(sites, forecast_hours)
    for package in (*REQUIRED_PACKAGES, *OPTIONAL_PACKAGES):
        if package not in files:
            if package in REQUIRED_PACKAGES:
                logger.warning("No %s file in %s", package, grib_dir)
            else:
                logger.warning("No %s file in %s: convective closure disabled", package, grib_dir)
            continue
        ex.add_files(files[package])
    return ex.result()
