"""Vertical profiles at one site and one lead hour, built from extracted point data."""

from __future__ import annotations

import numpy as np

from seeing_core.constants import CP_AIR, G, HAG_TOP_M, HEIGHTS, R_D, SSHF_SIGN
from seeing_core.grib import SitePoints

Profile = dict[str, np.ndarray]


def get_h_coulim(sp2: SitePoints, hour: int) -> float:
    """Boundary-layer height H_COULIM (or blh) [m] from SP2, NaN if unavailable."""
    source = sp2.get(hour, {})
    for name in ("h_coulim", "blh"):
        values = source.get(name, {})
        if values:
            value = next(iter(values.values()))
            if np.isfinite(value):
                return float(value)
    return np.nan


def build_hag_profile(hp1_hour: dict, hp2_hour: dict | None) -> Profile:
    """HP1 (T, U, V, P) + HP2 (TKE) on the fixed heightAboveGround grid HEIGHTS."""

    def arr(source, variable):
        out = np.full(len(HEIGHTS), np.nan)
        if source is None or variable not in source:
            return out
        for i, h in enumerate(HEIGHTS):
            if h in source[variable]:
                out[i] = source[variable][h]
        return out

    T = arr(hp1_hour, "t")
    U = arr(hp1_hour, "u")
    V = arr(hp1_hour, "v")
    P = arr(hp1_hour, "pres")
    TKE = arr(hp2_hour, "tke") if hp2_hour is not None else np.full(len(HEIGHTS), np.nan)

    # Pressure may come in Pa or hPa depending on the GRIB mapping.
    finite_p = P[np.isfinite(P)]
    if finite_p.size and np.nanmedian(finite_p) > 2000:
        P /= 100.0

    return {"z": HEIGHTS.copy(), "T": T, "U": U, "V": V, "P": P, "TKE": TKE}


def build_isobaric_profile(ip1_hour: dict, ip4_hour: dict | None, surface_altitude: float) -> Profile:
    """IP1 (T, U, V, Z) + IP4 (TKE) on isobaric levels, as a profile in metres AGL.

    Z/g is converted to AGL with the model orography SP2:h; levels below ground are dropped.
    """
    levels = sorted(ip1_hour.get("z", {}).keys())
    z = np.asarray([ip1_hour["z"][lev] for lev in levels], dtype=float) / G
    T = np.asarray([ip1_hour.get("t", {}).get(lev, np.nan) for lev in levels], dtype=float)
    U = np.asarray([ip1_hour.get("u", {}).get(lev, np.nan) for lev in levels], dtype=float)
    V = np.asarray([ip1_hour.get("v", {}).get(lev, np.nan) for lev in levels], dtype=float)
    P = np.asarray(levels, dtype=float)

    if np.isfinite(surface_altitude):
        z = z - surface_altitude

    valid = np.isfinite(z) & np.isfinite(T) & np.isfinite(U) & np.isfinite(V) & (z > 0)
    z, T, U, V, P = z[valid], T[valid], U[valid], V[valid], P[valid]

    order = np.argsort(z)
    z, T, U, V, P = z[order], T[order], U[order], V[order], P[order]

    # Drop duplicate altitudes. (V2 forgot to filter P here, which could only crash; same values otherwise.)
    if z.size:
        keep = np.r_[True, np.diff(z) > 1e-6]
        z, T, U, V, P = z[keep], T[keep], U[keep], V[keep], P[keep]

    profile = {"z": z, "T": T, "U": U, "V": V, "P": P}
    profile["TKE"] = _ip4_tke(P, ip4_hour or {})
    return profile


