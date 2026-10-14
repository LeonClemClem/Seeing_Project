"""Unit tests of the physics building blocks (no GRIB, no fixtures)."""

from datetime import UTC, datetime

import numpy as np
import pytest

from seeing_core import ExtractedRun, SiteSpec, compute_from_extracted, parse_grib_filename
from seeing_core.cn2 import cn2_convective, cn2_shear, cn2_tke
from seeing_core.constants import HEIGHTS, LAMBDA
from seeing_core.profiles import get_h_coulim, surface_kinematic_heat_flux
from seeing_core.seeing import display_cn2_profile, display_grid, integrate_seeing


def test_integrate_seeing_constant_profile():
    z = np.array([0.0, 500.0, 1000.0])
    cn2 = np.full(3, 1e-16)
    integral, r0, seeing = integrate_seeing(z, cn2)
    assert integral == pytest.approx(1e-13)
    assert r0 == pytest.approx((0.423 * (2 * np.pi / LAMBDA) ** 2 * 1e-13) ** (-3 / 5))
    assert seeing == pytest.approx(0.98 * LAMBDA / r0 * 206265.0)


def test_integrate_seeing_skips_nan_and_unsorted():
    z = np.array([1000.0, np.nan, 0.0, 500.0])
    cn2 = np.array([1e-16, 1.0, 1e-16, np.nan])
    assert integrate_seeing(z, cn2)[0] == pytest.approx(1e-13)
    assert all(np.isnan(integrate_seeing(np.array([1.0]), np.array([1e-16]))))


def _stable_profile(n=10):
    z = np.linspace(100, 1000, n)
    T = 290.0 - 0.003 * z  # sub-adiabatic -> dtheta/dz > 0
    P = 1000.0 * np.exp(-z / 8000.0)
    U = 0.01 * z
    V = np.zeros(n)
    return {"z": z, "T": T, "P": P, "U": U, "V": V, "TKE": np.full(n, 0.5)}


def test_cn2_models_scale_with_k():
    p = _stable_profile()
    a, b = cn2_tke(p, 1.0), cn2_tke(p, 3.0)
    assert np.all(np.isfinite(a)) and np.all(a > 0)
    np.testing.assert_allclose(b, 3 * a)
    s1, s2 = cn2_shear(p, 1.0), cn2_shear(p, 30.0)
    assert np.all(s1 > 0)
    np.testing.assert_allclose(s2, 30 * s1)


def test_cn2_tke_holes_where_unstable():
    p = _stable_profile()
    p["T"] = 300.0 - 0.02 * p["z"]  # super-adiabatic: no TKE solution
    assert np.all(np.isnan(cn2_tke(p, 3.0)))
    assert np.all(np.isnan(cn2_tke({k: v[:1] for k, v in p.items()}, 3.0)))


def test_cn2_convective_plateau_and_top():
    p = _stable_profile()
    c = cn2_convective(p, w_theta0=0.1, zi=600.0, theta0=290.0, k_tke_conv=0.3)
    assert np.all(np.isnan(c[p["z"] > 600.0]))
    assert np.all(c[p["z"] <= 600.0] > 0)
    assert np.all(np.isnan(cn2_convective(p, np.nan, 600.0, 290.0, 0.3)))


def test_h_coulim_and_heat_flux():
    sp2 = {3: {"h_coulim": {0.0: 850.0}}, 4: {"blh": {0.0: 900.0}}}
    assert get_h_coulim(sp2, 3) == 850.0
    assert get_h_coulim(sp2, 4) == 900.0
    assert np.isnan(get_h_coulim(sp2, 5))
    sp3 = {0: {"sshf": {0.0: 0.0}}, 1: {"sshf": {0.0: -360000.0}}}
    w0 = surface_kinematic_heat_flux(sp3, 0, 290.0, 900.0)  # hour 0 uses (1 - 0)
    assert w0 == surface_kinematic_heat_flux(sp3, 1, 290.0, 900.0)
    assert w0 > 0  # SSHF_SIGN = -1: negative accumulation = surface heating
    assert np.isnan(surface_kinematic_heat_flux(sp3, 2, 290.0, 900.0))


