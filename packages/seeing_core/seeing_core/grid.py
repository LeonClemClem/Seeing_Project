"""Seeing map over the whole AROME 0.025 grid: the V2bd physics vectorised over columns.

The per-site pipeline handles one vertical profile at a time; here every grid column of a lead hour
is computed at once with 2-D arrays (columns x levels). The result is identical to compute_hour()
with model="V2bd" for the same column (tests/test_grid.py).

Memory: one lead hour of the needed fields is ~250 2-D fields. The grid is subsampled by `stride`
(2 -> 0.05 deg, ~200 000 columns, ~200 MB per lead hour) and a lead hour is computed and freed as
soon as all its packages have been read (files ordered by lead-hour group, see order_by_group).
"""

from __future__ import annotations

import logging
import zlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from eccodes import codes_get_array, codes_grib_new_from_file, codes_release

from seeing_core.constants import (
    ARCSEC,
    C_FC,
    CP_AIR,
    G,
    HAG_TOP_M,
    HEIGHTS,
    LAMBDA,
    P0_HPA,
    R_D,
    R_OVER_CP,
    SSHF_SIGN,
    V2BD_TRANSITION_M,
)
from seeing_core.grib import PACKAGES, REQUIRED_PACKAGES, _get, _message_step, parse_grib_filename

logger = logging.getLogger(__name__)

# K of the global map (one set for every grid point and every run, until the global calibration).
MAP_K = (2.0, 57.0, 0.1)  # K_TKE, K_CIS, K_conv
# Map hours: the night from 19h to 05h UTC (the map's night mean uses 20h-04h, the fisheye 19h-05h).
NIGHT_HOURS_UTC = (19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5)
DEFAULT_STRIDE = 2

# Fields: fields[(package, shortName, level)] = 2-D array (ny, nx)
Fields = dict[tuple[str, str, float], np.ndarray]


@dataclass(frozen=True)
class GridGeometry:
    """Subsampled grid: row r / column c is at (lat0 + r * dlat, lon0 + c * dlon)."""

    ny: int
    nx: int
    lat0: float
    lon0: float
    dlat: float
    dlon: float


def night_steps(run_time: datetime, forecast_hours: int = 51) -> list[int]:
    """Lead hours of the run whose valid time is a map hour (20h-04h UTC), from the night that starts
    on the day of the run (the map's first night, as on the website)."""
    first = run_time.replace(hour=NIGHT_HOURS_UTC[0], minute=0, second=0, microsecond=0)
    return [
        h for h in range(1, forecast_hours + 1)
        if (v := run_time + timedelta(hours=h)) >= first and v.hour in NIGHT_HOURS_UTC
    ]


