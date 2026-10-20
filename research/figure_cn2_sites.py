"""Figure Cn2 par site (run donne) : Cn2 (altitude x temps, log), H_COULIM, couches convectives (hachures),
seeing prevu V2 et seeing observe (brut + mediane horaire) superposes. Copernic : ancienne maille, nouvelle, mediane.
Signale aussi les NaN (seeing et Cn2). Usage : python figure_cn2_sites.py <run_court>  (ex. 2026-10-08_12Z)"""
import importlib.util, pickle, sys
from pathlib import Path
import sys as _sys; _sys.path.insert(0, str(Path(__file__).resolve().parent))  # chemins.py est a cote
from chemins import RESEARCH, PREVISIONS, CACHE
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["hatch.linewidth"] = 1.2
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.patches import Patch

SCR = CACHE / "panneaux"   # profils enregistres par calcul_run.py
OUT = PREVISIONS
run = sys.argv[1]
spec = importlib.util.spec_from_file_location("h", RESEARCH / "historique_sites.py")
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
h.SITES = {n: c for n, c in h.SITES.items() if n not in getattr(h, "SITES_HORS_PREVISION", set())}   # 13/10 : Pic du Midi retire (pas de mesures recentes)
ZMAX, DZ = 4000.0, 25.0
ZG = np.arange(10.0, ZMAX + DZ, DZ)
# K utilises lors du calcul des pickles du 09/10 (les nouveaux pickles contiennent "K")
K_CALCUL_09_10 = {"Drôme": (15.8, 11.2, 0.1), "Copernic": (1, 30, 0.1), "Saint-Veran": (6, 12, 0.1),
                  "OHP": (0.53, 32.6, 0.515), "Seeing monitor 5": (2.32, 65.5, 0.002)}
sm = importlib.util.spec_from_file_location("m", RESEARCH / "SeeingAromeV2_correction_conv_tke.py")
M = importlib.util.module_from_spec(sm); sm.loader.exec_module(M)
V1M = h.v1()     # modele V1 (caches), superpose a la V2


smb = importlib.util.spec_from_file_location("mb", RESEARCH / "SeeingAromeV2b_cisaillement_V1.py")
MB = importlib.util.module_from_spec(smb); smb.loader.exec_module(MB); MB.K_CIS = 1.0
DELTA_V2BD = 100.0


def profil_v2bd(p, i, hh, K0, K1):
    """15/10 : profil Cn2 V2bd aux K K1, depuis les termes enregistres (cn2_tke, cn2_bl, convection, profil meteo)."""
    cv = p["conv"][i]; r = p["r"][hh]; z = np.asarray(cv["z"], float); H = float(cv.get("h_coulim", r["H_COULIM"]))
    tke1 = np.nan_to_num(cv["cn2_tke"], nan=0.0) / K0[0]
    conv1 = (np.where(cv["conv"], np.nan_to_num(cv["cn2_bl"], nan=0.0), 0.0) / K0[2]) if K0[2] else np.zeros_like(z)
    full = {q: np.asarray(r[q], float) for q in ("z", "T", "U", "V", "P")}
    fab1 = np.interp(z, full["z"], np.nan_to_num(MB.cisaillement_v2b(full, H), nan=0.0))
    w = 0.5 * (1 - np.tanh((z - H) / DELTA_V2BD))
    c = w * (K1[0] * tke1 + K1[2] * conv1) + (1 - w) * K1[1] * fab1
    J = np.trapezoid(c, z)
    s = 0.98 * 500e-9 * (0.423 * (2 * np.pi / 500e-9) ** 2 * J) ** 0.6 * 206265 if J > 0 else np.nan
    return z, np.where(c > 0, c, np.nan), s


