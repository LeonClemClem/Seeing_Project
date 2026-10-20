#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calcul complet d'un run AROME pour tous les sites, V2 ET V1 en une seule passe
(demande utilisateur du 09/10). Chaque fichier GRIB n'est lu qu'UNE fois par point :
les lectures sont mises en commun entre la V2 (script principal), les integrales de
validation (K = 1) et la V1.

Pour chaque site (et, pour Copernic, les deux mailles : ancienne et position utilisateur) :
  1. V2 : integrales a K = 1 -> cache_validation/<run>__<site>__<lat>_<lon>__H51.csv
         (meme format que validation_sites.compute_components ; seulement au point COORDS)
  2. V1 : integrales a K = 1 -> cache_validation/v1/<run>__<site>__V1.csv (seulement au point COORDS)
  3. Panneaux : profils V2 aux K actuels (+ couches convectives, Cn2 BL / cisaillement)
         -> cache_validation/panneaux/pan_<site>_<maille>_<run>.pkl, et figure des 9 panneaux
         previsions/panneaux_<site>_<maille>_<run>.png (Copernic : mediane des deux mailles)

Usage :  python calcul_run.py <dossier du run> [site ...]      (un processus par site conseille)
Ensuite : python figures_run.py <run_court> [<run_court> ...]   (figure Cn2, prevision collee, historique)
"""
from pathlib import Path
import sys as _sys; _sys.path.insert(0, str(Path(__file__).resolve().parent))  # chemins.py est a cote
from chemins import CACHE, PREVISIONS
import contextlib, importlib.util, io, pickle, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

V2 = Path(__file__).resolve().parent
SCRIPT_V2 = V2 / "SeeingAromeV2_correction_conv_tke.py"
OUT = PREVISIONS
PAN = CACHE / "panneaux"
FORECAST_HOURS = 51
# Copernic : deux mailles (09/10) ; la position COORDS de historique_sites sert aux caches V1/V2
MAILLES_COPERNIC = {"ancienne": (44.5828, 5.9868), "nouvelle": (44.56179, 5.99762)}
# variables lues une fois par paquet (union des besoins V2 et V1)
VARIABLES = {"HP1": {"t", "u", "v", "10u", "10v", "pres"}, "HP2": {"tke"}, "IP1": {"t", "u", "v", "z"},
             "IP4": {"tke"}, "SP2": {"blh", "h_coulim"}, "SP3": {"sshf"}}
TYPES = {"IP1": {"isobaricInhPa"}, "IP4": {"isobaricInhPa"}, "SP2": {"surface"}}


def _load(path, nom):
    s = importlib.util.spec_from_file_location(nom, path)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


class Lecteur:
    """Lecture GRIB memorisee pour un point : chaque fichier lu une fois avec toutes les variables utiles."""

    def __init__(self, lat, lon):
        self.m = _load(SCRIPT_V2, "lecteur_v2")
        self.m.LAT_SITE, self.m.LON_SITE = lat, lon
        self.memo = {}

    def __call__(self, path, variables, allowed_types=None):
        path = Path(path)
        paquet = path.name.split("__")[2]
        cle = path.name
        if cle not in self.memo:
            self.memo[cle] = self.m.read_grib_package(path, VARIABLES.get(paquet, set(variables)), TYPES.get(paquet))
        data, la, lo = self.memo[cle]
        sous = {st: {v: lv for v, lv in d.items() if v in variables} for st, d in data.items()}
        return sous, la, lo


def branche(module, lecteur, run, lat, lon):
    module.DATA_DIR, module.LAT_SITE, module.LON_SITE, module.FORECAST_HOURS = Path(run), lat, lon, FORECAST_HOURS
    module.read_grib_package = lecteur
    return module


def panneaux(h, nom, etiq, run, lat, lon, lecteur, figure=True):
    """Profils V2 aux K actuels + masques convectifs (pickle) ; figure des 9 panneaux si figure=True."""
    K = h.SITES[nom]["K_new"]
    if h.est_jour_nuit(K):      # jeux jour / nuit : profils calcules avec le jeu de nuit (remis a l'echelle ensuite par heure)
        K = tuple(K["nuit"])
    m = branche(_load(SCRIPT_V2, "m_pan"), lecteur, run, lat, lon)
    m.K_TKE, m.K_CIS, m.K_TKE_CONV = K
    pris, dernier, conv = {}, {}, []
    orig_fig, f_tke, f_see = m.make_one_figure, m.calculate_cn2_tke, m.calculate_seeing

    def fig(r, df, ref):
        pris.update(r=r, df=df, ref=ref)
        if figure:
            orig_fig(r, df, ref)

    def tke(profile):
        r = f_tke(profile); dernier["cn2"] = np.array(r["Cn2"], float, copy=True); return r

    def see(z, bl, fa, hc):
        z = np.asarray(z, float); avant = dernier.get("cn2", np.full_like(z, np.nan))
        conv.append({"z": z.copy(), "conv": np.isfinite(bl) & ~np.isfinite(avant) & (z <= hc),
                     "trou": ~np.isfinite(np.where(z <= hc, bl, fa)), "cn2_tke": avant.copy(),
                     "cn2_bl": np.asarray(bl, float).copy(), "cn2_fa": np.asarray(fa, float).copy(), "h_coulim": float(hc)})
        return f_see(z, bl, fa, hc)

    m.make_one_figure, m.calculate_cn2_tke, m.calculate_seeing = fig, tke, see
    court = Path(run).name.replace("AROME_download_", "")
    out = OUT / f"panneaux_{nom}_{etiq}_{court}.png"
    m.plt.show = lambda *a, **k: (plt.gcf().suptitle(f"{nom} - maille {etiq} ({lat:.5f} N, {lon:.5f} E) - K = {K}",
                                                      y=0.995, fontsize=12), plt.gcf().savefig(out, dpi=110))
    to_csv = pd.DataFrame.to_csv; pd.DataFrame.to_csv = lambda *a, **k: None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            m.main()
    finally:
        pd.DataFrame.to_csv = to_csv
        plt.close("all")
    pris.update(conv=conv, K=tuple(K), point=(lat, lon))
    PAN.mkdir(parents=True, exist_ok=True)
    pickle.dump(pris, open(PAN / f"pan_{nom}_{etiq}_{court}.pkl", "wb"))
    return out if figure else None


def calcule_site(nom, run):
    h = _load(V2 / "historique_sites.py", "historique_sites")
    v = _load(V2 / "validation_sites.py", "validation_sites")
    v1 = _load(V2 / "seeing_v1_sites.py", "seeing_v1_sites")
    points = MAILLES_COPERNIC if nom == "Copernic" else {"site": h.COORDS[nom]}
    for etiq, (lat, lon) in points.items():
        lec = Lecteur(lat, lon)
        au_point_coords = np.allclose((lat, lon), h.COORDS[nom])
        if au_point_coords:
            # V2 : integrales a K = 1 (cache de validation)
            v.load_seeing_module = lambda: branche(_load(SCRIPT_V2, "m_val"), lec, run, lat, lon)
            v.compute_components({"nom": h.SITES[nom]["cache_tag"], "lat": lat, "lon": lon, "K": h.SITES[nom]["K_new"],
                                  "forecast_hours": FORECAST_HOURS}, Path(run))
            # V1 : integrales a K = 1
            def v1_mod():
                m1 = v1._load_v1.__wrapped__() if hasattr(v1._load_v1, "__wrapped__") else _load(v1.V1_SCRIPT, "m_v1")
                m1.read_grib_package = lec
                return m1
            v1._load_v1 = v1_mod
            v1.compute_v1(nom, h.SITES[nom]["cache_tag"], lat, lon, Path(run))
        panneaux(h, nom, etiq, run, lat, lon, lec, figure=(nom != "Copernic"))
        print(f"{nom} {etiq} : V2{' + V1' if au_point_coords else ''} + panneaux OK ({len(lec.memo)} fichiers lus une fois)")


if __name__ == "__main__":
    run = Path(sys.argv[1])
    sites = sys.argv[2:] or list(_load(V2 / "historique_sites.py", "historique_sites").SITES)
    for nom in sites:
        calcule_site(nom, run)
