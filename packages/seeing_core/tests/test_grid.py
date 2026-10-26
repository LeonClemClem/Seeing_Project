"""The vectorised map physics must give the per-site V2bd result for the same columns."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from seeing_core import SiteSpec, compute_from_extracted
from seeing_core.grid import (
    MAP_K,
    decode_seeing,
    encode_seeing,
    night_steps,
    order_by_group,
    seeing_map,
)
from seeing_core.serialize import load_extracted
from tests.sites import FIXTURE_SITES

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def extracted():
    return load_extracted(FIXTURES / "extracted.npz")


def fields_of_sites(run, slugs, step):
    """The sites as a 1 x n grid: fields[(package, shortName, level)] = values of every site."""
    keys = set()
    for pkg in ("HP1", "HP2", "IP1", "IP4", "SP2"):
        for slug in slugs:
            for name, by_level in run.data[pkg][slug].get(step, {}).items():
                keys |= {(pkg, name, float(lev)) for lev in by_level}
    fields = {}
    for pkg, name, lev in keys:
        fields[(pkg, name, lev)] = np.array(
            [[run.data[pkg][s].get(step, {}).get(name, {}).get(lev, np.nan) for s in slugs]], dtype=np.float32
        )

    def sshf(h):
        return np.array([[next(iter(run.data["SP3"][s].get(h, {}).get("sshf", {np.nan: np.nan}).values())) for s in slugs]])

    h = max(step, 1)
    oro = np.array([[run.surface_h[s] for s in slugs]])
    return fields, sshf(h), sshf(h - 1), oro


@pytest.mark.parametrize("step", [3, 14, 22, 30, 46])
def test_map_matches_site_v2bd(extracted, step):
    slugs = [s.slug for s in FIXTURE_SITES]
    sites = [SiteSpec(s.slug, s.lat, s.lon, MAP_K[2], MAP_K[0], MAP_K[1]) for s in FIXTURE_SITES]
    fc = compute_from_extracted(extracted, sites, forecast_hours=step)
    expected = [next(h.seeing_arcsec for h in fc[s].hours if h.lead_hour == step) for s in slugs]
    fields, now, prev, oro = fields_of_sites(extracted, slugs, step)
    got = seeing_map(fields, now, prev, oro)[0]
    # fields are float32 on the map (float64 for the sites)
    np.testing.assert_allclose(got, expected, rtol=2e-3)


def test_encode_roundtrip():
    s = np.array([[0.5, 1.0, np.nan], [3.0, 12.0, 0.1]])
    d = decode_seeing(encode_seeing(s), s.shape)
    assert np.isnan(d[0, 2])
    np.testing.assert_allclose(d[0, :2], [0.5, 1.0], rtol=0.01)
    np.testing.assert_allclose(d[1], [3.0, 10.0, 0.2], rtol=0.01)  # clipped to the stored range


def test_night_steps_and_order():
    steps = night_steps(datetime(2026, 10, 14, 0, tzinfo=UTC), 51)
    assert steps[:9] == list(range(20, 29)) and steps[9:] == list(range(44, 52))
    steps18 = night_steps(datetime(2026, 10, 14, 18, tzinfo=UTC), 51)
    assert steps18[:9] == list(range(2, 11))
    urls = [("HP1", "x/arome__0025__HP1__07H12H__a.grib2"), ("SP2", "x/arome__0025__SP2__00H06H__a.grib2"),
            ("HP1", "x/arome__0025__HP1__00H06H__a.grib2"), ("SP2", "x/arome__0025__SP2__07H12H__a.grib2")]
    assert [u[1].split("__")[2:4] for u in order_by_group(urls)] == [["HP1", "00H06H"], ["SP2", "00H06H"], ["HP1", "07H12H"], ["SP2", "07H12H"]]