def recaler_K(p, nom):
    """Cn2 et seeing pour les K actuels (historique_sites.SITES), SANS relire les GRIB :
    Cn2 = K_TKE x (TKE) sous H_COULIM hors convection, K_conv x (convection) dans les couches convectives,
    K_CIS x (cisaillement) au-dessus de H_COULIM ; chaque zone est remise a l'echelle, puis seeing re-integre."""
    K0 = tuple(p["K"] if "K" in p else K_CALCUL_09_10[nom]); KA = h.SITES[nom]["K_new"]   # KA : simple ou jour / nuit
    if h.MODELE_V2 == "V2bd" and p.get("conv") and "cn2_tke" in p["conv"][0] and "cn2_fa" in p["conv"][0]:
        # 15/10 : profil et seeing V2bd (cisaillement V2b + transition douce 100 m) depuis les termes enregistres
        q = {"ref": p["ref"], "conv": p["conv"], "df": p["df"].copy(), "r": {}}; seeing = []
        for i, hh in enumerate(sorted(p["r"])):
            K1 = tuple(h.K_heure(KA, p["ref"] + pd.Timedelta(hours=int(hh))))
            z, c, s_ = profil_v2bd(p, i, hh, K0, K1)
            r = dict(p["r"][hh]); r["z"] = z; r["Cn2"] = c; q["r"][hh] = r
            seeing.append(s_ if np.isfinite(p["df"].seeing_arcsec.iloc[i]) else np.nan)
        q["df"]["seeing_arcsec"] = seeing
        return q
    if not h.est_jour_nuit(KA) and K0 == tuple(KA):
        return p
    q = {"ref": p["ref"], "conv": p["conv"], "df": p["df"].copy(), "r": {}}
    seeing = []
    for i, hh in enumerate(sorted(p["r"])):
        K1 = tuple(h.K_heure(KA, p["ref"] + pd.Timedelta(hours=int(hh))))
        r = dict(p["r"][hh]); z = np.asarray(r["z"], float); c = np.asarray(r["Cn2"], float).copy()
        hc = r["H_COULIM"]
        cv = p["conv"][i]
        conv = np.isin(np.round(z, 3), np.round(cv["z"][cv["conv"]], 3))
        bl = z <= hc
        c[bl & ~conv] *= K1[0] / K0[0]
        c[bl & conv] *= (K1[2] / K0[2]) if K0[2] else np.nan
        c[~bl] *= K1[1] / K0[1]
        r["Cn2"] = c
        q["r"][hh] = r
        s_old = p["df"].seeing_arcsec.iloc[i]
        if not np.isfinite(s_old):
            seeing.append(np.nan)
        elif "cn2_bl" in cv:      # profils complets enregistres : recalcul exact
            zc = cv["z"]; conv_c = cv["conv"]
            bl_c = np.asarray(cv["cn2_bl"], float).copy()
            bl_c[conv_c] *= (K1[2] / K0[2]) if K0[2] else np.nan
            bl_c[~conv_c] *= K1[0] / K0[0]
            seeing.append(M.calculate_seeing(zc, bl_c, np.asarray(cv["cn2_fa"], float) * K1[1] / K0[1], cv["h_coulim"])[2])
        else:                     # anciens pickles : approximation (ecart ~1 % en mediane, < 7 %)
            seeing.append(M.calculate_seeing(z, c, c, hc)[2])
    q["df"]["seeing_arcsec"] = seeing
    return q


def grilles(p):
    """Cn2, masque convectif et masque NaN sur la grille d'affichage ; seeing et H_COULIM par heure."""
    heures = sorted(p["r"])
    t = pd.DatetimeIndex([p["ref"] + pd.Timedelta(hours=int(x)) for x in heures])
    C = np.full((len(heures), ZG.size), np.nan); V = np.zeros_like(C, dtype=bool); N = np.zeros_like(C, dtype=bool)
    for i, hh in enumerate(heures):
        r = p["r"][hh]
        z, c = np.asarray(r["z"], float), np.asarray(r["Cn2"], float)
        o = np.argsort(z); z, c = z[o], c[o]
        ok = np.isfinite(c) & (c > 0)
        if ok.sum() >= 2:
            C[i] = 10 ** np.interp(ZG, z[ok], np.log10(c[ok]), left=np.nan, right=np.nan)
        # niveau d'affichage -> niveau natif le plus proche
        k = np.clip(np.searchsorted(z, ZG), 1, len(z) - 1); k = np.where(np.abs(z[k - 1] - ZG) < np.abs(z[k] - ZG), k - 1, k)
        N[i] = ~ok[k] & (ZG >= z.min()) & (ZG <= z.max())
        cv = p["conv"][i]
        zc = cv["z"]; oc = np.argsort(zc)
        kc = np.clip(np.searchsorted(zc[oc], ZG), 0, len(zc) - 1)
        V[i] = cv["conv"][oc][kc]
    C[N] = np.nan
    s = p["df"].seeing_arcsec.to_numpy(float)
    # echeance sans TKE (H+0) : pas de modele de couche limite -> colonne vide (NaN), pas de convection affichee
    sans = ~np.isfinite(s)
    C[sans] = np.nan; V[sans] = False; N[sans] = True
    hc = np.array([p["r"][hh]["H_COULIM"] for hh in heures], float)
    return t, C, V, N, s, hc


def mediane(ga, gb):
    t, Ca, Va, Na, sa, ha = ga; _, Cb, Vb, Nb, sb, hb = gb
    with np.errstate(all="ignore"):
        C = np.nanmedian(np.stack([Ca, Cb]), axis=0)
        s = np.nanmedian(np.vstack([sa, sb]), axis=0)
    return t, C, Va | Vb, Na & Nb, s, (ha + hb) / 2


