#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prevision de seeing AROME pour les sites, sur tout un run.

- Run : par defaut le plus recent des dossiers de ARUNS_DIR qui est complet
  et coherent (les 6 paquets HP1 HP2 IP1 IP4 SP2 SP3, un seul run, aucun
  fichier vide). Sinon, fixer RUN_DIR.
- Calcul : validation_sites.compute_components (integrales a K = 1, en cache).
- Coefficients et mesures : ceux de historique_sites.py (SITES, K_AFFICHES,
  toutes les sources de mesures), pour rester coherent avec l'historique.
- Figure : AROME en bleu, mesures en orange (brutes + mediane horaire),
  nuits en gris (Soleil sous -12 deg), resume des nuits dans le titre.
Sorties : previsions/prevision_<run>.png et .csv
"""
from pathlib import Path
import importlib.util
import re

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

V2 = Path(__file__).resolve().parent
ARUNS_DIR = Path("C:/Users/clement/Documents/Seeing_project/modele/Arome_runs")
OUT_DIR = Path("C:/Users/clement/Documents/Seeing_project/modele/previsions")
RUN_DIR = None                  # None : dernier run complet ; sinon Path(".../AROME_download_...")
FORECAST_HOURS = 51
PAQUETS = ("HP1", "HP2", "IP1", "IP4", "SP2", "SP3")
# Coordonnees des sites, nuit (est_nuit : 17h30-06h00 TU) : definis dans historique_sites.py


def _load(name):
    spec = importlib.util.spec_from_file_location(name, V2 / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_complet(d):
    """Run unique, 6 paquets presents, aucun fichier vide -> horodatage du run, sinon None."""
    files = list(d.glob("arome__0025__*.grib2"))
    runs = {re.search(r"__(\d{4}-\d\d-\d\dT\d\d)-", f.name).group(1) for f in files if re.search(r"__(\d{4}-\d\d-\d\dT\d\d)-", f.name)}
    paquets = {f.name.split("__")[2] for f in files}
    if len(runs) != 1 or not set(PAQUETS) <= paquets or any(f.stat().st_size == 0 for f in files):
        return None
    return pd.Timestamp(runs.pop())


def choisir_run():
    if RUN_DIR is not None:
        return Path(RUN_DIR), run_complet(Path(RUN_DIR))
    candidats = [(run_complet(d), d) for d in ARUNS_DIR.iterdir() if d.is_dir() and not d.name.startswith("_")]
    candidats = [(t, d) for t, d in candidats if t is not None]
    if not candidats:
        raise FileNotFoundError(f"Aucun run complet et coherent dans {ARUNS_DIR}")
    t, d = max(candidats)
    return d, t


def main():
    v, h = _load("validation_sites"), _load("historique_sites")
    COORDS, NUIT_SOLEIL_DEG, sun_elevation = h.COORDS, h.NUIT_SOLEIL_DEG, h.sun_elevation
    v1m = _load("seeing_v1_sites")
    run_dir, run_t = choisir_run()
    print(f"Run : {run_dir.name}  ({run_t:%d/%m/%Y %H} TU)")
    bg = "#fcfcfb"
    fig, axes = plt.subplots(len(h.SITES), 1, figsize=(12, 3.8 * len(h.SITES)), dpi=120, sharex=True)
    fig.patch.set_facecolor(bg)
    rows = []
    for ax, (nom, cfg) in zip(axes, h.SITES.items()):
        lat, lon = COORDS[nom]
        cle_K, K = h.coefficients(nom)
        site = {"nom": nom, "lat": lat, "lon": lon, "K": K, "forecast_hours": FORECAST_HOURS}
        comp = v.compute_components(site, run_dir)
        s = v.arome_seeing(comp, K)
        for t, val, hc in zip(comp.t, s, comp.H_COULIM):
            rows.append({"site": nom, "datetime_utc": t, "H_COULIM_m": hc, "seeing_arcsec": val, "modele": "V2",
                         "K": f"{K[0]:g}/{K[1]:g}/{K[2]:g}"})

        ax.set_facecolor(bg)
        fine = pd.date_range(comp.t.min(), comp.t.max(), freq="10min")
        nuit_fine = h.est_nuit(fine)
        ax.fill_between(fine, 0, 1, where=nuit_fine, transform=ax.get_xaxis_transform(), color=h.COULEUR_NUIT, lw=0, zorder=0)

        o = h.observations(nom)
        o = h.filtre_sequences(o[(o.t >= comp.t.min()) & (o.t <= comp.t.max())])   # regle des 3 h dans la fenetre du run
        if len(o):
            ax.plot(o.t, o.seeing, lw=0, marker="o", ms=2.5, color=h.COULEUR_MESURES, alpha=0.35,
                    label=f"Mesures brutes ({len(o)})")
            th, mh, gh = h.hourly_median(o)
            h.plot_line(ax, th, mh, gh, color=h.COULEUR_MESURES, lw=1.8, marker="s", ms=4,
                        label=f"Mediane horaire (>= {h.HORAIRE_MIN_POINTS} mesures)")
        else:
            ax.plot([], [], lw=0, label="Pas de mesure sur la periode")
        ax.plot(comp.t, s, color=h.COULEUR_AROME, lw=2, marker="o", ms=4,
                label=f"AROME V2 ({h.NOMS_K[cle_K]}, voir encadre)")
        if h.TRACER_V1:
            d1 = v1m.compute_v1(nom, h.SITES[nom]["cache_tag"], lat, lon, run_dir)
            s1 = v1m.seeing_v1(d1, h.K_V1[nom], h.seeing_arcsec)
            ax.plot(d1.t, s1, color=h.COULEUR_V1, ls="--", lw=1.6, marker="^", ms=4, label="AROME V1 (sans convection)")
            for t, val in zip(d1.t, s1):
                rows.append({"site": nom, "datetime_utc": t, "seeing_arcsec": val, "modele": "V1",
                             "K": f"{h.K_V1[nom][0]:g}/{h.K_V1[nom][1]:g}"})

        nuit = pd.Series(s, index=comp.t)[h.est_nuit(comp.t)]
        txt = "   ".join(f"nuit du {d:%d/%m} : mediane {g.median():.1f}\", min {g.min():.1f}\""
                         for d, g in nuit.groupby((nuit.index - pd.Timedelta(hours=12)).date) if g.notna().any())
        ax.set_title(f"{nom}   {txt}", loc="left", fontsize=10.5)
        ax.set_ylabel("Seeing [arcsec]")
        ax.set_ylim(0, ax.get_ylim()[1] * 1.3)          # place pour la legende et l'encadre
        ax.grid(axis="y", color="#e4e3df", lw=0.8)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.legend(frameon=False, loc="upper left", fontsize=8, ncol=3)
        h.encadre_K(ax, nom, K, complet=False, v1_trace=h.TRACER_V1)   # seulement les K des courbes tracees
    # Graduation a chaque heure ; heure ecrite aux heures paires, date a 00 h
    # (meme style que la figure a 9 panneaux du script principal).
    heures = pd.date_range(comp.t.min(), comp.t.max(), freq="1h")
    etiquettes = ["" if t.hour % 2 else (t.strftime("%d/%m %Hh") if t.hour == 0 else t.strftime("%Hh")) for t in heures]
    for ax in axes:
        ax.set_xticks(heures)
        ax.set_xticklabels(etiquettes, rotation=90, fontsize=7)
        ax.tick_params(axis="x", labelbottom=True)
    axes[-1].set_xlabel(f"TU  (gris : {h.NUIT_TEXTE})")
    fig.suptitle(f"Prevision de seeing AROME - run du {run_t:%d/%m/%Y %H} TU", x=0.01, y=0.998, ha="left", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    png = OUT_DIR / f"prevision_{run_t:%Y-%m-%d_%H}Z.png"
    fig.savefig(png)
    pd.DataFrame(rows).to_csv(png.with_suffix(".csv"), index=False, float_format="%.3f")
    print(png)
    print(png.with_suffix(".csv"))


if __name__ == "__main__":
    main()
