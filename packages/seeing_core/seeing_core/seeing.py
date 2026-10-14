"""Integration of the Cn2 profile into r0 / seeing, and projection onto the display grid."""

from __future__ import annotations

import numpy as np

from seeing_core.constants import ARCSEC, DISPLAY_DZ, DISPLAY_Z0, LAMBDA


def integrate_seeing(z: np.ndarray, cn2: np.ndarray) -> tuple[float, float, float]:
    """(integral of Cn2 dz [m^1/3], Fried parameter r0 [m], seeing [arcsec]) at LAMBDA.

    Trapezoidal integration on the native levels (no interpolation), NaN levels skipped.
    """
    z = np.asarray(z, dtype=float)
    cn2 = np.asarray(cn2, dtype=float)
    valid = np.isfinite(z) & np.isfinite(cn2) & (cn2 >= 0)
    if np.count_nonzero(valid) < 2:
        return np.nan, np.nan, np.nan

    zv = z[valid]
    cv = cn2[valid]
    order = np.argsort(zv)
    zv = zv[order]
    cv = cv[order]

    integral = np.trapezoid(cv, zv)
    if not np.isfinite(integral) or integral <= 0:
        return float(integral), np.nan, np.nan

    r0 = (0.423 * (2.0 * np.pi / LAMBDA) ** 2 * integral) ** (-3.0 / 5.0)
    seeing = 0.98 * LAMBDA / r0 * ARCSEC
    return float(integral), float(r0), float(seeing)


def interp_on_grid(z_target: np.ndarray, z_source: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Linear interpolation of a sorted profile, ignoring NaN source points; NaN outside."""
    z_source = np.asarray(z_source, dtype=float)
    values = np.asarray(values, dtype=float)
    valid = np.isfinite(z_source) & np.isfinite(values)
    out = np.full_like(z_target, np.nan, dtype=float)
    if np.count_nonzero(valid) < 2:
        return out
    target_valid = np.isfinite(z_target)
    out[target_valid] = np.interp(z_target[target_valid], z_source[valid], values[valid], left=np.nan, right=np.nan)
    return out


def display_grid(z_top: float) -> np.ndarray:
    """Regular grid DISPLAY_Z0, DISPLAY_Z0 + 100, ... covering the profile up to `z_top`."""
    if not np.isfinite(z_top):
        return np.empty(0)
    return np.arange(DISPLAY_Z0, np.ceil(z_top / DISPLAY_DZ) * DISPLAY_DZ + DISPLAY_DZ, DISPLAY_DZ)


def display_cn2_profile(
    z_display: np.ndarray, z_cn2: np.ndarray, cn2: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Cn2 on the regular display grid, as in the V2 figure: native Cn2 values are placed on the
    full meteorological profile levels `z_display`, then linearly interpolated onto the grid."""
    cn2_by_z = {round(float(z0), 6): float(c0) for z0, c0 in zip(z_cn2, cn2) if np.isfinite(c0)}
    cn2_display = np.array([cn2_by_z.get(round(float(z0), 6), np.nan) for z0 in z_display], dtype=float)
    finite_z = z_cn2[np.isfinite(z_cn2)]
    heights = display_grid(float(np.max(finite_z)) if finite_z.size else np.nan)
    return heights, interp_on_grid(heights, z_display, cn2_display)