RUNS = sys.argv[1:]          # un ou plusieurs runs (ordre chronologique) : ils sont colles, le plus recent l'emporte


def charge(nom, etiq, run):
    f = SCR / f"pan_{nom}_{etiq}_{run}.pkl"
    return recaler_K(pickle.load(open(f, "rb")), nom) if f.exists() else None


def coller(liste):
    """Colle les grilles de plusieurs runs : pour chaque heure, le run le plus recent qui la couvre."""
    liste = [g for g in liste if g is not None]
    if len(liste) == 1:
        return liste[0]
    par_t = {}
    for t, C, V, N, s, hc in liste:          # ordre chronologique : les suivants ecrasent
        for i, ti in enumerate(t):
            if np.isfinite(s[i]) or ti not in par_t:
                par_t[ti] = (C[i], V[i], N[i], s[i], hc[i])
    tt = pd.DatetimeIndex(sorted(par_t))
    C, V, N, s, hc = (np.array([par_t[x][k] for x in tt]) for k in range(5))
    return tt, C, V, N, s, hc


panneaux = []
for nom in h.SITES:
    if nom == "Copernic":
        # 09/10 (demande utilisateur) : pour Copernic, seulement la mediane des deux mailles
        g = []
        for run in RUNS:
            pa, pb = charge("Copernic", "ancienne", run), charge("Copernic", "nouvelle", run)
            if pa is not None and pb is not None:
                g.append(mediane(grilles(pa), grilles(pb)))
        panneaux.append(("Copernic", "mediane des 2 mailles (hachures : convection dans au moins une)", coller(g)))
    else:
        panneaux.append((nom, "", coller([grilles(p) if (p := charge(nom, "site", run)) is not None else None for run in RUNS])))
run = " + ".join(RUNS)

