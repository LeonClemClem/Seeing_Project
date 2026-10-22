#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mise a jour complete apres un releve (demande utilisateur du 09/10 : a chaque nouveau releve,
inclure les mesures dans les graphiques et relancer la correlation).

1. Releve des 5 seeing monitors :
   - Copernic, ROSA (Drome), Saint-Veran : claude/releve-seeing-3-sites.ps1
   - OHP, Seeing monitor 5 (Miratlas)           : claude/releve_miratlas_ohp_sm5.py 3
2. Figures refaites avec toutes les mesures, SANS changer les coefficients :
   historique_sites.png, correlation_sites.png, correlation_sites_V2.png, prevision_<run>.png
3. Correlations affichees par site (V2 et V1).

Usage : python maj_mesures_figures.py [--sans-releve]
"""
from pathlib import Path
import sys as _sys; _sys.path.insert(0, str(Path(__file__).resolve().parent))  # chemins.py est a cote
from chemins import CACHE
import importlib.util
import subprocess
import sys

V2 = Path(__file__).resolve().parent
CLAUDE = V2   # dossier a plat : collecteurs a cote des scripts (original : Documents/claude)
PY = sys.executable


def _load(name):
    spec = importlib.util.spec_from_file_location(name, V2 / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def releve():
    print("=== Releve Copernic, ROSA, Saint-Veran")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(CLAUDE / "releve-seeing-3-sites.ps1")], check=False)
    print("=== Releve OHP, Seeing monitor 5 (Miratlas)")
    subprocess.run([PY, str(CLAUDE / "releve_miratlas_ohp_sm5.py"), "3"], check=False)


def figures():
    print("=== Figures (coefficients inchanges)")
    h = _load("historique_sites")
    h.calibrate = lambda *a, **k: None                      # pas de recalage automatique
    h.COEFF_FILE = CACHE / "coeff_non_ecrit.json"
    h.main()
    _load("prevision_sites").main()


if __name__ == "__main__":
    if "--sans-releve" not in sys.argv:
        releve()
    figures()
