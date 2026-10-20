#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chemins des donnees, propres a chaque machine.

Les scripts de research/ ne contiennent plus de chemins absolus : ils importent ce module.
Chaque personne cree a cote un fichier chemins_locaux.json (NON versionne, voir
chemins_locaux.exemple.json) qui indique ou sont ses donnees. Sans ce fichier, tout est
cherche dans le dossier donnees/ a la racine du depot (lui aussi non versionne).

Une variable d'environnement SEEING_<CLE> (ex. SEEING_AROME_RUNS) l'emporte sur le fichier.
"""
from pathlib import Path
import json
import os

RESEARCH = Path(__file__).resolve().parent          # dossier des scripts
_LOCAL = RESEARCH / "chemins_locaux.json"
_CFG = json.loads(_LOCAL.read_text(encoding="utf-8")) if _LOCAL.exists() else {}


def _chemin(cle, defaut):
    return Path(os.environ.get("SEEING_" + cle.upper(), _CFG.get(cle, defaut))).expanduser()


DONNEES = _chemin("donnees", RESEARCH.parent / "donnees")
AROME_RUNS = _chemin("arome_runs", DONNEES / "Arome_runs")      # dossiers AROME_download_<date>_<HH>Z
CACHE = _chemin("cache", DONNEES / "cache_validation")          # integrales K = 1, panneaux, carte, ciel
PREVISIONS = _chemin("previsions", DONNEES / "previsions")      # figures et CSV de prevision
TESTS = _chemin("tests", DONNEES / "tests")                     # validations et mesures ponctuelles
MESURES = _chemin("mesures", DONNEES / "mesures")               # seeing-rosa/, seeing-copernic/, seeing-saint-veran/,
                                                                # seeing-miratlas/, releves/
MESURES_V1 = _chemin("mesures_v1", DONNEES / "V1")              # anciens fichiers de mesures (Saint-Veran 18/09)
