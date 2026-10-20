# Website mock-up (static HTML)

`index.html` is a clickable mock-up of the planned website: global map, forecast, fisheye, calibration,
sites and account pages. Most pages use **fake data**; the *Mes lieux*, *Prévision* (public sites and "mon lieu")
and *Calibrer* (public sites) pages use **real data** from the monitored sites.

Published preview: https://claude.ai/artifact/VgVjJzRK53fqRBMTfuNiMU

## Real data file (not versioned)

The real data live in `lieux_data.js`, which is **not committed** (measurement data, about 1.5 MB, rebuilt
from the caches). Generate it with:

```bash
cd research
python export_lieux_site.py            # writes ../apps/maquette/lieux_data.js
```

It needs the data folders configured in `research/chemins_locaux.json` (see `research/chemins.py`): AROME
caches (`cache_validation/`, including the `panneaux/` pickles written by `calcul_run.py`) and the seeing
monitor measurements. Without the file, the real-data pages show an empty state.

Open `index.html` through a local web server (the data file is loaded as a script):

```bash
python -m http.server 8765 --directory apps/maquette
```
