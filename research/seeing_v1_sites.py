#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modele V1 (code/V1/SeeingAromeV1.py) calcule pour les sites, pour le tracer
a cote de la V2.

V1 : meme forme dans la couche limite et au-dessus,
    Cn2 = K (80e-6 P / (T theta))^2 L^(4/3) (dtheta/dz)^2,
    L = sqrt(2 E / ((g/theta) dtheta/dz))  (en metres),
    E = TKE sous H_COULIM (K_TKE), E = S^2 au-dessus (K_CIS) ; pas de convection.
    Integrale (trapezes) sur le profil combine, niveaux sans Cn2 ignores.

Les fonctions de calcul sont celles du script V1, appelees avec K = 1 : le
seeing se recompose pour tout jeu (K_TKE, K_CIS) car l'integrale est lineaire :
    integrale = K_TKE * I_tke + K_CIS * I_cis.
Les integrales sont gardees en cache (cache_validation/v1/), ce qui permet de
retracer la V1 apres suppression des GRIB.
"""
from pathlib import Path
import importlib.util

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parent
V1_SCRIPT = V2 / "SeeingAromeV1.py"   # dossier a plat : V1 a cote des scripts V2
CACHE_V1 = V2 / "cache_validation" / "v1"
FORECAST_HOURS = 51


def _load_v1():
    spec = importlib.util.spec_from_file_location("seeing_v1", V1_SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _cache_path(run_dir, tag):
    return CACHE_V1 / f"{Path(run_dir).name}__{tag}__V1.csv"


def compute_v1(nom, tag, lat, lon, run_dir):
    """Integrales V1 a K = 1 par echeance (t, h, H_COULIM, I_tke, I_cis, has_tke), en cache."""
    out = _cache_path(run_dir, tag)
    if out.exists():
        return pd.read_csv(out, parse_dates=["t"])
    m = _load_v1()
    m.DATA_DIR, m.LAT_SITE, m.LON_SITE = Path(run_dir), lat, lon
    m.K_TKE = m.K_CIS = 1.0

    files = {p: m.find_grib_files(p) for p in ("HP1", "HP2", "IP1", "IP4", "SP2")}
    variables = {"HP1": ({"t", "u", "v", "pres"}, None), "HP2": ({"tke"}, None),
                 "IP1": ({"t", "u", "v", "z"}, {"isobaricInhPa"}), "IP4": ({"tke"}, {"isobaricInhPa"}),
                 "SP2": ({"blh", "h_coulim"}, {"surface"})}
    cache, hour_file = {}, {}
    for p, fl in files.items():
        var, types = variables[p]
        hour_file[p] = m.build_hour_file_map(fl, FORECAST_HOURS)
        for path in fl:
            data, la, lo = m.read_grib_package(path, var, allowed_types=types)
            cache[path] = {"data": data, "lat": la, "lon": lo}
    reference = m.get_grib_cycle_datetime(files["HP1"][0])
    surface, _, _ = m.read_surface_h(files["SP2"][0])

    def integrale(z, c):
        z, c = np.asarray(z, float), np.asarray(c, float)
        ok = np.isfinite(z) & np.isfinite(c) & (c >= 0)
        if ok.sum() < 2:
            return np.nan
        o = np.argsort(z[ok])
        return float(np.trapezoid(c[ok][o], z[ok][o]))

    rows = []
    for hour in range(FORECAST_HOURS + 1):
        d = {p: cache[hour_file[p][hour]] for p in files}
        h_coulim = m.get_h_coulim(d["SP2"]["data"], hour)
        hag = m.build_hag_profile(d["HP1"]["data"], d["HP2"]["data"], hour, d["HP1"]["lat"], d["HP1"]["lon"])
        iso = m.make_isobaric_profile(d["IP1"]["data"], hour, surface, d["IP1"]["lat"], d["IP1"]["lon"])
        iso["TKE"] = m.add_ip4_tke(iso, d["IP4"]["data"], hour)

        # Memes decoupages que main() de la V1
        bl_h, bl_i = hag["z"] <= h_coulim, (iso["z"] > 3000.0) & (iso["z"] <= h_coulim)
        tke_bl = {k: np.concatenate([hag[k][bl_h], iso[k][bl_i]]) for k in ("z", "T", "U", "V", "P", "TKE")}
        r_tke = m.calculate_cn2_tke(tke_bl)
        sh_h = np.isfinite(hag["z"]) & (hag["z"] > h_coulim) & (hag["z"] <= 3000.0)
        sh_i = np.isfinite(iso["z"]) & (iso["z"] > max(float(h_coulim), 3000.0))
        shear = {k: np.concatenate([np.asarray(hag[k])[sh_h], np.asarray(iso[k])[sh_i]]) for k in ("z", "T", "U", "V", "P")}
        r_cis = m.calculate_cn2_shear(shear)

        z = np.concatenate([r_tke["z"], r_cis["z"]])
        c_tke, c_cis = np.asarray(r_tke["Cn2"], float), np.asarray(r_cis["Cn2"], float)
        # Meme ensemble de niveaux que la V1 (Cn2 fini), une partie mise a 0 :
        # integrale(K_TKE, K_CIS) = K_TKE * I_tke + K_CIS * I_cis exactement.
        zero = lambda c: np.where(np.isfinite(c), 0.0, np.nan)
        rows.append({"t": reference + pd.Timedelta(hours=hour), "h": hour, "H_COULIM": h_coulim,
                     "I_tke": integrale(z, np.concatenate([c_tke, zero(c_cis)])),
                     "I_cis": integrale(z, np.concatenate([zero(c_tke), c_cis])),
                     "has_tke": bool(np.any(np.isfinite(hag["TKE"]) & (hag["TKE"] > 0)))})
        print(f"  V1 {nom} H+{hour:02d}")
    df = pd.DataFrame(rows)
    CACHE_V1.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, float_format="%.6e")
    return df


def forecasts_v1(tag):
    """Toutes les echeances V1 en cache pour un site (le run le plus recent l'emporte)."""
    runs = [pd.read_csv(f, parse_dates=["t"]).assign(run=lambda d: d.t.iloc[0])
            for f in CACHE_V1.glob(f"*__{tag}__V1.csv")]
    if not runs:
        return None
    d = pd.concat(runs, ignore_index=True).assign(I_conv=0.0)    # pas de convection en V1
    # echeance sans TKE (H+0) ignoree si un autre run couvre la meme heure
    d = d[~(~d.has_tke.astype(bool) & d.t.duplicated(keep=False))]
    # 17/10 (utilisateur) : runs PRINCIPAUX (00/06/12/18Z) prioritaires ; un run intermediaire ne comble que les trous
    d["principal"] = (pd.DatetimeIndex(d.run).hour % 6 == 0)
    return d.sort_values(["t", "principal", "run"]).drop_duplicates("t", keep="last").sort_values("t").reset_index(drop=True)


def seeing_v1(d, K, seeing_arcsec):
    """Seeing V1 pour K = (K_TKE, K_CIS) ; NaN sans TKE (H+0), comme la V2."""
    s = seeing_arcsec(K[0] * d.I_tke + K[1] * d.I_cis)
    return np.where(d.has_tke, s, np.nan)


if __name__ == "__main__":
    spec = importlib.util.spec_from_file_location("historique_sites", V2 / "historique_sites.py")
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    import sys
    # usage : seeing_v1_sites.py <dossier du run> [site ...]  (par defaut tous les sites)
    run = Path(sys.argv[1])
    for nom in (sys.argv[2:] or list(h.SITES)):
        compute_v1(nom, h.SITES[nom]["cache_tag"], *h.COORDS[nom], run)
