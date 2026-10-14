"""Cn2 models: TKE (boundary layer), free-convection closure (fills TKE holes), wind shear
(free atmosphere). Formulas are copied verbatim from the V2 research script; the per-site
coefficients k_* are parameters instead of globals."""

from __future__ import annotations

import numpy as np

from seeing_core.constants import C_FC, G, P0_HPA, R_OVER_CP
from seeing_core.profiles import Profile


def potential_temperature(T: np.ndarray, P: np.ndarray) -> np.ndarray:
    return T * (P0_HPA / P) ** R_OVER_CP


def cn2_tke(profile: Profile, k_tke: float) -> np.ndarray:
    """Masciadri "new equation" with the model TKE E:

        Cn2 = K_TKE * 3.35e-6 * P^(2(1-2R/cp)) * theta^(-10/3) * (dtheta/dz)^(4/3) * E^(2/3)

    Only defined in stable layers (dtheta/dz > 0, E > 0); NaN elsewhere (the "holes").
    """
    z = np.asarray(profile["z"], dtype=float)
    T = np.asarray(profile["T"], dtype=float)
    P = np.asarray(profile["P"], dtype=float)
    E = np.asarray(profile["TKE"], dtype=float)

    # No (or a single) level in the TKE layer: H_COULIM below the first levels.
    if z.size < 2:
        return np.full_like(z, np.nan, dtype=float)

    theta = potential_temperature(T, P)
    dtheta_dz = np.gradient(theta, z)
    L = np.full_like(z, np.nan)

    stable = np.isfinite(E) & np.isfinite(theta) & np.isfinite(dtheta_dz) & (E > 0) & (dtheta_dz > 0)
    L[stable] = np.sqrt(2.0 * E[stable] / ((G / theta[stable]) * dtheta_dz[stable]))

    cn2 = np.full_like(z, np.nan)
    valid = stable & np.isfinite(L) & (L > 0) & np.isfinite(P) & np.isfinite(T) & (T > 0)

    exponent = 2 * (1 - 2 * R_OVER_CP)
    cn2[valid] = k_tke * (
        3.35e-6
        * (P[valid] ** exponent)
        * (theta[valid] ** (-10 / 3))
        * (dtheta_dz[valid] ** (4 / 3))
        * (E[valid] ** (2 / 3))
    )
    return cn2


def cn2_convective(profile: Profile, w_theta0: float, zi: float, theta0: float, k_tke_conv: float) -> np.ndarray:
    """Cn2 in the convective boundary layer, free-convection regime (u* -> 0 limit of
    Monin-Obukhov similarity, Wyngaard-Izumi-Collins 1971):

        CT2(z) = C_FC * (g/theta0)^(-2/3) * (w'theta'_0)^(4/3) * z^(-4/3)

    Independent of u*, so no surface stress is needed. Above 0.1*zi CT2 is frozen at its
    0.1*zi value ("plateau" approximation for the mixed-layer core, lacking verified
    coefficients for the full Wyngaard & LeMone 1980 form). Valid below zi only, NaN above.

    The optical conversion is the SAME as the TKE branch (Masciadri formula), not the classical
    Gladstone-Dale (80e-6*P/(T*theta))^2: writing the Masciadri formula as
    prefactor(P, theta) * CT2 with CT2 = L^(4/3) * (dtheta/dz)^2 gives
        prefactor(P, theta) = 3.35e-6 * (g/2)^(2/3) * P^exponent * theta^-4
    which is applied here to the free-convection CT2.
    """
    z = np.asarray(profile["z"], dtype=float)
    T = np.asarray(profile["T"], dtype=float)
    P = np.asarray(profile["P"], dtype=float)

    theta = potential_temperature(T, P)
    cn2 = np.full_like(z, np.nan)

    valid = (
        np.isfinite(z) & (z > 0)
        & np.isfinite(zi) & (zi > 0)
        & (z <= zi)
        & np.isfinite(P) & np.isfinite(T) & (T > 0)
        & np.isfinite(theta0) & (theta0 > 0)
        & np.isfinite(w_theta0)
    )
    if np.any(valid):
        z_plateau = np.clip(z[valid], 1.0, 0.1 * zi)
        CT2 = C_FC * (G / theta0) ** (-2.0 / 3.0) * (w_theta0 ** (4.0 / 3.0)) * z_plateau ** (-4.0 / 3.0)
        exponent = 2.0 * (1.0 - 2.0 * R_OVER_CP)
        prefactor = 3.35e-6 * (G / 2.0) ** (2.0 / 3.0) * P[valid] ** exponent * theta[valid] ** (-4.0)
        cn2[valid] = k_tke_conv * prefactor * CT2
    return cn2


def cn2_shear(profile: Profile, k_cis: float) -> np.ndarray:
    """Free-atmosphere model: TKE parameterised by the wind shear, E = S^2 = (dU/dz)^2 + (dV/dz)^2,
    with the classical Gladstone-Dale conversion:

        Cn2 = K_CIS * (80e-6 * P / (T * theta))^2 * L^(4/3) * (dtheta/dz)^2
    """
    z = np.asarray(profile["z"], dtype=float)
    T = np.asarray(profile["T"], dtype=float)
    U = np.asarray(profile["U"], dtype=float)
    V = np.asarray(profile["V"], dtype=float)
    P = np.asarray(profile["P"], dtype=float)

    if z.size < 2:  # np.gradient needs 2 points (V2 would crash here)
        return np.full_like(z, np.nan, dtype=float)

    theta = potential_temperature(T, P)
    dtheta_dz = np.gradient(theta, z)
    dU_dz = np.gradient(U, z)
    dV_dz = np.gradient(V, z)

    S = np.sqrt(dU_dz ** 2 + dV_dz ** 2)
    E = S ** 2

    L = np.full_like(z, np.nan)
    stable = np.isfinite(E) & np.isfinite(theta) & np.isfinite(dtheta_dz) & (E > 0) & (dtheta_dz > 0)
    L[stable] = np.sqrt(2.0 * E[stable] / ((G / theta[stable]) * dtheta_dz[stable]))

    cn2 = np.full_like(z, np.nan)
    valid = stable & np.isfinite(L) & (L > 0) & np.isfinite(P) & np.isfinite(T) & (T > 0)
    cn2[valid] = (
        k_cis * (80e-6 * P[valid] / (T[valid] * theta[valid])) ** 2
        * L[valid] ** (4.0 / 3.0) * dtheta_dz[valid] ** 2
    )
    return cn2