vals = np.concatenate([g[1][np.isfinite(g[1])] for _, _, g in panneaux])
norm = LogNorm(vmin=np.nanpercentile(vals, 5), vmax=np.nanpercentile(vals, 99.5))
bg = "#fcfcfb"
fig, axes = plt.subplots(len(panneaux), 1, figsize=(15, 3.6 * len(panneaux)), dpi=110, sharex=True)
fig.patch.set_facecolor(bg)
print("NaN :")
for ax, (nom, sous, (t, C, V, N, s, hc)) in zip(axes, panneaux):
    ax.set_facecolor("#e9e8e4")      # gris = NaN (aucun Cn2)
    mesh = ax.pcolormesh(t, ZG, C.T, shading="nearest", cmap="turbo", norm=norm)
    if V.any():
        # hachures alternees blanc / noir : traits blancs serres ("////") puis traits noirs deux fois moins
        # serres ("//") par-dessus -> un trait sur deux est noir
        for motif, coul, zo in (("////", "#ffffff", 3), ("//", "#0b0b0b", 3.1)):
            cs = ax.contourf(t, ZG, V.T.astype(float), levels=[0.5, 1.5], colors="none", hatches=[motif], zorder=zo)
            cs.set_edgecolor(coul); cs.set_linewidth(0)
        ax.contour(t, ZG, V.T.astype(float), levels=[0.5], colors="#0b0b0b", linewidths=0.9, zorder=3.2)
    ax.plot(t, np.minimum(hc, ZMAX), color="#fcfcfb", lw=2.2, zorder=4)
    ax.plot(t, np.minimum(hc, ZMAX), color="#0b0b0b", lw=0.9, ls="--", zorder=5)
    ax.set_ylim(ZG[0], ZMAX); ax.set_ylabel("Altitude AGL [m]")
    # seeing prevu et observe
    ax2 = ax.twinx()
    K = h.SITES[nom]["K_new"]
    o = h.observations(nom)
    o = h.filtre_sequences(o[(o.t >= t.min() - pd.Timedelta(minutes=30)) & (o.t <= t.max() + pd.Timedelta(minutes=30))])
    th, mh, gh = h.hourly_median(o)
    fac = 1.0
    if nom in h.FACTEUR_ECHELLE_SITES and len(mh):
        sp = pd.Series(s, index=t); mm = pd.Series(mh, index=th)
        j = pd.concat([sp.rename("p"), mm.rename("m")], axis=1).dropna()
        j = j[j.p > 0]
        if len(j) >= 3:
            fac = float(np.exp(np.mean(np.log(j.m / j.p))))
    if len(o):
        # mesures en BLANC sur la figure Cn2 (demande utilisateur 09/10), contour fonce pour la lisibilite
        ax2.plot(o.t, o.seeing, lw=0, marker="o", ms=2.4, color="#ffffff", mec="#0b0b0b", mew=0.3, alpha=0.75, zorder=12)
        h.plot_line(ax2, th, mh, gh, color="#0b0b0b", lw=3.4, zorder=13)
        h.plot_line(ax2, th, mh, gh, color="#ffffff", lw=1.8, marker="s", ms=4.5, mec="#0b0b0b", mew=0.8, zorder=14,   # mesures au premier plan
                    label="seeing observe (mediane horaire)")
    ax2.plot(t, s * fac, color="#fcfcfb", lw=3.2, zorder=8)
    ax2.plot(t, s * fac, color=h.COULEUR_AROME, lw=1.8, marker="o", ms=3, zorder=9,
             label=f"seeing prevu {h.nom_v2()}" + (f" x {fac:.2f} (facteur d'echelle)" if fac != 1 else ""))
    for mod_a, coul_a, f0, Ka in h.autres_modeles(nom):   # 15/10 : V2 d'origine et V2b, chacune avec ses K
        f0 = f0[(f0.t >= t.min()) & (f0.t <= t.max())]
        if len(f0):
            ax2.plot(f0.t, h.arome(f0, Ka)[1] * fac, color=coul_a, lw=1.4, ls=":", marker=".", ms=3, zorder=9,
                     label=f"seeing prevu {mod_a} (ses K)")
    # seeing prevu V1 (caches, runs colles), meme periode
    haut1 = 0
    f1 = h.forecasts_v1_site(V1M, nom)
    if f1 is not None:
        f1 = f1[(f1.t >= t.min()) & (f1.t <= t.max())]
        if len(f1):
            s1 = h.seeing_v1_k(V1M, f1, h.K_V1[nom])
            ax2.plot(f1.t, s1, color="#fcfcfb", lw=3.0, zorder=8)
            ax2.plot(f1.t, s1, color=h.COULEUR_V1, lw=1.6, ls="--", marker="^", ms=3, zorder=9,
                     label=f"seeing prevu V1 ({h.texte_K_v1(h.K_V1[nom])})")
            haut1 = np.nanmax(s1) if np.any(np.isfinite(s1)) else 0
    ax2.set_ylim(0, max(np.nanmax(s * fac) if np.any(np.isfinite(s)) else 1, haut1, np.nanmax(mh) if len(mh) else 0) * 1.25)
    ax2.set_ylabel("Seeing [arcsec]")
    ax2.legend(loc="upper right", fontsize=8, frameon=True, facecolor=bg, edgecolor="none")
    ax.set_title(f"{nom}{'  -  ' + sous if sous else ''}   |   {h.nom_v2()} {h.texte_K(K)}", loc="left", fontsize=10.5)
    # NaN
    h_nan = [f"{x:%d/%m %Hh}" for x, v in zip(t, s) if not np.isfinite(v)]
    sous_hc = ZG[None, :] <= hc[:, None]
    print(f"  {nom:12s} {sous[:15]:15s} seeing NaN : {len(h_nan)} h {h_nan[:6]}{' ...' if len(h_nan) > 6 else ''} | "
          f"Cn2 NaN : {100 * N.mean():.1f} % des cases (<= {ZMAX:.0f} m), dont sous H_COULIM {100 * N[sous_hc].mean():.1f} %"
          f" | convection : {V.any(axis=1).sum()} h")
heures = pd.date_range(t.min(), t.max(), freq="1h")
for ax in axes:
    ax.set_xticks(heures)
    ax.set_xticklabels(["" if x.hour % 2 else (f"{x:%d/%m %Hh}" if x.hour == 0 else f"{x:%Hh}") for x in heures],
                       rotation=90, fontsize=7)
    ax.tick_params(axis="x", labelbottom=True)
fig.subplots_adjust(top=0.965, bottom=0.03, left=0.06, right=0.86, hspace=0.42)
cb = fig.colorbar(mesh, cax=fig.add_axes([0.925, 0.25, 0.012, 0.5]))
cb.set_label("Cn2 [m^-2/3]")
fig.legend(handles=[Patch(facecolor="#ffffff", edgecolor="#0b0b0b", hatch="//", label="couches convectives (fermeture convective)"),
                    Patch(facecolor="#e9e8e4", label="NaN : aucun Cn2"),
                    plt.Line2D([], [], color="#0b0b0b", ls="--", label="H_COULIM")],
           loc="upper right", ncol=3, fontsize=9, frameon=False, bbox_to_anchor=(0.86, 0.995))
fig.suptitle(f"Cn2 AROME, seeing prevu (V2) et observe - run du {run} (TU)", x=0.01, y=0.993, ha="left", fontsize=13)
out = OUT / f"cn2_sites_{RUNS[-1]}{'_colle' if len(RUNS) > 1 else ''}.png"
fig.savefig(out)
print(out)
