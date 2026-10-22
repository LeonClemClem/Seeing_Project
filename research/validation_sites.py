#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validation du seeing AROME contre les seeing monitors.

Principe :
- Le calcul physique est celui de SeeingAromeV2_correction_conv_tke.py,
  importe comme une bibliotheque (le fichier n'est pas modifie).
- Pour chaque site, le script lance ce calcul avec K_TKE = K_CIS =
  K_TKE_CONV = 1 et recupere a chaque echeance les trois integrales de Cn2
  (TKE, convection, cisaillement). Le Cn2 etant lineaire en chaque K :
      int Cn2 = K_TKE*I_tke + K_TKE_CONV*I_conv + K_CIS*I_cis
  le seeing de n'importe quel jeu de K s'obtient sans relancer AROME.
- Les integrales sont mises en cache (dossier CACHE_DIR) : le second
  lancement est immediat.
- Mesures : points bruts + mediane glissante (5 points centres,
  min_periods=1 : aucun point perdu, ni aux extremites ni dans les petits
  groupes isoles) pour les figures. Statistiques selon REFERENCE : mediane
  horaire centree (+/-30 min, par defaut, echelle d'une valeur AROME),
  tendance (mediane glissante sur TENDANCE_HEURES, qui ignore les pics locaux)
  ou mediane glissante a 5 points.
- Tout est en TU.

Sorties (dans OUTPUT_DIR) : figure PNG (un panneau par site) et CSV des
statistiques.
"""
from pathlib import Path
import sys as _sys; _sys.path.insert(0, str(Path(__file__).resolve().parent))  # chemins.py est a cote
from chemins import AROME_RUNS, CACHE, TESTS, MESURES
import contextlib
import importlib.util
import io
import re

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ============================================================================
# CONFIGURATION
# ============================================================================
SEEING_SCRIPT = Path(__file__).resolve().parent / "SeeingAromeV2_correction_conv_tke.py"
RUN_DIR = AROME_RUNS / "AROME_download_2509_16h"
CACHE_DIR = CACHE
OUTPUT_DIR = TESTS

# utc_offset_h : heures a retirer pour passer en TU (0 si deja en TU,
# 2 pour l'heure locale d'ete, 1 pour l'heure locale d'hiver).
# K = (K_TKE, K_CIS, K_TKE_CONV).
SITES = [
    {
        "nom": "Drôme",
        "lat": 44.3814, "lon": 5.4286,
        "K": (8, 40, 0.1),
        "forecast_hours": 19,
        "obs_csv": MESURES / "seeing-rosa/seeing_rosa_2026-09-26_UTC.csv",
        "col_temps": "datetime_utc", "col_seeing": "seeing_brut_arcsec", "utc_offset_h": 0,
    },
    {
        "nom": "Copernic",
        "lat": 44.5828, "lon": 5.9868,
        "K": (84, 126, 0.3),
        "forecast_hours": 19,
        "obs_csv": MESURES / "seeing-copernic/seeing_copernic_2026-09-25_UTC.csv",
        "col_temps": "datetime_utc", "col_seeing": "seeing_arcsec", "utc_offset_h": 0,
    },
    {
        "nom": "Saint-Veran",
        "lat": 44.6988, "lon": 6.9083,
        "K": (6, 12, 0.1),
        "forecast_hours": 51,
        "obs_csv": TESTS / "Saint_veran_2026-09-25_27_UTC_capture.csv",
        "col_temps": "datetime_utc", "col_seeing": "seeing_arcsec", "utc_offset_h": 0,
    },
]

MEDIANE_FENETRE = 5          # points de la mediane glissante (figures)
# Mesures comparees a AROME pour les statistiques :
#   "horaire"   : mediane des mesures sur +/-30 min autour de chaque echeance
#                 (echelle d'une valeur AROME : maille ~10 km, ~1 h d'advection),
#                 au moins HORAIRE_MIN_POINTS mesures dans l'heure ;
#   "tendance"  : mediane glissante sur TENDANCE_HEURES (ecarte les pics locaux) ;
#   "glissante" : mediane glissante a MEDIANE_FENETRE points.
REFERENCE = "horaire"
HORAIRE_MIN_POINTS = 5
# Tendance generale : mediane glissante sur une duree (heures), qui ignore les
# pics locaux plus courts que la moitie de la fenetre (4 h -> pics <= 2 h).
TENDANCE_HEURES = 4
LARGEUR_FIGURE = 12          # pouces ; 6 = axe horaire compresse de moitie
ECART_MAX_MIN = 10           # ecart max (min) entre echeance AROME et mesure
COUPURE_SEGMENT_MIN = 30     # trou de mesures qui separe deux segments
CALER_K = False              # True : recale aussi les K (erreur relative)
TITRE = "AROME vs seeing monitors"
NOM_FIGURE = "validation_sites.png"
NOM_STATS = "validation_sites_stats.csv"


# ============================================================================
# CALCUL AROME (integrales a K = 1)
# ============================================================================
def load_seeing_module():
    spec = importlib.util.spec_from_file_location("seeing_arome", SEEING_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compute_components(site, run_dir):
    """
    Integrales de Cn2 a K = 1 par echeance pour un site, lues dans le cache
    si elles existent deja. Colonnes : h, t, H_COULIM, has_tke, I_tke,
    I_conv, I_cis.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tag = re.sub(r"[^A-Za-z0-9]+", "_", site["nom"])
    cache = CACHE_DIR / f"{run_dir.name}__{tag}__{site['lat']:.4f}_{site['lon']:.4f}__H{site['forecast_hours']}.csv"
    if cache.exists():
        return pd.read_csv(cache, parse_dates=["t"])

    m = load_seeing_module()
    m.DATA_DIR = run_dir
    m.LAT_SITE, m.LON_SITE = site["lat"], site["lon"]
    m.FORECAST_HOURS = site["forecast_hours"]
    m.K_TKE = m.K_CIS = m.K_TKE_CONV = 1.0
    m.make_one_figure = lambda *a, **k: None

    state, rows = {}, []
    f_display, f_tke, f_seeing = m.build_display_profile, m.calculate_cn2_tke, m.calculate_seeing

    def display(*a):
        r = f_display(*a)
        state["has_tke"] = bool(np.any(np.isfinite(r["TKE"])))
        return r

    def tke(profile):
        r = f_tke(profile)
        state["raw"] = r["Cn2"].copy()          # avant fermeture convective
        return r

    def integral(z, cn2_bl, cn2_fa, h):
        value = f_seeing(z, cn2_bl, cn2_fa, h)[0]
        return value if np.isfinite(value) else 0.0

    def seeing(z, cn2_bl, cn2_fa, h):
        raw, none = state["raw"], np.full_like(cn2_bl, np.nan)
        from_tke = np.where(np.isfinite(raw), cn2_bl, np.nan)
        from_conv = np.where(~np.isfinite(raw) & np.isfinite(cn2_bl), cn2_bl, np.nan)
        rows.append({
            "h": len(rows), "H_COULIM": h, "has_tke": state["has_tke"],
            "I_tke": integral(z, from_tke, none, h),
            "I_conv": integral(z, from_conv, none, h),
            "I_cis": integral(z, none, cn2_fa, h),
        })
        return f_seeing(z, cn2_bl, cn2_fa, h)

    f_empty = m.empty_hour_result

    def empty(h_coulim=np.nan):
        # Echeance incomplete, non calculee par le script : ligne NaN.
        rows.append({"h": len(rows), "H_COULIM": h_coulim, "has_tke": False,
                     "I_tke": np.nan, "I_conv": np.nan, "I_cis": np.nan})
        return f_empty(h_coulim)

    m.build_display_profile, m.calculate_cn2_tke, m.calculate_seeing = display, tke, seeing
    m.empty_hour_result = empty

    # Le script ecrit son propre CSV dans le dossier du run : on l'en empeche.
    to_csv = pd.DataFrame.to_csv
    pd.DataFrame.to_csv = lambda *a, **k: None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            m.main()
    finally:
        pd.DataFrame.to_csv = to_csv

    cycle = m.get_grib_cycle_datetime(m.find_grib_files("HP1")[0])
    d = pd.DataFrame(rows)
    d.insert(1, "t", pd.Timestamp(cycle) + pd.to_timedelta(d.h, unit="h"))
    d.to_csv(cache, index=False, float_format="%.6e")
    return d


def seeing_arcsec(integral, lam=500e-9):
    """Meme formule que calculate_seeing (r0 puis seeing a 500 nm)."""
    integral = np.asarray(integral, dtype=float)
    k2 = (2.0 * np.pi / lam) ** 2
    out = np.full_like(integral, np.nan)
    ok = integral > 0
    r0 = (0.423 * k2 * integral[ok]) ** (-3.0 / 5.0)
    out[ok] = 0.98 * lam / r0 * 206265.0
    return out


def arome_seeing(comp, K):
    k_tke, k_cis, k_conv = K
    s = seeing_arcsec(k_tke * comp.I_tke + k_conv * comp.I_conv + k_cis * comp.I_cis)
    return np.where(comp.has_tke, s, np.nan)       # H+0 : pas de TKE


# ============================================================================
# MESURES
# ============================================================================
def load_observations(site):
    o = pd.read_csv(site["obs_csv"])
    t = pd.to_datetime(o[site["col_temps"]])
    if t.dt.tz is not None:
        t = t.dt.tz_convert("UTC").dt.tz_localize(None)
    o = pd.DataFrame({
        "t": t - pd.Timedelta(hours=site["utc_offset_h"]),
        "seeing": pd.to_numeric(o[site["col_seeing"]], errors="coerce"),
    }).dropna().sort_values("t").reset_index(drop=True)
    o["segment"] = (o.t.diff() > pd.Timedelta(minutes=COUPURE_SEGMENT_MIN)).cumsum()
    o["mediane"] = o.groupby("segment")["seeing"].transform(
        lambda x: x.rolling(MEDIANE_FENETRE, center=True, min_periods=1).median()
    )
    o["tendance"] = np.nan
    if TENDANCE_HEURES:
        for _, idx in o.groupby("segment").groups.items():
            seg = o.loc[idx].set_index("t")["seeing"]
            o.loc[idx, "tendance"] = seg.rolling(
                f"{TENDANCE_HEURES}h", center=True, min_periods=1
            ).median().values
    # Courbe utilisee pour la comparaison avec AROME (hors mode "horaire")
    o["reference"] = o["tendance"] if REFERENCE == "tendance" else o["mediane"]
    return o


def extract_copernic_svg(svg_path, nuit, utc_offset_h=2):
    """
    Releve les points d'un export SVG Highcharts de la page historique de
    Copernic (axe X categoriel : un point = une mesure, libelles horaires
    toutes les N mesures). `nuit` : date du debut de nuit (AAAA-MM-JJ).
    Retourne un DataFrame (datetime_utc, seeing_arcsec).
    """
    text = Path(svg_path).read_text(encoding="utf-8")
    grid = re.search(r'class="highcharts-grid highcharts-yaxis-grid"[^>]*>(.*?)</g>', text, re.S).group(1)
    grid_y = sorted({float(v) for v in re.findall(r'd="M\s*[\d.]+\s+([\d.]+)', grid)})
    tick_values = [float(v) for v in re.findall(
        r'<text[^>]*>([\d.]+)</text>',
        re.search(r'class="highcharts-axis-labels highcharts-yaxis-labels"[^>]*>(.*?)</g>', text, re.S).group(1))]
    series = re.search(r'class="highcharts-series highcharts-series-0[^"]*"[^>]*transform="translate\(([\d.]+),([\d.]+)\)[^"]*"[^>]*>\s*<path[^>]*\sd="([^"]*)"', text, re.S)
    off_x, off_y, path = float(series.group(1)), float(series.group(2)), series.group(3)
    pts = np.array([[float(a), float(b)] for a, b in re.findall(r"[ML]\s*([-\d.]+)\s+([-\d.]+)", path)])
    x, y = pts[:, 0], pts[:, 1] + off_y

    # axe Y : lignes de grille <-> graduations (de bas en haut)
    values = sorted(tick_values)[:len(grid_y)]
    a, b = np.polyfit(values, sorted(grid_y, reverse=True)[:len(values)], 1)
    seeing = (y - b) / a

    # axe X : libelles horaires aux indices 0, N, 2N...
    labels = re.findall(r'<text[^>]*rotate\(-45[^>]*>(\d\d:\d\d)</text>', text)
    step = np.median(np.diff(x))
    idx = np.round((x - x[0]) / step).astype(int)
    label_x = [float(v) for v in re.findall(r'<text x="([\d.]+)"[^>]*rotate\(-45', text)]
    every = int(round((label_x[1] - label_x[0]) / step))
    base = pd.Timestamp(nuit)
    times = []
    for lab in labels:
        hh, mm = map(int, lab.split(":"))
        ts = base + pd.Timedelta(hours=hh, minutes=mm)
        times.append(ts + pd.Timedelta(days=1) if hh < 12 else ts)
    tick_idx = np.arange(len(labels)) * every
    ns = np.array([t.value for t in times], dtype=float)
    rate = (ns[-1] - ns[0]) / tick_idx[-1]
    t_ns = np.where(idx <= tick_idx[-1], np.interp(idx, tick_idx, ns), ns[-1] + (idx - tick_idx[-1]) * rate)
    local = pd.to_datetime(t_ns.astype("int64"))
    return pd.DataFrame({
        "datetime_utc": local - pd.Timedelta(hours=utc_offset_h),
        "seeing_arcsec": np.round(seeing, 3),
    })


# ============================================================================
# COMPARAISON
# ============================================================================
def pair_with_observations(times, values, obs):
    """
    Valeur mesuree associee a chaque echeance AROME :
    - REFERENCE = "horaire" : mediane des mesures sur [t - 30 min, t + 30 min[,
      si au moins HORAIRE_MIN_POINTS mesures ;
    - sinon : courbe de reference au point le plus proche (<= ECART_MAX_MIN).
    """
    tt = obs.t.values
    out = []
    for t, v in zip(times, values):
        if not np.isfinite(v):
            continue
        if REFERENCE == "horaire":
            w = obs.seeing[(obs.t >= t - pd.Timedelta(minutes=30)) & (obs.t < t + pd.Timedelta(minutes=30))]
            if len(w) >= HORAIRE_MIN_POINTS:
                out.append((t, v, w.median()))
            continue
        i = int(np.argmin(np.abs(tt - np.datetime64(t))))
        if abs(tt[i] - np.datetime64(t)) <= np.timedelta64(ECART_MAX_MIN, "m"):
            out.append((t, v, obs.reference.iloc[i]))
    return pd.DataFrame(out, columns=["t", "arome", "mesure"])


def statistics(pairs):
    if len(pairs) < 3:
        return {"n": len(pairs), "biais": np.nan, "rmse": np.nan, "corr": np.nan, "err_rel_pct": np.nan}
    e = pairs.arome - pairs.mesure
    log_err = np.sqrt(np.mean(np.log(pairs.arome / pairs.mesure) ** 2))
    return {
        "n": len(pairs),
        "biais": e.mean(),
        "rmse": np.sqrt((e ** 2).mean()),
        "corr": np.corrcoef(pairs.arome, pairs.mesure)[0, 1],
        "err_rel_pct": 100.0 * (np.exp(log_err) - 1.0),
    }


def fit_K(comp, obs):
    """Recale (K_TKE, K_CIS, K_TKE_CONV) en minimisant l'erreur relative (log)."""
    pts = pair_with_observations(comp.t, np.where(comp.has_tke, 1.0, np.nan), obs)
    sub = comp.set_index("t").loc[pts.t]
    grid = np.logspace(-2, 3, 61)
    kt, kv = np.meshgrid(grid, grid, indexing="ij")
    best = (np.inf, None)
    for kc in np.logspace(-1, 4, 61):
        integ = kt[..., None] * sub.I_tke.values + kv[..., None] * sub.I_conv.values + kc * sub.I_cis.values
        s = seeing_arcsec(integ)
        err = np.sqrt(np.nanmean(np.log(s / pts.mesure.values) ** 2, axis=2))
        i = np.unravel_index(np.nanargmin(err), err.shape)
        if err[i] < best[0]:
            best = (err[i], (kt[i], kc, kv[i]))
    return best[1]


# ============================================================================
# FIGURE
# ============================================================================
def plot_sites(results, path):
    bg = "#fcfcfb"
    fig, axes = plt.subplots(len(results), 1, figsize=(LARGEUR_FIGURE, 4 * len(results)), dpi=120, squeeze=False)
    fig.patch.set_facecolor(bg)
    for ax, r in zip(axes[:, 0], results):
        obs, comp = r["obs"], r["comp"]
        ax.set_facecolor(bg)
        ax.plot(obs.t, obs.seeing, lw=0, marker="o", ms=2.5, color="#2a78d6", alpha=0.3, label="Mesures")
        for _, g in obs.groupby("segment"):
            ax.plot(g.t, g.mediane, color="#2a78d6", lw=2, marker="o" if len(g) < 3 else None, ms=4)
        ax.plot([], [], color="#2a78d6", lw=2, label=f"Mediane glissante ({MEDIANE_FENETRE} points)")
        if REFERENCE == "tendance":
            for _, g in obs.groupby("segment"):
                ax.plot(g.t, g.tendance, color="#4a3aa7", lw=2.5, ls=":")
            ax.plot([], [], color="#4a3aa7", lw=2.5, ls=":", label=f"Tendance ({TENDANCE_HEURES} h, comparee a AROME)")
        if REFERENCE == "horaire":
            p = pair_with_observations(comp.t, np.where(comp.has_tke, 1.0, np.nan), obs)
            ax.plot(p.t, p.mesure, lw=0, marker="s", ms=7, color="#4a3aa7", markeredgecolor=bg,
                    markeredgewidth=1.5, label="Mediane horaire (comparee a AROME)", zorder=6)
        lo, hi = obs.t.min() - pd.Timedelta(hours=1), obs.t.max() + pd.Timedelta(hours=1)
        show = (comp.t >= lo) & (comp.t <= hi)
        kt, kc, kv = r["K"]
        ax.plot(comp.t[show], r["arome"][show], color="#eb6834", lw=2, marker="o", ms=6,
                markeredgecolor=bg, markeredgewidth=1.5,
                label=f"AROME  K_TKE = {kt:g}   K_CIS = {kc:g}   K_conv = {kv:g}")
        if r.get("K_cale") is not None:
            kt2, kc2, kv2 = r["K_cale"]
            ax.plot(comp.t[show], r["arome_cale"][show], color="#1baf7a", lw=2, ls="--", marker="o", ms=5,
                    label=f"AROME  K cales : K_TKE = {kt2:.2g}   K_CIS = {kc2:.3g}   K_conv = {kv2:.2g}")
        st = r["stats"]
        etroite = LARGEUR_FIGURE < 9
        ax.set_title(f"{r['nom']}" + ("\n" if etroite else "   ") +
                     f"(n={st['n']}, biais {st['biais']:+.2f}\", RMSE {st['rmse']:.2f}\", "
                     f"corr {st['corr']:+.2f}, erreur rel. {st['err_rel_pct']:.0f} %)",
                     loc="left", fontsize=9 if etroite else 11)
        ax.set_xlim(lo, hi)
        ax.set_ylim(0, None)
        ax.set_ylabel("Seeing [arcsec]", color="#52514e")
        ax.grid(axis="y", color="#e4e3df", lw=0.8)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        court = (hi - lo) < pd.Timedelta(hours=36)
        if court:
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=2 if etroite else 1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Hh" if court else "%d/%m %Hh"))
        ax.legend(frameon=False, loc="upper right", fontsize=7 if etroite else 8.5, ncol=1 if etroite else 3)
    axes[-1, 0].set_xlabel("TU")
    fig.suptitle(TITRE, x=0.01, ha="left", fontsize=10 if LARGEUR_FIGURE < 9 else 13)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


# ============================================================================
# MAIN
# ============================================================================
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results, table = [], []
    for site in SITES:
        print(f"{site['nom']} : calcul AROME (ou cache)...")
        comp = compute_components(site, RUN_DIR)
        obs = load_observations(site)
        arome = arome_seeing(comp, site["K"])
        st = statistics(pair_with_observations(comp.t, arome, obs))
        r = {"nom": site["nom"], "comp": comp, "obs": obs, "K": site["K"], "arome": arome, "stats": st}
        row = {"site": site["nom"], "K_TKE": site["K"][0], "K_CIS": site["K"][1], "K_TKE_CONV": site["K"][2], **st}
        if CALER_K:
            K_cale = fit_K(comp, obs)
            r["K_cale"], r["arome_cale"] = K_cale, arome_seeing(comp, K_cale)
            st_c = statistics(pair_with_observations(comp.t, r["arome_cale"], obs))
            row.update({"K_TKE_cale": K_cale[0], "K_CIS_cale": K_cale[1], "K_TKE_CONV_cale": K_cale[2],
                        **{f"{k}_cale": v for k, v in st_c.items()}})
        results.append(r)
        table.append(row)
        print(f"   n={st['n']}  biais {st['biais']:+.2f}\"  RMSE {st['rmse']:.2f}\"  "
              f"corr {st['corr']:+.2f}  erreur relative {st['err_rel_pct']:.0f} %")

    pd.DataFrame(table).to_csv(OUTPUT_DIR / NOM_STATS, index=False, float_format="%.4g")
    plot_sites(results, OUTPUT_DIR / NOM_FIGURE)
    print(f"\nFigure       : {OUTPUT_DIR / NOM_FIGURE}")
    print(f"Statistiques : {OUTPUT_DIR / NOM_STATS}")


if __name__ == "__main__":
    main()