def order_by_group(urls: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    """(package, url) pairs ordered by lead-hour group, then package: all the packages of a lead
    hour are read close together, so its map can be computed and freed early."""
    order = {p: i for i, p in enumerate(PACKAGES)}
    return sorted(urls, key=lambda pu: (parse_grib_filename(Path(pu[1]))[1], order.get(pu[0], 99)))


def _sshf_steps(steps: Iterable[int]) -> set[int]:
    out: set[int] = set()
    for s in steps:
        h = max(s, 1)
        out |= {h, h - 1}
    return out


class GridExtractor:
    """Keep the subsampled fields of the map lead hours, one GRIB file at a time.

    >>> grid = GridExtractor(night_steps(run_time), packages)
    >>> for path in files:
    ...     grid.add_file(path)
    ...     for step in grid.complete_steps():
    ...         frame = grid.compute(step)
    """

    def __init__(self, steps: Iterable[int], packages: Sequence[str] = (*REQUIRED_PACKAGES, "SP3"), stride: int = DEFAULT_STRIDE):
        self.steps = sorted(set(steps))
        self.packages = tuple(packages)
        self.stride = stride
        self.geometry: GridGeometry | None = None
        self.surface_h: np.ndarray | None = None
        self._fields: dict[int, Fields] = {}
        self._sshf: dict[int, np.ndarray] = {}
        self._covered: dict[str, set[int]] = {p: set() for p in self.packages}
        self._done: set[int] = set()
        # encoded seeing map (encode_seeing) of every computed lead hour
        self.frames: dict[int, bytes] = {}
        # encode_split() of every computed lead hour (fisheye)
        self.extras: dict[int, bytes] = {}
        self.failed = False

    def _geometry(self, gid) -> GridGeometry:
        ni, nj = int(_get(gid, "Ni")), int(_get(gid, "Nj"))
        lat_first = float(_get(gid, "latitudeOfFirstGridPointInDegrees"))
        lon_first = float(_get(gid, "longitudeOfFirstGridPointInDegrees"))
        di = float(_get(gid, "iDirectionIncrementInDegrees"))
        dj = float(_get(gid, "jDirectionIncrementInDegrees"))
        dlat = dj if int(_get(gid, "jScansPositively", 0)) else -dj
        dlon = -di if int(_get(gid, "iScansNegatively", 0)) else di
        s = self.stride
        lon_first = ((lon_first + 180.0) % 360.0) - 180.0
        return GridGeometry(ny=len(range(0, nj, s)), nx=len(range(0, ni, s)), lat0=lat_first, lon0=lon_first, dlat=dlat * s, dlon=dlon * s)

    def _values(self, gid) -> np.ndarray:
        ni, nj = int(_get(gid, "Ni")), int(_get(gid, "Nj"))
        values = np.asarray(codes_get_array(gid, "values"), dtype=np.float64).reshape(nj, ni)[:: self.stride, :: self.stride]
        out = values.astype(np.float32)
        if int(_get(gid, "bitmapPresent", 0)):
            out[values == float(_get(gid, "missingValue", 9999))] = np.nan
        return out

    def add_file(self, path: Path, package: str | None = None) -> None:
        path = Path(path)
        pkg, start, end = parse_grib_filename(path)
        package = package or pkg
        spec = PACKAGES[package]
        wanted = (_sshf_steps(self.steps) if package == "SP3" else set(self.steps)) & set(range(start, end + 1))
        want_h = package == "SP2" and self.surface_h is None
        if wanted or want_h:
            with open(path, "rb") as f:
                while True:
                    try:
                        gid = codes_grib_new_from_file(f)
                    except Exception as exc:
                        logger.warning("Premature end of GRIB file %s: %s", path.name, exc)
                        break
                    if gid is None:
                        break
                    try:
                        short_name = _get(gid, "shortName")
                        type_of_level = _get(gid, "typeOfLevel")
                        if self.geometry is None:
                            self.geometry = self._geometry(gid)
                        if want_h and short_name == "h" and type_of_level == "surface":
                            self.surface_h = self._values(gid)
                            want_h = False
                            continue
                        if short_name not in spec.variables or type_of_level not in spec.level_types:
                            continue
                        step = _message_step(gid)
                        if step not in wanted:
                            continue
                        level = _get(gid, "level")
                        level = 0.0 if level is None else float(level)
                        if package == "SP3":
                            self._sshf[step] = self._values(gid)
                        else:
                            self._fields.setdefault(step, {})[(package, short_name, level)] = self._values(gid)
                    finally:
                        codes_release(gid)
        if package in self._covered:
            self._covered[package] |= set(range(start, end + 1))

    def complete_steps(self) -> list[int]:
        """Map lead hours not computed yet whose packages have all been read."""
        out = []
        for s in self.steps:
            if s in self._done:
                continue
            need = {p: {s} for p in self.packages}
            if "SP3" in need:
                need["SP3"] = {max(s, 1), max(s, 1) - 1}
            if all(n <= self._covered[p] for p, n in need.items()):
                out.append(s)
        return out

    def compute_ready(self, k: tuple[float, float, float] = MAP_K) -> list[int]:
        """Compute (and free) every complete lead hour; the encoded maps go to self.frames and the
        low / high turbulence split to self.extras."""
        done = self.complete_steps()
        for s in done:
            integrals = self.compute(s)
            shape = np.asarray(self.surface_h).shape
            self.frames[s] = encode_seeing(seeing_from_integrals(integrals, k).reshape(shape))
            self.extras[s] = encode_split(integrals, k, shape)
        return done

    def compute(self, step: int) -> np.ndarray:
        """V2bd integrals and moments (npoints, 6) of one lead hour on the subsampled grid; frees its fields."""
        fields = self._fields.pop(step, {})
        self._done.add(step)
        if self.geometry is None or self.surface_h is None:
            raise RuntimeError("grid geometry or model orography SP2:h not read")
        h = max(step, 1)
        return map_integrals(fields, self._sshf.get(h), self._sshf.get(h - 1), self.surface_h)


# --- physics on columns -----------------------------------------------------------------------


def _field(fields: Fields, key: tuple[str, str, float], shape: tuple[int, ...]) -> np.ndarray:
    a = fields.get(key)
    return np.full(shape, np.nan) if a is None else np.asarray(a, dtype=np.float64).reshape(-1)


def _theta(T: np.ndarray, P: np.ndarray) -> np.ndarray:
    return T * (P0_HPA / P) ** R_OVER_CP


def _gradient(f: np.ndarray, z: np.ndarray, nv: np.ndarray) -> np.ndarray:
    """np.gradient(f, z) of every row restricted to its first nv[row] levels (NaN beyond)."""
    n, L = f.shape
    out = np.full((n, L), np.nan)
    if L < 2:
        return out
    with np.errstate(all="ignore"):
        hs = z[:, 1:-1] - z[:, :-2]
        hd = z[:, 2:] - z[:, 1:-1]
        out[:, 1:-1] = (hs**2 * f[:, 2:] + (hd**2 - hs**2) * f[:, 1:-1] - hd**2 * f[:, :-2]) / (hs * hd * (hd + hs))
        out[:, 0] = (f[:, 1] - f[:, 0]) / (z[:, 1] - z[:, 0])
        rows = np.arange(n)
        li = np.clip(nv - 1, 1, L - 1)
        out[rows, li] = (f[rows, li] - f[rows, li - 1]) / (z[rows, li] - z[rows, li - 1])
    out[np.arange(L)[None, :] >= nv[:, None]] = np.nan
    out[nv < 2] = np.nan
    return out


def _masciadri_tke(z, T, P, E, nv):
    theta = _theta(T, P)
    dth = _gradient(theta, z, nv)
    with np.errstate(all="ignore"):
        L = np.sqrt(2.0 * E / ((G / theta) * dth))
        ok = (
            np.isfinite(E) & np.isfinite(theta) & np.isfinite(dth) & (E > 0) & (dth > 0)
            & np.isfinite(L) & (L > 0) & np.isfinite(P) & np.isfinite(T) & (T > 0)
        )
        e = 2 * (1 - 2 * R_OVER_CP)
        c = 3.35e-6 * P**e * theta ** (-10 / 3) * dth ** (4 / 3) * E ** (2 / 3)
    return np.where(ok, c, np.nan)


def _shear(z, T, U, V, P, nv):
    theta = _theta(T, P)
    dth = _gradient(theta, z, nv)
    du = _gradient(U, z, nv)
    dv = _gradient(V, z, nv)
    with np.errstate(all="ignore"):
        E = du**2 + dv**2
        L = np.sqrt(2.0 * E / ((G / theta) * dth))
        ok = (
            np.isfinite(E) & np.isfinite(theta) & np.isfinite(dth) & (E > 0) & (dth > 0)
            & np.isfinite(L) & (L > 0) & np.isfinite(P) & np.isfinite(T) & (T > 0)
        )
        c = (80e-6 * P / (T * theta)) ** 2 * L ** (4.0 / 3.0) * dth**2
    return np.where(ok, c, 0.0)


def v2bd_integrals(
    z: np.ndarray, T: np.ndarray, U: np.ndarray, V: np.ndarray, P: np.ndarray, E: np.ndarray,
    h_coulim: np.ndarray, w_theta0: np.ndarray,
) -> np.ndarray:
    """(n, 6): integrals I_tke, I_conv, I_cis of the V2bd terms at K = 1, already weighted by the soft
    transition, so that  integral(Cn2 dz) = K_TKE * I_tke + K_conv * I_conv + K_CIS * I_cis, then their
    first moments in altitude Z_x = integral(z * term dz) (heights of the turbulence, for the fisheye).

    Rows are columns, levels sorted by altitude, NaN-padded at the end (z NaN beyond the last level).
    """
    n, L = z.shape
    nv = np.sum(np.isfinite(z), axis=1)
    idx = np.arange(L)[None, :]
    valid = idx < nv[:, None]
    zf = np.where(valid, z, np.take_along_axis(z, np.clip(nv - 1, 0, L - 1)[:, None], axis=1))
    h = h_coulim[:, None]

    tke_raw = _masciadri_tke(zf, T, P, E, nv)
    tke1 = np.nan_to_num(tke_raw, nan=0.0)

    # Convective closure: in the TKE holes below H_COULIM, when the surface heat flux heats.
    below = valid & (zf <= h)
    theta = _theta(T, P)
    theta0 = theta[:, :1]
    with np.errstate(all="ignore"):
        zp = np.clip(zf, 1.0, 0.1 * h)
        ct2 = C_FC * (G / theta0) ** (-2.0 / 3.0) * np.abs(w_theta0[:, None]) ** (4.0 / 3.0) * zp ** (-4.0 / 3.0)
        e = 2.0 * (1.0 - 2.0 * R_OVER_CP)
        conv = 3.35e-6 * (G / 2.0) ** (2.0 / 3.0) * P**e * theta ** (-4.0) * ct2
    conv_ok = (
        below & ~np.isfinite(tke_raw) & (np.isfinite(w_theta0) & (w_theta0 > 0))[:, None]
        & (zf > 0) & np.isfinite(h) & (h > 0) & np.isfinite(P) & np.isfinite(T) & (T > 0)
        & np.isfinite(theta0) & (theta0 > 0) & np.isfinite(conv)
    )
    conv1 = np.where(conv_ok, conv, 0.0)

    # V2b shear on the levels above H_COULIM only (a suffix of the valid levels), gradients on them.
    first = np.sum(below, axis=1)
    src = np.clip(first[:, None] + idx, 0, L - 1)
    nsub = nv - first
    sub_valid = idx < nsub[:, None]
    sub = [np.where(sub_valid, np.take_along_axis(a, src, axis=1), np.nan) for a in (zf, T, U, V, P)]
    sh_sub = np.where(sub_valid, _shear(*sub, nsub), 0.0)
    sh_sub[nsub < 2] = 0.0
    back = np.clip(idx - first[:, None], 0, L - 1)
    shear1 = np.where(valid & (idx >= first[:, None]), np.take_along_axis(sh_sub, back, axis=1), 0.0)

    w = 0.5 * (1.0 - np.tanh((zf - h) / V2BD_TRANSITION_M))
    terms = (w * tke1 * valid, w * conv1, (1.0 - w) * shear1)
    out = np.stack(
        [np.trapezoid(c, zf, axis=1) for c in terms] + [np.trapezoid(zf * c, zf, axis=1) for c in terms],
        axis=1,
    )
    out[(nv < 2) | ~np.isfinite(h_coulim)] = np.nan
    return out


def seeing_from_integrals(integrals: np.ndarray, k: tuple[float, float, float] = MAP_K) -> np.ndarray:
    """Seeing [arcsec] from v2bd_integrals() for K = (K_TKE, K_CIS, K_conv)."""
    J = k[0] * integrals[..., 0] + k[2] * integrals[..., 1] + k[1] * integrals[..., 2]
    with np.errstate(all="ignore"):
        r0 = (0.423 * (2.0 * np.pi / LAMBDA) ** 2 * J) ** (-3.0 / 5.0)
        s = 0.98 * LAMBDA / r0 * ARCSEC
    return np.where(np.isfinite(J) & (J > 0), s, np.nan)


def columns_from_fields(
    fields: Fields, sshf_now: np.ndarray | None, sshf_prev: np.ndarray | None, surface_h: np.ndarray,
    rows: slice | None = None,
) -> tuple[np.ndarray, ...]:
    """Column arrays (z, T, U, V, P, TKE, h_coulim, w_theta0) for the flattened grid points `rows`."""
    sel = slice(None) if rows is None else rows
    oro = np.asarray(surface_h, dtype=np.float64).reshape(-1)[sel]
    n = oro.size
    flat = {k: np.asarray(v).reshape(-1)[sel] for k, v in fields.items()}

    def f(key):
        return _field(flat, key, (n,))

    # HAG levels (HP1 / HP2)
    T_h = np.stack([f(("HP1", "t", z)) for z in HEIGHTS], axis=1)
    U_h = np.stack([f(("HP1", "u", z)) for z in HEIGHTS], axis=1)
    V_h = np.stack([f(("HP1", "v", z)) for z in HEIGHTS], axis=1)
    P_h = np.stack([f(("HP1", "pres", z)) for z in HEIGHTS], axis=1)
    E_h = np.stack([f(("HP2", "tke", z)) for z in HEIGHTS], axis=1)
    finite_p = P_h[np.isfinite(P_h)]
    if finite_p.size and np.median(finite_p) > 2000:
        P_h = P_h / 100.0
    z_h = np.broadcast_to(HEIGHTS, (n, HEIGHTS.size))

    # Isobaric levels (IP1 / IP4), metres AGL, only above the HAG grid
    levels = sorted({lev for (pkg, name, lev) in flat if pkg == "IP1" and name == "z"})
    if levels:
        z_i = np.stack([f(("IP1", "z", p)) for p in levels], axis=1) / G - oro[:, None]
        T_i = np.stack([f(("IP1", "t", p)) for p in levels], axis=1)
        U_i = np.stack([f(("IP1", "u", p)) for p in levels], axis=1)
        V_i = np.stack([f(("IP1", "v", p)) for p in levels], axis=1)
        E_i = np.stack([f(("IP4", "tke", p)) for p in levels], axis=1)
        P_i = np.broadcast_to(np.asarray(levels, dtype=np.float64), (n, len(levels)))
        ok = np.isfinite(z_i) & np.isfinite(T_i) & np.isfinite(U_i) & np.isfinite(V_i) & (z_i > HAG_TOP_M)
        z_i = np.where(ok, z_i, np.nan)
    else:
        z_i = T_i = U_i = V_i = E_i = P_i = np.empty((n, 0))

    z = np.concatenate([z_h, z_i], axis=1)
    order = np.argsort(z, axis=1, kind="stable")  # NaN last
    cols = [np.take_along_axis(np.concatenate([a, b], axis=1), order, axis=1)
            for a, b in ((z_h, z_i), (T_h, T_i), (U_h, U_i), (V_h, V_i), (P_h, P_i), (E_h, E_i))]

    h = np.full(n, np.nan)
    for name in ("blh", "h_coulim"):  # h_coulim has priority, as in get_h_coulim()
        a = f(("SP2", name, 0.0))
        h = np.where(np.isfinite(a), a, h)

    w_theta0 = np.full(n, np.nan)
    if sshf_now is not None and sshf_prev is not None:
        q = (np.asarray(sshf_now, np.float64).reshape(-1)[sel] - np.asarray(sshf_prev, np.float64).reshape(-1)[sel]) / 3600.0 * SSHF_SIGN
        T0, P0 = cols[1][:, 0], cols[4][:, 0]
        with np.errstate(all="ignore"):
            rho = (P0 * 100.0) / (R_D * T0)
            w_theta0 = np.where(np.isfinite(T0) & np.isfinite(P0) & (T0 > 0) & (P0 > 0), q / (rho * CP_AIR), np.nan)
    return (*cols, h, w_theta0)


def map_integrals(
    fields: Fields, sshf_now: np.ndarray | None, sshf_prev: np.ndarray | None, surface_h: np.ndarray,
    chunk: int = 20000,
) -> np.ndarray:
    """(npoints, 6) V2bd integrals and moments of every grid point, computed by chunks of columns."""
    n = np.asarray(surface_h).size
    out = np.full((n, 6), np.nan)
    for a in range(0, n, chunk):
        sl = slice(a, min(n, a + chunk))
        out[sl] = v2bd_integrals(*columns_from_fields(fields, sshf_now, sshf_prev, surface_h, sl))
    return out


def seeing_map(
    fields: Fields, sshf_now: np.ndarray | None, sshf_prev: np.ndarray | None, surface_h: np.ndarray,
    k: tuple[float, float, float] = MAP_K,
) -> np.ndarray:
    shape = np.asarray(surface_h).shape
    return seeing_from_integrals(map_integrals(fields, sshf_now, sshf_prev, surface_h), k).reshape(shape).astype(np.float32)


# --- storage encoding ---------------------------------------------------------------------------

# Seeing stored on one byte, log scale from SEE_MIN to SEE_MAX arcsec; 255 = no value.
SEE_MIN, SEE_MAX = 0.2, 10.0


def encode_seeing(seeing: np.ndarray) -> bytes:
    """uint8 log-scale codes of a seeing map, zlib-compressed."""
    s = np.asarray(seeing, dtype=np.float64)
    with np.errstate(all="ignore"):
        q = np.round((np.log(s) - np.log(SEE_MIN)) / (np.log(SEE_MAX) - np.log(SEE_MIN)) * 254.0)
    codes = np.where(np.isfinite(q), np.clip(q, 0, 254), 255).astype(np.uint8)
    return zlib.compress(codes.tobytes(), 6)


def decode_seeing(data: bytes, shape: tuple[int, int]) -> np.ndarray:
    codes = np.frombuffer(zlib.decompress(data), dtype=np.uint8).reshape(shape)
    s = np.exp(np.log(SEE_MIN) + codes / 254.0 * (np.log(SEE_MAX) - np.log(SEE_MIN)))
    return np.where(codes == 255, np.nan, s)


# Low / high turbulence split, one byte each (fisheye): share of the boundary-layer terms (TKE +
# convection) in the integral, J-weighted heights of the low and high parts.
H_LOW_STEP, H_HIGH_STEP = 20.0, 100.0  # m per code: low 0-5080 m, high 0-25 400 m


def split(integrals: np.ndarray, k: tuple[float, float, float] = MAP_K) -> tuple[np.ndarray, ...]:
    """(share of the low part, height of the low part [m], height of the high part [m]) for K."""
    i = np.asarray(integrals, dtype=np.float64)
    with np.errstate(all="ignore"):
        j_low = k[0] * i[..., 0] + k[2] * i[..., 1]
        j_high = k[1] * i[..., 2]
        share = j_low / (j_low + j_high)
        h_low = (k[0] * i[..., 3] + k[2] * i[..., 4]) / j_low
        h_high = i[..., 5] / i[..., 2]
    return share, h_low, h_high


def encode_split(integrals: np.ndarray, k: tuple[float, float, float], shape: tuple[int, ...]) -> bytes:
    share, h_low, h_high = split(integrals, k)

    def code(v, scale, top=254):
        q = np.round(np.asarray(v) * scale)
        return np.where(np.isfinite(q), np.clip(q, 0, top), 255).astype(np.uint8).reshape(shape)

    planes = [code(share, 254.0), code(h_low, 1 / H_LOW_STEP), code(h_high, 1 / H_HIGH_STEP)]
    return zlib.compress(np.concatenate([a.reshape(-1) for a in planes]).tobytes(), 6)


def decode_split(data: bytes, shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    a = np.frombuffer(zlib.decompress(data), dtype=np.uint8).reshape(3, *shape).astype(np.float64)
    bad = a == 255
    a[bad] = np.nan
    return a[0] / 254.0, a[1] * H_LOW_STEP, a[2] * H_HIGH_STEP
