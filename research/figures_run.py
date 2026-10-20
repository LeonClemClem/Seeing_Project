#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Figures apres un (ou plusieurs) run(s) calcule(s) par calcul_run.py, SANS relire les GRIB et sans recalage :
  - panneaux de Copernic : mediane des deux mailles (dernier run)
  - figure Cn2 par site, runs colles (seeing prevu V2 / observe, couches convectives, NaN)
  - prevision collee V2 + V1 avec les mesures
  - historique + correlations (V1 et V2)
Usage : python figures_run.py <run_court> [<run_court> ...]   ex. 2026-10-08_12Z 2026-10-09_12Z (ordre chronologique)
Si les K changent, relancer ce script suffit (Cn2 remis a l'echelle par zone, seeing des caches a K = 1).
"""
from pathlib import Path
import importlib.util, subprocess, sys

V2 = Path(__file__).resolve().parent
PY = sys.executable
runs = sys.argv[1:]
subprocess.run([PY, str(V2 / "panneaux_mediane.py"), runs[-1]], check=False)
subprocess.run([PY, str(V2 / "figure_cn2_sites.py"), *runs], check=False)
subprocess.run([PY, str(V2 / "prevision_collee.py"), *[f"AROME_download_{r}" for r in runs]], check=False)
s = importlib.util.spec_from_file_location("historique_sites", V2 / "historique_sites.py")
h = importlib.util.module_from_spec(s); s.loader.exec_module(h)
h.calibrate = lambda *a, **k: None                       # pas de recalage automatique
h.COEFF_FILE = V2 / "cache_validation" / "coeff_non_ecrit.json"
h.main()
