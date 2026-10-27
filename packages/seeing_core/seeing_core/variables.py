"""Model variables shown next to the seeing (website "Variables du modèle"), from the same profiles."""

from __future__ import annotations

import numpy as np

from seeing_core.cn2 import potential_temperature
from seeing_core.profiles import Profile

# Altitude band of the jet-stream shear [m AGL].
JET_BAND_M = (6000.0, 14000.0)


def _at(p: Profile, key: str, z: float) -> float:
    """Value of `key` at height z (HAG levels: exact level, NaN if absent)."""
    i = np.flatnonzero(np.isclose(p["z"], z))
    return float(p[key][i[0]]) if i.size else np.nan


def model_variables(hag: Profile, full: Profile, wind10: tuple[float, float] | None = None) -> dict[str, float]:
    """t2 [deg C] (10 m), dth [K/100 m] (10-100 m), u10/u100/u500 [km/h], shl [m/s/km] (10-500 m),
    shj [m/s/km] (max shear between consecutive levels in JET_BAND_M), tke [m2/s2] (10 m)."""
    out: dict[str, float] = {}
    if wind10 is not None and np.all(np.isfinite(wind10)) and not np.isfinite(_at(hag, "U", 10.0)):
        hag = {k: np.array(v, dtype=float, copy=True) for k, v in hag.items()}  # 10 m wind from 10u / 10v
        i = np.flatnonzero(np.isclose(hag["z"], 10.0))
        if i.size:
            hag["U"][i[0]], hag["V"][i[0]] = wind10
    t10 = _at(hag, "T", 10.0)
    out["t2"] = t10 - 273.15
    th10 = potential_temperature(t10, _at(hag, "P", 10.0))
    th100 = potential_temperature(_at(hag, "T", 100.0), _at(hag, "P", 100.0))
    out["dth"] = (th100 - th10) / 90.0 * 100.0
    for z in (10.0, 100.0, 500.0):
        out[f"u{int(z)}"] = float(np.hypot(_at(hag, "U", z), _at(hag, "V", z)) * 3.6)
    du = _at(hag, "U", 500.0) - _at(hag, "U", 10.0)
    dv = _at(hag, "V", 500.0) - _at(hag, "V", 10.0)
    out["shl"] = float(np.hypot(du, dv) / 0.49)
    z, U, V = (np.asarray(full[k], dtype=float) for k in ("z", "U", "V"))
    band = (z >= JET_BAND_M[0]) & (z <= JET_BAND_M[1])
    idx = np.flatnonzero(band)
    if idx.size >= 2:
        dz = np.diff(z[idx])
        s = np.hypot(np.diff(U[idx]), np.diff(V[idx])) / dz * 1000.0
        out["shj"] = float(np.nanmax(s)) if np.any(np.isfinite(s)) else np.nan
    else:
        out["shj"] = np.nan
    out["tke"] = _at(hag, "TKE", 10.0)
    return {k: (float(v) if np.isfinite(v) else None) for k, v in out.items()}