def test_display_grid():
    np.testing.assert_array_equal(display_grid(250.0), [10.0, 110.0, 210.0, 310.0])
    heights, cn2 = display_cn2_profile(
        np.array([10.0, 100.0, 300.0]), np.array([10.0, 100.0, 300.0]), np.array([1.0, np.nan, 3.0])
    )
    np.testing.assert_array_equal(heights, [10.0, 110.0, 210.0, 310.0])
    np.testing.assert_allclose(cn2[:3], [1.0, 1.0 + 2 * 100 / 290, 1.0 + 2 * 200 / 290])
    assert np.isnan(cn2[3])


def test_parse_grib_filename():
    assert parse_grib_filename("arome__0025__HP1__07H12H__2026-10-13T00-00-00Z.grib2") == ("HP1", 7, 12)
    with pytest.raises(ValueError):
        parse_grib_filename("foo.grib2")


def _synthetic_run(hours=(0, 1, 2)):
    slug = "s"
    hp1, hp2, ip1, ip4, sp2, sp3 = {}, {}, {}, {}, {}, {}
    for h in hours:
        hp1[h] = {
            "t": {z: 288.0 - 0.004 * z for z in HEIGHTS},
            "u": {z: 2.0 + 0.004 * z for z in HEIGHTS},
            "v": {z: 1.0 for z in HEIGHTS},
            "pres": {z: 100.0 * 900.0 * np.exp(-z / 8000.0) for z in HEIGHTS},  # Pa -> converted
        }
        hp2[h] = {"tke": {z: 0.3 for z in HEIGHTS}}
        levels = [850.0, 700.0, 600.0, 500.0, 400.0, 300.0, 250.0, 200.0]
        zs = [1500, 3000, 4200, 5600, 7200, 9200, 10400, 11800]
        ip1[h] = {
            "z": {p: 9.81 * (z + 1000.0) for p, z in zip(levels, zs)},
            "t": {p: 288.0 - 0.0065 * z for p, z in zip(levels, zs)},
            "u": {p: 5.0 + 0.002 * z for p, z in zip(levels, zs)},
            "v": {p: 0.0 for p in levels},
        }
        ip4[h] = {"tke": {p: 0.1 for p in levels}}
        sp2[h] = {"h_coulim": {0.0: 700.0}}
        sp3[h] = {"sshf": {0.0: -1e5 * h}}
    return ExtractedRun(
        run_time=datetime(2026, 10, 13, tzinfo=UTC), slugs=[slug],
        data={k: {slug: v} for k, v in dict(HP1=hp1, HP2=hp2, IP1=ip1, IP4=ip4, SP2=sp2, SP3=sp3).items()},
        surface_h={slug: 1000.0}, grid_points={slug: (44.0, 6.0)},
    )


SITE = SiteSpec("s", 44.0, 6.0, 0.3, 3.0, 30.0)


def test_pipeline_synthetic_and_missing_hours_skipped():
    run = _synthetic_run(hours=(0, 1, 3))
    fc = compute_from_extracted(run, [SITE], forecast_hours=3)["s"]
    assert [h.lead_hour for h in fc.hours] == [0, 1, 3]  # H+2 missing: skipped, no crash
    h = fc.hours[0]
    assert h.valid_time == datetime(2026, 10, 13, tzinfo=UTC)
    assert h.h_coulim_m == 700.0 and h.model_altitude_m == 1000.0
    assert np.isfinite(h.seeing_arcsec) and h.seeing_arcsec > 0
    assert h.heights_m[0] == 10.0 and np.all(np.diff(h.heights_m) == 100.0)
    assert h.heights_m.shape == h.cn2.shape


def test_pipeline_missing_h_coulim_skips_hour():
    run = _synthetic_run(hours=(0, 1))
    run.data["SP2"]["s"][1] = {"h_coulim": {0.0: np.nan}}
    fc = compute_from_extracted(run, [SITE], forecast_hours=1)["s"]
    assert [h.lead_hour for h in fc.hours] == [0]


def test_k_coefficients_come_from_site():
    run = _synthetic_run(hours=(0,))
    a = compute_from_extracted(run, [SITE], 0)["s"].hours[0]
    b = compute_from_extracted(run, [SiteSpec("s", 44.0, 6.0, 0.3, 6.0, 60.0)], 0)["s"].hours[0]
    # Both TKE and shear branches doubled -> integral doubled (the convective one is unused here).
    assert b.integral_cn2 == pytest.approx(2 * a.integral_cn2, rel=1e-12)
