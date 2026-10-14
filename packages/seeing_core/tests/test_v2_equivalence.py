"""Numerical equivalence with the original V2 research script.

Fixtures were captured from the real AROME run 2026-10-14T00Z (see make_fixtures.py):
`extracted.npz` = per-site point data read from the GRIBs, `v2_expected.npz` = outputs of the
unmodified V2 physics for each site. The opt-in integration test re-reads the GRIBs themselves
when SEEING_GRIB_DIR points to the files of that run.
"""

import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from seeing_core import compute_from_extracted, compute_sites
from seeing_core.serialize import load_extracted, save_extracted
from tests.sites import FIXTURE_SITES

FIXTURES = Path(__file__).parent / "fixtures"
RTOL = 1e-6


@pytest.fixture(scope="module")
def expected():
    with np.load(FIXTURES / "v2_expected.npz") as f:
        return {k: f[k] for k in f.files}


@pytest.fixture(scope="module")
def extracted():
    return load_extracted(FIXTURES / "extracted.npz")


def assert_matches_v2(forecasts, expected):
    for site in FIXTURE_SITES:
        fc = forecasts[site.slug]
        assert fc.run_time == datetime.fromisoformat(str(expected["run_time"]))
        hours = expected[f"{site.slug}/forecast_hour"].astype(int)
        assert [h.lead_hour for h in fc.hours] == list(hours)
        got = {
            "integral_Cn2": [h.integral_cn2 for h in fc.hours],
            "r0_m": [h.r0_m for h in fc.hours],
            "seeing_arcsec": [h.seeing_arcsec for h in fc.hours],
            "H_COULIM_m": [h.h_coulim_m for h in fc.hours],
            "surface_altitude_m": [h.model_altitude_m for h in fc.hours],
        }
        for col, values in got.items():
            np.testing.assert_allclose(values, expected[f"{site.slug}/{col}"], rtol=RTOL, err_msg=f"{site.slug} {col}")

        # Display profile: V2 uses one grid for all hours (up to the max top), we use a per-hour
        # grid with the same origin and step -> compare on the common part.
        z_v2 = expected[f"{site.slug}/display_z"]
        cn2_v2 = expected[f"{site.slug}/display_cn2"]
        for row, h in zip(cn2_v2, fc.hours):
            n = h.heights_m.size
            np.testing.assert_array_equal(h.heights_m, z_v2[:n])
            np.testing.assert_allclose(h.cn2, row[:n], rtol=1e-6, equal_nan=True)  # fixture stored as float32
            assert np.all(np.isnan(row[n:]))


def test_physics_matches_v2(extracted, expected):
    forecasts = compute_from_extracted(extracted, FIXTURE_SITES, forecast_hours=51)
    assert_matches_v2(forecasts, expected)


def test_serialize_roundtrip(extracted, tmp_path):
    save_extracted(extracted, tmp_path / "x.npz", slugs=["saint-veran"], hours=range(0, 4))
    small = load_extracted(tmp_path / "x.npz")
    assert small.slugs == ["saint-veran"]
    assert small.data["HP1"]["saint-veran"][3] == extracted.data["HP1"]["saint-veran"][3]
    assert small.surface_h["saint-veran"] == extracted.surface_h["saint-veran"]


@pytest.mark.skipif("SEEING_GRIB_DIR" not in os.environ, reason="set SEEING_GRIB_DIR to the GRIBs of run 2026-10-14T00Z")
def test_grib_integration(expected):
    forecasts = compute_sites(Path(os.environ["SEEING_GRIB_DIR"]), FIXTURE_SITES, forecast_hours=51)
    assert_matches_v2(forecasts, expected)
