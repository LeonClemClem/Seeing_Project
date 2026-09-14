# Seeing Project

Tools to estimate astronomical **seeing** (atmospheric turbulence that blurs telescope images,
expressed in arcseconds) at a given location, using weather forecast data from Météo-France's
AROME model. The scripts turn temperature, wind and turbulence (TKE) profiles from AROME into
the optical turbulence parameter **Cn²**, then combine it into a seeing estimate and a set of
diagnostic plots.

This README is written for someone who has never used Python packaging tools before. Follow it
top to bottom.

## What's in this repo

| File | What it does |
|---|---|
| `telecharger_arome_meteofetch_TKE_cisaillement_HCOULIM_v3.py` | Downloads the AROME GRIB2 files needed by the calculations. **Run this first.** |
| `calcul_seeing_arome_2_modeles_V11_optimise.py` | Main seeing calculation (newer version). Reads the downloaded GRIB2 files, produces a CSV and a figure. |
| `calcul_seeing_arome_2_modeles_HCOULIM.py` | Earlier version of the same calculation, kept for reference/comparison. |
| `Model Masciardi et al 2001.py` | A small, self-contained example of the Cn² formula. It needs no downloaded data, so it's the easiest way to check your setup works. |
| `Quatresooz.pdf`, `seeing_cn2_of_mm5_OCuevas_Valpo2010.pdf` | Reference papers, not code. |

## 1. Prerequisites

You need Python 3.12 installed (3.10 and 3.11 will not work — the latest version of one of the
plotting libraries this project uses requires 3.12 or newer). Check what you have:

```bash
python3 --version
```

If it's older than 3.12, install Python 3.12+ from [python.org](https://www.python.org/downloads/)
first, then continue below.

## 2. Install Poetry

[Poetry](https://python-poetry.org/) is the tool this project uses to install the exact right
versions of all the libraries it depends on (numpy, pandas, matplotlib, etc.), so that "it works
on my machine" also means it works on yours.

**macOS / Linux** — open a terminal and run:

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

**Windows** — open PowerShell and run:

```powershell
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -
```

Then close and reopen your terminal, and check it worked:

```bash
poetry --version
```

If you get "command not found", Poetry was installed but isn't on your PATH yet. The installer
prints the folder it was installed to (usually `~/.local/bin` on macOS/Linux, or
`%APPDATA%\Python\Scripts` on Windows) — add that folder to your PATH, or restart your computer,
then try again.

## 3. Get the code

If you're comfortable with git:

```bash
git clone <this-repo-url>
cd Seeing_Project
```

Otherwise, on the repo's GitHub page click the green **Code** button → **Download ZIP**, then
unzip it and open a terminal in that folder.

## 4. Install the project's dependencies

From inside the project folder, run:

```bash
poetry install
```

This creates an isolated environment (so it doesn't interfere with anything else on your
computer) and installs everything listed in `pyproject.toml` at the exact versions recorded in
`poetry.lock`. The first run downloads a few hundred MB (mainly matplotlib and the ecCodes/GRIB
libraries) and can take a few minutes depending on your internet connection; later runs are fast.

## 5. Check it worked

Run the small self-contained example — it doesn't need any downloaded weather data:

```bash
poetry run python "Model Masciardi et al 2001.py"
```

You should see a line like:

```
C_n^2: 1.877e-12 m^(-2/3)
```

If you see that, your setup is correct.

## 6. Configure the scripts for your location

- **Data folder** — all three scripts (the downloader and both calculation scripts) take the
  data folder as an optional command-line argument, and default to the **current directory** if
  you don't pass one. Pick a folder to hold the (potentially large) downloaded GRIB2 files, and
  pass the same folder to the downloader and whichever calculation script you use — see step 7
  for examples.
- **`LAT_SITE` / `LON_SITE`** — the latitude/longitude of the observing site you care about is
  still a value you edit directly in the calculation script you're using. Several examples are
  given as commented-out lines above the active one; uncomment the one you want (or add your own)
  and comment out the rest.

## 7. Run it

Order matters — download the data first, then run a calculation script. Pass the same folder to
both so the calculation script finds the files the downloader just saved. For example, to keep
everything in a folder called `AROME_download` next to the scripts:

```bash
poetry run python "telecharger_arome_meteofetch_TKE_cisaillement_HCOULIM_v3.py" AROME_download
poetry run python "calcul_seeing_arome_2_modeles_V11_optimise.py" AROME_download
```

(Quoting the filenames is needed because some of them contain spaces.)

If you omit the folder argument, both scripts use the current directory — fine for a quick test,
but the downloaded GRIB2 files will land right next to the source code, so a dedicated folder
(as above) is recommended. Run `poetry run python "<script>" --help` on any of the three scripts
to see its argument description.

Each calculation script prints its progress in the terminal, writes a CSV file of results (in
the same folder as the GRIB2 data) and pops up a matplotlib window with several diagnostic plots
(wind, temperature, TKE, Cn², and the resulting seeing over the forecast period).

## Troubleshooting

- **`RuntimeError: Cannot find the ecCodes library`** — this means the `eccodes`/`eccodeslib`
  packages didn't install correctly. Re-run `poetry install`; if it persists, delete the
  environment and retry: `poetry env remove --all && poetry install`.
- **`poetry install` seems stuck / very slow** — the first install downloads matplotlib, numpy,
  pandas and the ecCodes binaries (~200-300 MB total). Just let it finish; subsequent installs
  are cached and much faster.
- **No plot window appears** — this happens if you're running on a remote server or inside a
  container without a graphical display. The scripts still write their CSV output even without
  a display; run them on a regular desktop/laptop to see the plots.
- **File not found for the AROME GRIB2 files** — make sure you ran the download script first, and
  that you passed the same folder argument to both the download script and the calculation
  script you're using (or omitted it consistently, so both default to the current directory).
