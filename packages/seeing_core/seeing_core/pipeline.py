"""Public API: per-site seeing forecasts from an AROME run."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from seeing_core.cn2 import cn2_convective, cn2_shear, cn2_tke, potential_temperature
from seeing_core.grib import ExtractedRun, extract_dir
from seeing_core.profiles import (
    boundary_layer_profile,
    build_hag_profile,
    build_isobaric_profile,
    display_profile_heights,
    free_atmosphere_profile,
    get_h_coulim,
    surface_kinematic_heat_flux,
)
from seeing_core.seeing import display_cn2_profile, integrate_seeing

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SiteSpec:
    slug: str
    lat: float
    lon: float
    k_tke_conv: float  # convective closure (fills TKE holes in the boundary layer)
    k_tke: float  # TKE model (boundary layer)
    k_cis: float  # wind-shear model (free atmosphere)


@dataclass
class HourResult:
    lead_hour: int
    valid_time: datetime  # tz-aware UTC
    seeing_arcsec: float
    r0_m: float
    integral_cn2: float
    h_coulim_m: float
    model_altitude_m: float
    heights_m: np.ndarray  # display grid [m AGL]
    cn2: np.ndarray  # Cn2 on heights_m [m^-2/3], NaN where undefined


@dataclass
class SiteForecast:
    slug: str
    run_time: datetime
    hours: list[HourResult]


class MissingDataError(LookupError):
    """Input data needed for one lead hour is missing."""


REQUIRED_HOURLY = ("HP1", "HP2", "IP1", "IP4", "SP2")


def compute_hour(
    site: SiteSpec,
    hourly: dict[str, dict],
    sp3: dict,
    hour: int,
    surface_altitude: float,
) -> tuple[float, float, float, float, np.ndarray, np.ndarray]:
    """Physics of one site / lead hour.

    `hourly[pkg]` is the site's SitePoints of each required package, `sp3` the SP3 SitePoints
    (possibly empty: no convective closure). Returns
    (integral_cn2, r0, seeing, h_coulim, display_heights, display_cn2).

    Model layout (H_COULIM is the physical boundary, 3000 m only the top of the HAG grids):
      - H_COULIM <= 3000 m: TKE on HP2 up to H_COULIM, then shear on HAG levels, then IP1.
      - H_COULIM >  3000 m: TKE on HP2 up to 3000 m, TKE on IP4 up to H_COULIM, shear on IP1 above.
    The Cn2 integration is done on the native combined levels, without interpolation.
    """
    for pkg in REQUIRED_HOURLY:
        if hour not in hourly[pkg]:
            raise MissingDataError(f"H+{hour} missing from {pkg}")
    h_coulim = get_h_coulim(hourly["SP2"], hour)
    if not np.isfinite(h_coulim):
        raise MissingDataError(f"H_COULIM/blh unavailable at H+{hour}")

    hag = build_hag_profile(hourly["HP1"][hour], hourly["HP2"].get(hour))
    iso = build_isobaric_profile(hourly["IP1"][hour], hourly["IP4"].get(hour), surface_altitude)

    # Boundary layer: the TKE model (Masciadri formula with the real HP2/IP4 TKE) is the main
    # computation everywhere below H_COULIM. The free-convection closure only FILLS the levels
    # where it fails (Cn2 = NaN, i.e. dtheta/dz <= 0); it never replaces a valid TKE value.
    bl = boundary_layer_profile(hag, iso, h_coulim)
    cn2_bl = cn2_tke(bl, site.k_tke)
    if bl["z"].size:
        theta0 = potential_temperature(bl["T"][0], bl["P"][0])
        w_theta0 = surface_kinematic_heat_flux(sp3, hour, bl["T"][0], bl["P"][0])
        if np.isfinite(w_theta0) and w_theta0 > 0:
            holes = ~np.isfinite(cn2_bl)
            if np.any(holes):
                cn2_conv = cn2_convective(bl, w_theta0, h_coulim, theta0, site.k_tke_conv)
                cn2_bl[holes] = cn2_conv[holes]
                logger.debug(
                    "%s H+%02d: %d BL level(s) filled by the convective closure (w'theta0=%.4f K.m/s)",
                    site.slug, hour, int(np.count_nonzero(holes)), w_theta0,
                )

    # Free atmosphere: shear model above H_COULIM (unchanged by the convective closure).
    fa = free_atmosphere_profile(hag, iso, h_coulim)
    cn2_fa = cn2_shear(fa, site.k_cis)

    # BL then FA levels: already increasing in altitude.
    z_cn2 = np.concatenate([bl["z"], fa["z"]])
    cn2 = np.concatenate([cn2_bl, cn2_fa])
    integral, r0, seeing = integrate_seeing(z_cn2, cn2)

    heights, cn2_display = display_cn2_profile(display_profile_heights(hag, iso), z_cn2, cn2)
    return integral, r0, seeing, h_coulim, heights, cn2_display


def compute_from_extracted(
    run: ExtractedRun, sites: Sequence[SiteSpec], forecast_hours: int = 51
) -> dict[str, SiteForecast]:
    """Physics for every site from already-extracted point data. Hours with missing inputs are
    skipped with a warning."""
    if run.run_time is None:
        raise RuntimeError("AROME cycle date not found in the GRIB files")
    out: dict[str, SiteForecast] = {}
    for site in sites:
        hourly = {pkg: run.data.get(pkg, {}).get(site.slug, {}) for pkg in REQUIRED_HOURLY}
        sp3 = run.data.get("SP3", {}).get(site.slug, {})
        if not sp3:
            logger.warning("%s: no SP3 data, convective closure disabled", site.slug)
        surface_altitude = run.surface_h.get(site.slug, np.nan)
        if not np.isfinite(surface_altitude):
            raise RuntimeError(f"{site.slug}: model orography SP2:h not found")

        hours: list[HourResult] = []
        for hour in range(forecast_hours + 1):
            try:
                integral, r0, seeing, h_coulim, heights, cn2 = compute_hour(
                    site, hourly, sp3, hour, surface_altitude
                )
            except MissingDataError as exc:
                logger.warning("%s: skipping H+%02d: %s", site.slug, hour, exc)
                continue
            hours.append(
                HourResult(
                    lead_hour=hour,
                    valid_time=run.run_time + timedelta(hours=hour),
                    seeing_arcsec=seeing,
                    r0_m=r0,
                    integral_cn2=integral,
                    h_coulim_m=h_coulim,
                    model_altitude_m=surface_altitude,
                    heights_m=heights,
                    cn2=cn2,
                )
            )
        out[site.slug] = SiteForecast(slug=site.slug, run_time=run.run_time, hours=hours)
    return out


def compute_sites(grib_dir: Path, sites: Sequence[SiteSpec], forecast_hours: int = 51) -> dict[str, SiteForecast]:
    """Seeing forecasts for all `sites` from the AROME files (SP2 SP3 HP1 HP2 IP1 IP4) in
    `grib_dir`, read in a single pass. `run_time` is the AROME cycle read from the GRIB."""
    run = extract_dir(Path(grib_dir), sites, forecast_hours)
    return compute_from_extracted(run, sites, forecast_hours)
