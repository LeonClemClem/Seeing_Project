"""Panneaux de la MEDIANE des deux mailles de Copernic, a partir des resultats sauvegardes par panneaux_point.py.
Chaque variable est interpolee sur les niveaux de la premiere maille, puis mediane niveau par niveau
(avec 2 mailles : mediane = moyenne). Seeing et H_COULIM : mediane heure par heure."""
import importlib.util, pickle, sys
from pathlib import Path
import sys as _sys; _sys.path.insert(0, str(Path(__file__).resolve().parent))  # chemins.py est a cote
from chemins import RESEARCH, PREVISIONS, CACHE
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCR = CACHE / "panneaux"   # profils enregistres par calcul_run.py
SCRIPT = str(RESEARCH / "SeeingAromeV2_correction_conv_tke.py")
OUT = PREVISIONS
nom, run_nom = "Copernic", sys.argv[1]
spec = importlib.util.spec_from_file_location("h", RESEARCH / "historique_sites.py")
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
K = h.SITES[nom]["K_new"]
if h.est_jour_nuit(K):          # jeux jour / nuit : la figure des panneaux est tracee avec le jeu de NUIT
    K = tuple(K["nuit"])
res = [pickle.load(open(SCR / f"pan_{nom}_{e}_{run_nom}.pkl", "rb")) for e in ("ancienne", "nouvelle")]
base = res[0]
fus = {}
for hh in base["r"]:
    z = np.asarray(base["r"][hh]["z"], float)
    d = dict(base["r"][hh])
    for k, v in base["r"][hh].items():
        if isinstance(v, np.ndarray) and v.shape == z.shape and k != "z":
            col = []
            for r in res:
                zz, vv = np.asarray(r["r"][hh]["z"], float), np.asarray(r["r"][hh][k], float)
                ok = np.isfinite(zz) & np.isfinite(vv)
                col.append(np.interp(z, zz[ok], vv[ok], left=np.nan, right=np.nan) if ok.sum() >= 2 else np.full_like(z, np.nan))
            with np.errstate(all="ignore"):
                d[k] = np.nanmedian(np.vstack(col), axis=0)
    d["H_COULIM"] = float(np.nanmedian([r["r"][hh]["H_COULIM"] for r in res]))
    fus[hh] = d
df = base["df"].copy()
df["seeing_arcsec"] = np.nanmedian(np.vstack([r["df"]["seeing_arcsec"].to_numpy() for r in res]), axis=0)
s = importlib.util.spec_from_file_location("m", SCRIPT)
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
m.LAT_SITE, m.LON_SITE = (44.5828 + 44.56179) / 2, (5.9868 + 5.99762) / 2
m.K_TKE, m.K_CIS, m.K_TKE_CONV = K
out = OUT / f"panneaux_{nom}_mediane_{run_nom}.png"
m.plt.show = lambda *a, **k: (plt.gcf().suptitle(f"{nom} - MEDIANE des 2 mailles (ancienne 44.5828/5.9868, nouvelle "
                                                  f"44.56179/5.99762) - K = {K}", y=0.995, fontsize=12),
                              plt.gcf().savefig(out, dpi=110))
m.make_one_figure(fus, df, base["ref"])
print(out)