def _ip4_tke(pressures: np.ndarray, ip4_hour: dict) -> np.ndarray:
    """IP4 TKE at the IP1 isobaric levels."""
    out = np.full(pressures.shape, np.nan, dtype=float)
    tke_by_p = ip4_hour.get("tke", {})
    if not tke_by_p:
        return out
    missing = []
    for i, p in enumerate(pressures):
        value = tke_by_p.get(float(p))
        if value is None:
            missing.append((i, float(p)))
        else:
            out[i] = value
    # Fallback for rare floating-point representation mismatches of the level keys.
    if missing:
        p4_keys = np.fromiter(tke_by_p.keys(), dtype=float)
        p4_values = np.fromiter(tke_by_p.values(), dtype=float)
        for i, p in missing:
            j = np.flatnonzero(np.isclose(p4_keys, p, rtol=0, atol=1e-6))
            if j.size:
                out[i] = p4_values[j[0]]
    return out


def boundary_layer_profile(hag: Profile, iso: Profile, h_coulim: float) -> Profile:
    """Levels of the TKE model: HAG levels up to H_COULIM, then (if H_COULIM > 3000 m)
    isobaric levels between 3000 m and H_COULIM. Already sorted by altitude."""
    mask_hag = hag["z"] <= h_coulim
    mask_iso = (iso["z"] > HAG_TOP_M) & (iso["z"] <= h_coulim)
    return {
        k: np.concatenate([hag[k][mask_hag], iso[k][mask_iso]])
        for k in ("z", "T", "U", "V", "P", "TKE")
    }


def free_atmosphere_profile(hag: Profile, iso: Profile, h_coulim: float) -> Profile:
    """Levels of the shear model above H_COULIM. HAG levels have priority up to 3000 m (so when
    H_COULIM < 3000 m the shear model uses the HAG levels above H_COULIM), then IP1 above."""
    mask_hag = np.isfinite(hag["z"]) & (hag["z"] > h_coulim) & (hag["z"] <= HAG_TOP_M)
    mask_iso = np.isfinite(iso["z"]) & (iso["z"] > max(float(h_coulim), HAG_TOP_M))
    return {
        k: np.concatenate([np.asarray(hag[k])[mask_hag], np.asarray(iso[k])[mask_iso]])
        for k in ("z", "T", "U", "V", "P")
    }


def display_profile_heights(hag: Profile, iso: Profile) -> np.ndarray:
    """Altitudes of the full meteorological profile (all HAG levels up to 3000 m, IP1 above),
    independent of H_COULIM, sorted."""
    z = np.concatenate([
        np.asarray(hag["z"])[np.isfinite(hag["z"]) & (hag["z"] <= HAG_TOP_M)],
        np.asarray(iso["z"])[np.isfinite(iso["z"]) & (iso["z"] > HAG_TOP_M)],
    ])
    return z[np.argsort(z)]


def _sshf_accum(sp3: SitePoints, hour: int) -> float:
    """SP3:sshf accumulated since the start of the run, at a lead hour."""
    source = sp3.get(hour, {}).get("sshf", {})
    if not source:
        return np.nan
    return float(next(iter(source.values())))


def surface_kinematic_heat_flux(sp3: SitePoints, hour: int, T_low: float, P_low: float) -> float:
    """Surface kinematic heat flux w'theta'_0 [K.m/s], from the difference of the accumulated
    SP3:sshf field between two consecutive lead hours. NaN if SP3 is missing or unusable.

    The sign depends on the Meteo-France GRIB convention of sshf (SSHF_SIGN): w'theta'_0 must
    come out positive (heating) on a sunny afternoon.
    """
    h_ref = max(hour, 1)
    acc_now = _sshf_accum(sp3, h_ref)
    acc_prev = _sshf_accum(sp3, h_ref - 1)
    if not (np.isfinite(acc_now) and np.isfinite(acc_prev)):
        return np.nan

    Q_H = (acc_now - acc_prev) / 3600.0  # W/m^2, mean over the past hour
    Q_H *= SSHF_SIGN

    if not (np.isfinite(T_low) and np.isfinite(P_low) and T_low > 0 and P_low > 0):
        return np.nan

    rho = (P_low * 100.0) / (R_D * T_low)  # P_low hPa -> Pa
    return Q_H / (rho * CP_AIR)
