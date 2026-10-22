---
name: python
description: Python coding standards for this repository (research scripts, packages, API). Use whenever writing or modifying Python code — PEP 8, ruff + isort formatting and linting, no hard-coded values, command-line parameters through argparse with sensible defaults.
---

# Python standards

## Style: PEP 8, enforced by ruff

Configuration lives in `ruff.toml` (repo root) and `.isort.cfg`. Line length is 120.

```bash
pip install ruff isort        # or: poetry run ..., pipx run ruff ...
ruff check <paths>            # lint (pyflakes, pycodestyle, isort, bugbear, pyupgrade...)
ruff check --fix <paths>      # safe automatic fixes, including import sorting
ruff format <paths>           # formatting
isort <paths>                 # only if someone runs isort standalone; settings match ruff
```

`make lint` and `make format` run the same commands on `research/`.

- Run `ruff check` and `ruff format --check` on every file you touch before committing.
- When reformatting an existing file, do it in a **separate commit** ("style: ...") so the
  real change stays readable in review. Do not reformat files you are not otherwise changing.
- Imports: standard library, third-party, local — one per line, sorted (ruff rule `I`).
- Names: `snake_case` functions and variables, `CapWords` classes, `UPPER_CASE` module constants.
- Every module and public function gets a docstring saying what it does, its inputs/outputs
  and units (seeing in arcsec, Cn2 in m^-2/3, heights in m above ground, times in UTC).

## No hard-coded values

- **Paths**: never write `C:\Users\...` or any machine-specific folder. Data folders come from
  `research/chemins.py` (`AROME_RUNS`, `CACHE`, `PREVISIONS`, `TESTS`, `MESURES`, `MESURES_V1`),
  configured per machine in `research/chemins_locaux.json` (not versioned).
- **Run-specific choices** (run folder, site, latitude/longitude, forecast hours, K coefficients,
  zone radius, output file...) are command-line parameters, not values edited in the source.
- **Physical constants and model settings** that are genuinely fixed stay as named
  `UPPER_CASE` constants at the top of the module, with a comment giving the unit and source.
- **Secrets** (tokens, passwords, API keys) never appear in code: read them from environment
  variables, and fail with a clear message when missing.

## Command-line interface: argparse with defaults

Every script that is run directly exposes its parameters with `argparse`, keeps working with no
arguments (defaults reproduce today's behaviour), and documents units in the help text.

```python
import argparse
from pathlib import Path

from chemins import AROME_RUNS

DEFAULT_RUN = "AROME_download_2026-10-20_12Z"
DEFAULT_K = (8.0, 40.0, 0.1)  # K_TKE, K_CIS, K_conv


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Seeing V2 at one site from an AROME run.")
    parser.add_argument("--run", type=Path, default=AROME_RUNS / DEFAULT_RUN, help="AROME run folder")
    parser.add_argument("--lat", type=float, default=44.3814, help="site latitude (deg N)")
    parser.add_argument("--lon", type=float, default=5.4286, help="site longitude (deg E)")
    parser.add_argument("--hours", type=int, default=51, help="last forecast hour to compute")
    parser.add_argument("--k", type=float, nargs=3, default=DEFAULT_K, metavar=("K_TKE", "K_CIS", "K_CONV"))
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    ...


if __name__ == "__main__":
    main()
```

- Put the work in `main(argv=None)` behind `if __name__ == "__main__":`, so other scripts can
  import the module (many of our tools load each other with `importlib`) without running it.
- Keep module-level globals that other tools override (e.g. `DATA_DIR`, `K_TKE`) until those
  callers are migrated; add the argparse layer on top rather than breaking them.

## Project-specific rules (from the user)

- Do not change the physics of `SeeingAromeV2_correction_conv_tke.py` or its K coefficients
  unless the user asks. Refactors must give identical results: compare outputs before/after.
- Missing data: an incomplete forecast hour gives an empty Cn2 column and a gap in the seeing,
  never a crash and never an interpolation.
- All times in UTC.
