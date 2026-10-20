"""Prevision de seeing collee sur plusieurs runs (le plus recent l'emporte), V2 et V1, avec les mesures.
Utilise les calculs en cache (aucune lecture de GRIB). Usage : python prevision_collee.py <run_dir1> <run_dir2> ..."""
import importlib.util, sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

spec = importlib.util.spec_from_file_location("h", r"C:\Users\clement\Documents\Seeing_project\modele\code\V2\historique_sites.py")
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
h.SITES = {n: c for n, c in h.SITES.items() if n not in getattr(h, "SITES_HORS_PREVISION", set())}   # 13/10 : Pic du Midi retire (pas de mesures recentes)
v1m = h.v1()
RUNS = sys.argv[1:]
OUT = Path(r"C:\Users\clement\Documents\Seeing_project\modele\previsions")
bg = "#fcfcfb"
fig, axes = plt.subplots(len(h.SITES), 1, figsize=(14, 3.8 * len(h.SITES)), dpi=110, sharex=True)
fig.patch.set_facecolor(bg)
for ax, nom in zip(axes, h.SITES):
    K = h.SITES[nom]["K_new"]
    f = h.forecasts_site(nom); f = f[f.run_dir.isin(RUNS)].sort_values("t")
    f1 = h.forecasts_v1_site(v1m, nom)
    f1 = f1[f1.t.isin(f.t)] if f1 is not None else None
    s = h.arome(f, K)[1]
    ax.set_facecolor(bg)
    fine = pd.date_range(f.t.min(), f.t.max(), freq="10min")
    ax.fill_between(fine, 0, 1, where=h.est_nuit(fine), transform=ax.get_xaxis_transform(), color=h.COULEUR_NUIT, lw=0, zorder=0)
    o = h.observations(nom)
    o = h.filtre_sequences(o[(o.t >= f.t.min()) & (o.t <= f.t.max())])
    if len(o):
        # 14/10 : mesures non utilisees par le calage (jour, hors plage) en gris
        h.trace_mesures(ax, nom, o.t, o.seeing, par_heure=True, lw=0, marker="o", ms=2.5, alpha=0.35, zorder=10, label=f"Mesures brutes ({len(o)})")
        th, mh, gh = h.hourly_median(o)
        hors_h = h.non_cale(nom, th, mh)
        h.plot_line(ax, th, np.where(hors_h, np.nan, mh), gh, color=h.COULEUR_MESURES, lw=1.8, marker="s", ms=4, zorder=11, label="Mediane horaire")
        if np.any(hors_h):
            h.plot_line(ax, th, np.where(hors_h, mh, np.nan), gh, color=h.COULEUR_NON_CALE, lw=1.8, marker="s", ms=4, zorder=11,
                        label="Non utilise pour le calage (jour, hors plage)")
    else:
        ax.plot([], [], lw=0, label="Pas de mesure sur la periode")
    gap = (f.t.diff() > pd.Timedelta(hours=1)).values
    h.plot_line(ax, f.t, s, gap, color=h.COULEUR_AROME, lw=2, marker="o", ms=3.5, label=f"AROME {h.nom_v2()}")
    exclues = h.heures_hors_plage(nom, th, mh) if len(o) else pd.DatetimeIndex([])   # 14/10 : previsions des heures exclues en gris
    h.grise_previsions(ax, f.t, s, exclues)
    for mod_a, coul_a, f0, Ka in h.autres_modeles(nom):   # 15/10 : V2 d'origine et V2b, chacune avec ses K
        f0 = f0[f0.run_dir.isin(RUNS)].sort_values("t")
        h.plot_line(ax, f0.t, h.arome(f0, Ka)[1], (f0.t.diff() > pd.Timedelta(hours=1)).values, color=coul_a, ls=":",
                    lw=1.5, marker=".", ms=3, label=f"AROME {mod_a} (ses K)")
    if f1 is not None and len(f1):
        s1 = h.seeing_v1_k(v1m, f1, h.K_V1[nom])
        ax.plot(f1.t, s1, color=h.COULEUR_V1, ls="--", lw=1.5, marker="^", ms=3.5,
                label="AROME V1 (sans convection)")
        h.grise_previsions(ax, f1.t, s1, exclues, marker="^")
    # changement de run
    for j, r in enumerate(RUNS[1:]):
        t0 = f.loc[f.run_dir == r, "t"].min()
        if pd.notna(t0):
            ax.axvline(t0, color="#52514e", lw=1, ls=":")
            ax.text(t0, 0.80 - 0.09 * j, f" run {r.replace('AROME_download_', '')}", transform=ax.get_xaxis_transform(),
                    fontsize=7.5, va="top", color="#52514e")   # etiquettes decalees (pas de chevauchement)
    nuit = pd.Series(s, index=f.t)[h.est_nuit(f.t)]
    txt = "   ".join(f"nuit du {d:%d/%m} : mediane {g.median():.1f}\", min {g.min():.1f}\""
                     for d, g in nuit.groupby((nuit.index - pd.Timedelta(hours=12)).date) if g.notna().any())
    ax.set_title(f"{nom}   {txt}", loc="left", fontsize=10.5)
    ax.set_ylabel("Seeing [arcsec]")
    ax.set_ylim(0, max(np.nanmax(s), np.nanmax(mh) if len(mh) else (np.nanmax(o.seeing) if len(o) else 0)) * 1.3)
    ax.grid(axis="y", color="#e4e3df", lw=0.8); ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.legend(frameon=False, loc="upper left", fontsize=8, ncol=4)
    h.encadre_K(ax, nom, K, complet=False, v1_trace=True)
heures = pd.date_range(f.t.min().ceil("1h"), f.t.max(), freq="1h")
for ax in axes:
    ax.set_xticks(heures)
    ax.set_xticklabels(["" if x.hour % 2 else (f"{x:%d/%m %Hh}" if x.hour == 0 else f"{x:%Hh}") for x in heures], rotation=90, fontsize=7)
    ax.tick_params(axis="x", labelbottom=True)
axes[-1].set_xlabel(f"TU  (gris : {h.NUIT_TEXTE} ; pointilles : changement de run)")
fig.suptitle("Prevision de seeing AROME - runs colles : " + " + ".join(r.replace("AROME_download_", "") for r in RUNS),
             x=0.01, y=0.998, ha="left", fontsize=13)
fig.tight_layout(rect=(0, 0, 1, 0.985))
out = OUT / f"prevision_collee_{RUNS[-1].replace('AROME_download_', '')}.png"
fig.savefig(out)
print(out)
