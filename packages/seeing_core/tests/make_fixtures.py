"""Regenerate the committed fixtures from a real AROME run (developer tool, not a test).

    poetry run python tests/make_fixtures.py <grib_dir> <v2_out_dir>

<v2_out_dir> holds the outputs of the ORIGINAL research script
(research/SeeingAromeV2_correction_conv_tke.py) run on the same <grib_dir>, one copy per site
with LAT/LON/K patched: `v2_<slug>.csv` (its CSV) and `v2_<slug>_display.npz` (the Cn2 matrix
of its figure: hours, display_z, cn2).

Writes tests/fixtures/extracted.npz (per-site point data, all lead hours) and
tests/fixtures/v2_expected.npz (V2 outputs).
"""

import csv
import sys
from pathlib import Path

import numpy as np

from seeing_core import extract_dir
from seeing_core.serialize import save_extracted
from tests.sites import FIXTURE_SITES

FIXTURES = Path(__file__).parent / "fixtures"


def main(grib_dir: Path, v2_dir: Path) -> None:
    run = extract_dir(grib_dir, FIXTURE_SITES)
    save_extracted(run, FIXTURES / "extracted.npz")

    expected = {}
    for site in FIXTURE_SITES:
        with open(v2_dir / f"v2_{site.slug}.csv") as f:
            rows = list(csv.DictReader(f))
        for col in ("forecast_hour", "surface_altitude_m", "H_COULIM_m", "integral_Cn2", "r0_m", "seeing_arcsec"):
            expected[f"{site.slug}/{col}"] = np.array([float(r[col]) for r in rows])
        disp = np.load(v2_dir / f"v2_{site.slug}_display.npz")
        expected[f"{site.slug}/display_hours"] = disp["hours"]
        expected[f"{site.slug}/display_z"] = disp["display_z"]
        expected[f"{site.slug}/display_cn2"] = disp["cn2"].astype(np.float32)
    expected["run_time"] = np.array(run.run_time.isoformat())
    np.savez_compressed(FIXTURES / "v2_expected.npz", **expected)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
