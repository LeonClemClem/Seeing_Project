#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Carte de seeing V2 sur une zone (par defaut 100 km x 100 km autour de Verclause).

Optimisation par rapport au calcul point par point :
  1. Chaque fichier GRIB n'est decode qu'UNE fois pour toutes les mailles de la zone
     (le script V2 decode deja le champ entier pour n'en garder qu'une valeur).
     Les fichiers sont lus en parallele (un processus par fichier).
  2. La physique n'est pas reecrite : pour chaque maille, main() du script V2 tourne
     tel quel, avec read_grib_package / read_surface_h remplaces par une lecture dans
     les champs deja extraits. Les mailles sont reparties sur plusieurs processus.
  3. Comme validation_sites.compute_components, on garde les integrales a K = 1
     (I_tke, I_conv, I_cis) : la carte se refait pour n'importe quels K sans recalcul.

Mode --echeances A-B (ex. 32-40, une nuit) : seules ces echeances sont extraites et
calculees (+ SP3 a A-1, seule dependance a l'echeance precedente : flux sshf cumule).
Les autres echeances sont vues par main() comme incompletes, donc sautees ; les
echeances gardees sont identiques au calcul complet. Une carte PNG par echeance
(echelle commune --vmin/--vmax) et un GIF anime.

Grande zone (--zone france) : la zone est decoupee en --tuiles bandes de latitude,
chacune avec son pickle, pour tenir dans la RAM (chaque processus charge sa tuile).

Sorties :
  cache_validation/carte/<run>__<zone>__champs[_tK].pkl     (champs extraits, etape 1)
  cache_validation/carte/<run>__<zone>__integrales[_tK].csv (integrales par maille et echeance)
  previsions/carte_seeing_<run_court>_<zone>.png             (moyenne de nuit)
  previsions/carte_seeing_<run_court>_<zone>/*.png + .gif    (mode --echeances)

Usage : python carte_seeing.py <dossier du run> [--heures 51] [--rayon-km 50] [--workers 3]
        python carte_seeing.py <dossier du run> --zone france --echeances 32-40 --tuiles 8 --K 1 6 0.1
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import argparse, contextlib, gc, importlib.util, io, pickle, shutil, sys, time
import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parent
SCRIPT_V2 = V2 / "SeeingAromeV2_correction_conv_tke.py"
CACHE = V2 / "cache_validation" / "carte"
OUT = V2.parent.parent / "previsions"
CENTRE = (44.3814, 5.4286)          # Verclause (historique_sites.COORDS["Drôme"])
FRANCE = (41.2, 51.3, -5.3, 9.8)    # lat min, lat max, lon min, lon max (France metropolitaine + Corse)
# sites des cartes zoomees (--zooms) : Cosmodrome = scripts V1, autres = historique_sites.COORDS
SITES_ZOOM = {"Cosmodrome": (44.1952, 5.4716), "Saint_Veran": (44.6988, 6.9083), "OHP": (43.9317, 5.7133),
              "Verclause": CENTRE, "Copernic": (44.56179, 5.99762),
              "Uzes": (44.0125, 4.4197),      # centre-ville d'Uzes (30)
              "Lac_de_Neuchatel": (46.90, 6.85)}   # centre du lac (Suisse)
# grandes villes (points sur les cartes France, ajoute_villes)
VILLES = {"Paris": (48.8566, 2.3522), "Marseille": (43.2965, 5.3698), "Lyon": (45.7640, 4.8357),
          "Toulouse": (43.6047, 1.4442), "Nice": (43.7102, 7.2620), "Nantes": (47.2184, -1.5536),
          "Montpellier": (43.6108, 3.8767), "Strasbourg": (48.5734, 7.7521), "Bordeaux": (44.8378, -0.5792),
          "Lille": (50.6292, 3.0573), "Rennes": (48.1173, -1.6778), "Reims": (49.2583, 4.0317),
          "Toulon": (43.1242, 5.9280), "Grenoble": (45.1885, 5.7245), "Dijon": (47.3220, 5.0415),
          "Clermont-Ferrand": (45.7772, 3.0870), "Brest": (48.3904, -4.4861), "Limoges": (45.8336, 1.2611),
          "Tours": (47.3941, 0.6848), "Rouen": (49.4432, 1.0999), "Metz": (49.1193, 6.1757),
          "Perpignan": (42.6887, 2.8948), "Nîmes": (43.8367, 4.3601), "Avignon": (43.9493, 4.8055),
          "Ajaccio": (41.9192, 8.7386), "Besançon": (47.2378, 6.0241), "Poitiers": (46.5802, 0.3404),
          "Pau": (43.2951, -0.3708), "Genève": (46.2044, 6.1432), "Bruxelles": (50.8503, 4.3517),
          "Turin": (45.0703, 7.6869), "Zurich": (47.3769, 8.5417), "Barcelone": (41.3874, 2.1686)}


# seeing monitors (historique_sites.COORDS ; Villeneuve exclu a la demande de l'utilisateur, 11/10)
MONITEURS = {"ROSA (Verclause)": CENTRE, "Copernic": (44.56179, 5.99762), "Saint-Véran": (44.6988, 6.9083),
             "OHP": (43.9317, 5.7133)}


def ajoute_moniteurs(ax, moniteurs=MONITEURS):
    """Etoiles creuses, sans nom (demande utilisateur 11/10)."""
    for la, lo in moniteurs.values():
        ax.plot(lo, la, marker="*", ms=11, mfc="none", mec="k", mew=1.0, zorder=7)


def ajoute_villes(ax, villes=VILLES, taille=5, noms=True, alpha=0.55):
    """Points blancs cercles de noir ; noms petits et semi-transparents (demande utilisateur 11/10)."""
    import matplotlib.patheffects as pe
    halo = [pe.withStroke(linewidth=1.5, foreground=(1, 1, 1, alpha * 0.8))]
    for nom, (la, lo) in villes.items():
        ax.plot(lo, la, "o", ms=3.5, mfc="white", mec="k", mew=0.8, zorder=5)
        if noms:
            ax.annotate(nom, (lo, la), xytext=(3, 2), textcoords="offset points", fontsize=taille, zorder=6,
                        color=(0, 0, 0, alpha), path_effects=halo)


# 13/10 (choix utilisateur) : K uniques pour la carte (seeing moyen de la maille, sans correction d'altitude) :
# K_CIS = 35 (valeur commune des sites fiables) et K_TKE = 2 (optimal sur 5 sites avec K_CIS = 35 ; sous-estime les
# vallees / creux d'environ 1-2"). K_conv sans effet la nuit. Avant : (9.53, 12.0, 0.1) = K de la Drome.
K_CARTE = (2.0, 35.0, 0.1)         # K_TKE, K_CIS, K_conv
# affichage seulement (le calcul reste maille par maille, sans interpolation)
INTERPOLATION = True                # True : interpolation lineaire entre centres de mailles (gouraud)
CMAP = "turbo"                      # bleu = bon seeing, rouge = mauvais (choix utilisateur 10/10 ; avant "viridis")
FENETRE_NUIT_TU = (20, 4)           # moyenne de la carte : de 20h a 04h TU (demande utilisateur 09/10)
# memes variables / types que calcul_run.py
VARIABLES = {"HP1": {"t", "u", "v", "10u", "10v", "pres"}, "HP2": {"tke"}, "IP1": {"t", "u", "v", "z"},
             "IP4": {"tke"}, "SP2": {"blh", "h_coulim"}, "SP3": {"sshf"}}
TYPES = {"IP1": {"isobaricInhPa"}, "IP4": {"isobaricInhPa"}, "SP2": {"surface"}}
TYPES_DEFAUT = {"heightAboveGround", "isobaricInhPa", "surface"}


def _load(nom):
    s = importlib.util.spec_from_file_location(nom, SCRIPT_V2)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


def steps_paquet(paquet, echeances):
    """Echeances a extraire pour un paquet (None = toutes)."""
    if echeances is None:
        return None
    a, b = echeances
    return set(range(a - 1 if paquet == "SP3" else a, b + 1))


# ============================================================================
# ETAPE 1 : extraction des champs de la zone (un decodage par message)
# ============================================================================
def zone_indices(lats, lons, zone):
    lons = ((lons + 180.0) % 360.0) - 180.0
    if zone[0] == "boite":
        la0, la1, lo0, lo1 = zone[1]
        return np.flatnonzero((lats >= la0) & (lats <= la1) & (lons >= lo0) & (lons <= lo1))
    rayon_km = zone[1]
    dlat = rayon_km / 111.2
    dlon = rayon_km / (111.32 * np.cos(np.radians(CENTRE[0])))
    return np.flatnonzero((np.abs(lats - CENTRE[0]) <= dlat) & (np.abs(lons - CENTRE[1]) <= dlon))


def extrait_fichier(args):
    """data[step][shortName][level] = valeurs (N mailles) ; + h relief pour SP2.
    Ecrit une part par tuile dans dossier_parts (rien de gros ne revient au processus principal)."""
    path, zone, steps, ntuiles, dossier_parts = args
    t0 = time.time()
    from eccodes import codes_grib_new_from_file, codes_get, codes_get_array, codes_release
    paquet = path.name.split("__")[2]
    variables, types = VARIABLES[paquet], TYPES.get(paquet, TYPES_DEFAUT)
    data, idx, lat, lon, relief = {}, None, None, None, None

    def get(gid, key):
        try:
            return codes_get(gid, key)
        except Exception:
            return None

    with open(path, "rb") as f:
        while True:
            try:
                gid = codes_grib_new_from_file(f)
            except Exception as exc:
                print(f"  fin de fichier prematuree dans {path.name} : {exc}", flush=True)
                break
            if gid is None:
                break
            try:
                nom, typ, niv = get(gid, "shortName"), get(gid, "typeOfLevel"), get(gid, "level")
                h_relief = paquet == "SP2" and relief is None and nom == "h" and typ == "surface"
                if not h_relief and (nom not in variables or typ not in types):
                    continue
                step = None
                for key in ("step", "endStep", "forecastTime"):
                    v = get(gid, key)
                    if v is not None:
                        step = int(round(float(v))); break
                if not h_relief and steps is not None and step not in steps:
                    continue
                if idx is None:
                    la = np.asarray(codes_get_array(gid, "latitudes"), float)
                    lo = ((np.asarray(codes_get_array(gid, "longitudes"), float) + 180.0) % 360.0) - 180.0
                    idx = zone_indices(la, lo, zone)
                    lat, lon = la[idx], lo[idx]
                vals = np.asarray(codes_get_array(gid, "values"), float)[idx]
                if h_relief:
                    relief = vals
                    if nom not in variables or (steps is not None and step not in steps):
                        continue
                if step is None:
                    continue
                data.setdefault(step, {}).setdefault(nom, {})[float(niv or 0.0)] = vals
            finally:
                codes_release(gid)
    n = 0 if idx is None else idx.size
    for k, sl in enumerate(np.array_split(np.arange(n), ntuiles)):
        s = slice(int(sl[0]), int(sl[-1]) + 1) if sl.size else slice(0, 0)
        part = {"data": {st: {v: {lv: a[s].copy() for lv, a in dv.items()} for v, dv in d.items()}
                         for st, d in data.items()},
                "lat": None if lat is None else lat[s].copy(), "lon": None if lon is None else lon[s].copy(),
                "relief": None if relief is None else relief[s].copy()}
        with open(Path(dossier_parts) / f"t{k}__{path.name}.pkl", "wb") as fp:
            pickle.dump(part, fp, protocol=pickle.HIGHEST_PROTOCOL)
    return path.name, n, time.time() - t0


def noms_tuiles(cle, ntuiles, suffixe):
    if ntuiles == 1:
        return [CACHE / f"{cle}__{suffixe}"]
    base, ext = suffixe.rsplit(".", 1)
    return [CACHE / f"{cle}__{base}_t{k}.{ext}" for k in range(ntuiles)]


def extrait_zone(run, zone, heures, echeances, workers, ntuiles, cle):
    """workers = processus de lecture GRIB (1 si peu de RAM : un fichier entier du domaine en memoire)."""
    tuiles = noms_tuiles(cle, ntuiles, "champs.pkl")
    if all(t.exists() for t in noms_tuiles(cle, ntuiles, "integrales.csv")):
        print("Integrales deja calculees : extraction inutile (champs supprimables)")
        return tuiles
    if all(t.exists() for t in tuiles):
        print(f"Champs deja extraits : {tuiles[0].name}{' ...' if ntuiles > 1 else ''}")
        return tuiles
    m = _load("m_fichiers"); m.DATA_DIR = run
    taches = []
    for paquet in VARIABLES:
        try:
            fs = m.find_grib_files(paquet)
        except FileNotFoundError:
            continue
        carte = m.build_hour_file_map(fs, heures)
        steps = steps_paquet(paquet, echeances)
        choisis = set(carte.values()) if steps is None else {carte[h] for h in steps if h in carte}
        if paquet == "SP2":
            choisis.add(fs[0])        # relief h (champ statique)
        taches += [(f, steps) for f in sorted(choisis)]
    parts = CACHE / f"{cle}__parts"
    parts.mkdir(parents=True, exist_ok=True)
    print(f"Etape 1 : {len(taches)} fichiers GRIB, {workers} processus, {ntuiles} tuile(s)...", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(workers) as ex:
        for nom, n, dt in ex.map(extrait_fichier, [(f, zone, s, ntuiles, str(parts)) for f, s in taches]):
            print(f"  {nom} : {n} mailles ({dt:.0f} s, total {time.time() - t0:.0f} s)", flush=True)
    noms = [f.name for f, _ in taches]
    total = 0
    for k, tuile in enumerate(tuiles):
        champs = {}
        for nom in noms:
            with open(parts / f"t{k}__{nom}.pkl", "rb") as fp:
                p = pickle.load(fp)
            champs[nom] = {"data": p["data"], "lat": p["lat"], "lon": p["lon"]}
            if p["relief"] is not None:
                champs.setdefault("_relief", p["relief"])
            (parts / f"t{k}__{nom}.pkl").unlink()     # disque : la part est dans la tuile
        ref = next(v for v in champs.values() if v["lat"] is not None and v["lat"].size)
        for nom, v in champs.items():
            if not nom.startswith("_") and v["lat"] is not None and not np.allclose(v["lat"], ref["lat"]):
                raise RuntimeError(f"Grille differente dans {nom}")
        champs["_lat"], champs["_lon"] = ref["lat"], ref["lon"]
        total += ref["lat"].size
        with open(tuile, "wb") as fp:
            pickle.dump(champs, fp, protocol=pickle.HIGHEST_PROTOCOL)
        del champs; gc.collect()
    shutil.rmtree(parts)
    print(f"Etape 1 terminee en {time.time() - t0:.0f} s : {total} mailles", flush=True)
    return tuiles


# ============================================================================
# ETAPE 2 : physique V2 maille par maille (main() inchange, lectures remplacees)
# ============================================================================
_W = {}


def _init_worker(champs_path, run, heures, garder):
    with open(champs_path, "rb") as fp:
        _W["champs"] = pickle.load(fp)
    _W["garder"] = garder
    m = _load("m_carte")
    m.DATA_DIR, m.FORECAST_HOURS = Path(run), heures
    m.K_TKE = m.K_CIS = m.K_TKE_CONV = 1.0
    m.make_one_figure = lambda *a, **k: None
    _W["m"] = m
    _W["orig"] = (m.build_display_profile, m.calculate_cn2_tke, m.calculate_seeing, m.empty_hour_result)
    _W["cycle"] = m.get_grib_cycle_datetime(m.find_grib_files("HP1")[0])
    # E/S identiques pour toutes les mailles : faites une fois par processus (glob + en-tete GRIB)
    fichiers = {}
    for paquet in VARIABLES:
        try:
            fichiers[paquet] = m.find_grib_files(paquet)
        except FileNotFoundError:
            pass

    def find_grib_files(paquet):
        if paquet not in fichiers:
            raise FileNotFoundError(f"Aucun fichier {paquet} dans {m.DATA_DIR}")
        return list(fichiers[paquet])
    m.find_grib_files = find_grib_files
    m.get_grib_cycle_datetime = lambda path: _W["cycle"]


def calcule_maille(j):
    """Integrales a K = 1 par echeance (meme decoupage que validation_sites.compute_components)."""
    m, champs = _W["m"], _W["champs"]
    f_display, f_tke, f_seeing, f_empty = _W["orig"]
    lat, lon = float(champs["_lat"][j]), float(champs["_lon"][j])
    m.LAT_SITE, m.LON_SITE = lat, lon

    def lecture(path, variables, allowed_types=None):
        c = champs.get(Path(path).name)
        if c is None:                  # fichier non extrait (hors --echeances) : echeances incompletes
            return {}, lat, lon
        sous = {st: {v: {lv: float(a[j]) for lv, a in d[v].items()} for v in variables if v in d}
                for st, d in c["data"].items()}
        return sous, lat, lon

    state, rows = {}, []

    def display(*a):
        r = f_display(*a)
        state["has_tke"] = bool(np.any(np.isfinite(r["TKE"])))
        return r

    def tke(profile):
        r = f_tke(profile)
        state["raw"] = r["Cn2"].copy()
        return r

    def integral(z, bl, fa, h):
        v = f_seeing(z, bl, fa, h)[0]
        return v if np.isfinite(v) else 0.0

    def seeing(z, bl, fa, h):
        raw, none = state["raw"], np.full_like(bl, np.nan)
        rows.append({"h": len(rows), "H_COULIM": h, "has_tke": state["has_tke"],
                     "I_tke": integral(z, np.where(np.isfinite(raw), bl, np.nan), none, h),
                     "I_conv": integral(z, np.where(~np.isfinite(raw) & np.isfinite(bl), bl, np.nan), none, h),
                     "I_cis": integral(z, none, fa, h)})
        return f_seeing(z, bl, fa, h)

    def empty(h_coulim=np.nan):
        rows.append({"h": len(rows), "H_COULIM": h_coulim, "has_tke": False,
                     "I_tke": np.nan, "I_conv": np.nan, "I_cis": np.nan})
        return f_empty(h_coulim)

    m.read_grib_package = lecture
    m.read_surface_h = lambda path: (float(champs["_relief"][j]), lat, lon)
    m.build_display_profile, m.calculate_cn2_tke, m.calculate_seeing, m.empty_hour_result = display, tke, seeing, empty
    to_csv = pd.DataFrame.to_csv
    pd.DataFrame.to_csv = lambda *a, **k: None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            m.main()
    finally:
        pd.DataFrame.to_csv = to_csv
    d = pd.DataFrame(rows)
    if _W["garder"] is not None:
        d = d[d.h.isin(_W["garder"])].reset_index(drop=True)
    d.insert(0, "maille", j); d.insert(1, "lat", lat); d.insert(2, "lon", lon)
    d.insert(3, "relief", float(champs["_relief"][j]))
    d.insert(5, "t", pd.Timestamp(_W["cycle"]) + pd.to_timedelta(d.h, unit="h"))
    return d


def calcule_zone(run, heures, garder, workers, cle, tuiles):
    sorties = noms_tuiles(cle, len(tuiles), "integrales.csv")
    resultats, decalage = [], 0
    for k, (tuile, out) in enumerate(zip(tuiles, sorties)):
        if out.exists():
            print(f"Integrales deja calculees : {out.name}")
            d = pd.read_csv(out, parse_dates=["t"])
        else:
            with open(tuile, "rb") as fp:
                n = pickle.load(fp)["_lat"].size
            gc.collect()
            print(f"Etape 2 (tuile {k + 1}/{len(tuiles)}) : {n} mailles, {workers} processus...", flush=True)
            t0, parts = time.time(), []
            with ProcessPoolExecutor(workers, initializer=_init_worker,
                                     initargs=(tuile, run, heures, garder)) as ex:
                for i, d in enumerate(ex.map(calcule_maille, range(n), chunksize=8), 1):
                    parts.append(d)
                    if i % 500 == 0 or i == n:
                        el = time.time() - t0
                        print(f"  {i}/{n} mailles ({el:.0f} s, reste ~{el / i * (n - i):.0f} s)", flush=True)
            d = pd.concat(parts, ignore_index=True)
            d["maille"] += decalage
            d.to_csv(out, index=False, float_format="%.6e")
            print(f"Etape 2 tuile {k + 1} terminee en {time.time() - t0:.0f} s", flush=True)
        decalage = int(d.maille.max()) + 1
        resultats.append(d)
    return pd.concat(resultats, ignore_index=True)


# ============================================================================
# CARTE
# ============================================================================
def seeing_arcsec(integral, lam=500e-9):
    integral = np.asarray(integral, float)
    out = np.full_like(integral, np.nan)
    ok = integral > 0
    out[ok] = 0.98 * lam * (0.423 * (2 * np.pi / lam) ** 2 * integral[ok]) ** 0.6 * 206265.0
    return out


def ajoute_seeing(d, K):
    kt, kc, kv = K
    d = d.copy()
    d["seeing"] = np.where(d.has_tke, seeing_arcsec(kt * d.I_tke + kv * d.I_conv + kc * d.I_cis), np.nan)
    return d


def grilles(sel):
    """Valeurs par maille -> grilles (lat, lon) regulieres."""
    lats, lons = np.unique(sel.lat.round(4)), np.unique(sel.lon.round(4))
    grille = np.full((lats.size, lons.size), np.nan); relief = grille.copy()
    il, jl = np.searchsorted(lats, sel.lat.round(4)), np.searchsorted(lons, sel.lon.round(4))
    grille[il, jl], relief[il, jl] = sel.seeing, sel.relief
    return lats, lons, grille, relief


def figure(d, cle, court, K=K_CARTE):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    kt, kc, kv = K
    d = ajoute_seeing(d, K)
    # premiere fenetre FENETRE_NUIT_TU complete du run (echeances avec TKE)
    h0, h1 = FENETRE_NUIT_TU
    t_ok = d.loc[d.has_tke, "t"]
    debut = t_ok.min().normalize() + pd.Timedelta(hours=h0)
    if debut < t_ok.min():
        debut += pd.Timedelta(days=1)
    fin = debut.normalize() + pd.Timedelta(days=1 if h1 < h0 else 0, hours=h1)
    sel = d[(d.t >= debut) & (d.t <= fin)]
    moy = sel.groupby("maille").agg(lat=("lat", "first"), lon=("lon", "first"), relief=("relief", "first"),
                                    seeing=("seeing", "mean"), n=("seeing", "count"))
    lats, lons, grille, relief = grilles(moy)

    fig, ax = plt.subplots(figsize=(8.5, 7))
    vmax = np.nanpercentile(grille, 98)
    pc = ax.pcolormesh(lons, lats, grille, shading="gouraud" if INTERPOLATION else "nearest", cmap=CMAP,
                       vmin=np.nanmin(grille), vmax=vmax)
    cs = ax.contour(lons, lats, relief, levels=np.arange(250, 3000, 250), colors="k", linewidths=0.4, alpha=0.5)
    ax.clabel(cs, fmt="%d m", fontsize=6)
    ax.plot(CENTRE[1], CENTRE[0], marker="*", ms=13, mfc="white", mec="k")
    ax.annotate("Verclause", (CENTRE[1], CENTRE[0]), xytext=(6, 6), textcoords="offset points", fontsize=8,
                bbox=dict(fc="white", ec="none", alpha=0.7))
    ax.set_aspect(1 / np.cos(np.radians(CENTRE[0])))
    ax.set_xlabel("longitude (°E)"); ax.set_ylabel("latitude (°N)")
    fig.colorbar(pc, ax=ax, label='seeing moyen de la nuit (")', shrink=0.85)
    ax.set_title(f"Seeing V2 moyen, nuit du {debut:%d/%m} {debut:%H}h au {fin:%d/%m} {fin:%H}h TU "
                 f"({int(moy.n.median())} échéances)\nrun {court} — K_TKE = {kt:g}  K_CIS = {kc:g}  "
                 f"K_conv = {kv:g} — {len(moy)} mailles{' (interpolation linéaire)' if INTERPOLATION else ''}, "
                 f"relief AROME en isolignes", fontsize=9)
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / f"carte_seeing_{court}_{cle.split('__')[1]}.png"
    fig.savefig(png, dpi=130, bbox_inches="tight"); plt.close(fig)
    n_nan = int(sel.seeing.isna().sum())
    print(f"Carte : {png}  (seeing moyen {np.nanmin(grille):.2f}-{np.nanmax(grille):.2f}\", "
          f"mediane {np.nanmedian(grille):.2f}\" ; NaN sur la nuit : {n_nan})")
    return png


def zoom(d, site, rayon_km):
    """Sous-zone carree de +/- rayon_km autour d'un site, prise dans une grande zone deja calculee."""
    lat0, lon0 = site
    dlat, dlon = rayon_km / 111.2, rayon_km / (111.32 * np.cos(np.radians(lat0)))
    return d[((d.lat - lat0).abs() <= dlat) & ((d.lon - lon0).abs() <= dlon)]


def figures_echeances(d, cle, court, K, vmin, vmax, grande_zone, site=("Verclause", *CENTRE), gif=True):
    """Une carte par echeance (echelle de couleur commune) + GIF anime.
    site = (nom, lat, lon) marque d'une etoile sur les petites zones."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    kt, kc, kv = K
    d = ajoute_seeing(d, K)
    zone = cle.split("__")[1]
    nom_site, lat_site, lon_site = site
    dossier = OUT / (f"carte_seeing_{court}_{zone}_K{kt:g}-{kc:g}-{kv:g}_echelle{vmin:g}-{vmax:g}"
                     + ("" if CMAP == "viridis" else f"_{CMAP}"))
    dossier.mkdir(parents=True, exist_ok=True)
    pngs = []
    for t, sel in d.groupby("t"):
        lats, lons, grille, relief = grilles(sel)
        lat_moy = float(np.mean(lats))
        fig, ax = plt.subplots(figsize=(10, 9.5) if grande_zone else (8.5, 7))
        pc = ax.pcolormesh(lons, lats, grille, shading="gouraud" if INTERPOLATION else "nearest", cmap=CMAP,
                           vmin=vmin, vmax=vmax)
        if grande_zone:        # trait de cote + isolignes 1000 / 2000 m
            # relief AROME bruite en mer (-4 a +20 m) : mediane 5x5 puis isoligne 1 m
            from scipy.ndimage import median_filter
            ax.contour(lons, lats, median_filter(relief, 5), levels=[1.0], colors="k", linewidths=0.6)
            ax.contour(lons, lats, relief, levels=[1000, 2000], colors="w", linewidths=0.3, alpha=0.6)
        else:
            cs = ax.contour(lons, lats, relief, levels=np.arange(250, 3000, 250), colors="k",
                            linewidths=0.4, alpha=0.5)
            ax.clabel(cs, fmt="%d m", fontsize=6)
        if not grande_zone:    # pas de Verclause sur la carte France (demande utilisateur 10/10)
            ax.plot(lon_site, lat_site, marker="*", ms=13, mfc="white", mec="k")
            ax.annotate(nom_site, (lon_site, lat_site), xytext=(6, 6), textcoords="offset points",
                        fontsize=8, bbox=dict(fc="white", ec="none", alpha=0.7))
        ax.set_aspect(1 / np.cos(np.radians(lat_moy)))
        ax.set_xlabel("longitude (°E)"); ax.set_ylabel("latitude (°N)")
        fig.colorbar(pc, ax=ax, label='seeing (")', shrink=0.8, extend="max")
        h = int(sel.h.iloc[0])
        ax.set_title(f"Seeing V2 — {t:%d/%m/%Y %H}h TU (H+{h:02d})\nrun {court} — K_TKE = {kt:g}  "
                     f"K_CIS = {kc:g}  K_conv = {kv:g} — {len(sel)} mailles, échelle {vmin:g}-{vmax:g}\""
                     f"{' (interpolation linéaire)' if INTERPOLATION else ''}", fontsize=9)
        png = dossier / f"seeing_{t:%Y-%m-%d_%H}h_TU.png"
        fig.savefig(png, dpi=110 if grande_zone else 130, bbox_inches="tight"); plt.close(fig)
        pngs.append(png)
        s = sel.seeing
        print(f"  {png.name} : mediane {s.median():.2f}\", min {s.min():.2f}\", max {s.max():.2f}\", "
              f"> {vmax:g}\" : {int((s > vmax).sum())} mailles, NaN : {int(s.isna().sum())}", flush=True)
    if gif:
        fait_gif(pngs, dossier / f"seeing_{court}_{zone}.gif")
    return dossier, pngs


GIF_MS = 1000                       # duree d'une image du GIF (une version 500 ms "_rapide" existe pour France 24 h)


def fait_gif(pngs, gif, duree=GIF_MS):
    from PIL import Image
    images = [Image.open(p).convert("RGB") for p in pngs]
    taille = images[0].size
    images = [im.resize(taille) if im.size != taille else im for im in images]
    images[0].save(gif, save_all=True, append_images=images[1:], duration=duree, loop=0, optimize=True)
    print(f"Cartes : {gif.parent}\nGIF : {gif}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run")
    p.add_argument("--heures", type=int, default=51)
    p.add_argument("--rayon-km", type=float, default=50.0)
    p.add_argument("--zone", choices=["verclause", "france", "arome"], default="verclause",
                   help="arome = domaine AROME 0.025 complet (803 757 mailles)")
    p.add_argument("--blocs", type=int, help="avec --echeances : calcul par blocs de N echeances (disque / RAM)")
    p.add_argument("--workers-lecture", type=int, help="processus de lecture GRIB (defaut = --workers)")
    p.add_argument("--supprime-champs", action="store_true",
                   help="supprime les champs extraits d'un bloc une fois ses integrales calculees")
    p.add_argument("--echeances", help="A-B : seulement ces echeances, une carte par echeance + GIF")
    p.add_argument("--tuiles", type=int, default=1)
    p.add_argument("--K", type=float, nargs=3, default=K_CARTE, metavar=("K_TKE", "K_CIS", "K_CONV"))
    p.add_argument("--vmin", type=float, default=0.0)
    p.add_argument("--vmax", type=float, default=15.0)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--zooms", nargs="+", choices=sorted(SITES_ZOOM),
                   help="avec --echeances : cartes zoomees autour de ces sites (decoupees dans la zone calculee)")
    p.add_argument("--zoom-km", type=float, default=50.0)
    a = p.parse_args()
    run = Path(a.run)
    court = run.name.replace("AROME_download_", "")
    lecture = a.workers_lecture or a.workers
    if a.zone == "france":
        zone, nom_zone = ("boite", FRANCE), "France"
    elif a.zone == "arome":
        zone, nom_zone = ("boite", (-90.0, 90.0, -180.0, 180.0)), "AROME"
    else:
        zone, nom_zone = ("rayon", a.rayon_km), f"Verclause_{int(a.rayon_km)}km"
    if a.echeances:
        e0, e1 = (int(x) for x in a.echeances.split("-"))
        echeances, heures, garder = (e0, e1), e1, list(range(e0, e1 + 1))
        cle = f"{run.name}__{nom_zone}_H{e0}-{e1}"
    else:
        echeances, heures, garder = None, a.heures, None
        cle = f"{run.name}__{nom_zone}_H{a.heures}"
    if echeances and a.blocs:
        # bloc par bloc : extraction, physique, cartes, puis (option) suppression des champs du bloc
        grande = a.zone != "verclause"
        pngs, pngs_zoom, t0 = [], {}, time.time()
        for b0 in range(e0, e1 + 1, a.blocs):
            b1 = min(b0 + a.blocs - 1, e1)
            print(f"\n=== Bloc H+{b0} a H+{b1} ({time.time() - t0:.0f} s depuis le debut)", flush=True)
            cle_b = f"{run.name}__{nom_zone}_H{b0}-{b1}"
            tuiles = extrait_zone(run, zone, b1, (b0, b1), lecture, a.tuiles, cle_b)
            d = calcule_zone(run, b1, list(range(b0, b1 + 1)), a.workers, cle_b, tuiles)
            if a.supprime_champs:
                for t in tuiles:
                    t.unlink(missing_ok=True)
            if a.zooms:
                for nom in a.zooms:
                    lat0, lon0 = SITES_ZOOM[nom]
                    cle_zoom = f"{run.name}__{nom}_{int(a.zoom_km)}km_H{e0}-{e1}"
                    dz, p_bloc = figures_echeances(zoom(d, (lat0, lon0), a.zoom_km), cle_zoom, court, tuple(a.K),
                                                   a.vmin, a.vmax, False, site=(nom.replace("_", " "), lat0, lon0),
                                                   gif=False)
                    pngs_zoom.setdefault(nom, (dz, []))[1].extend(p_bloc)
            else:
                dossier, p_bloc = figures_echeances(d, cle, court, tuple(a.K), a.vmin, a.vmax, grande, gif=False)
                pngs += p_bloc
            del d; gc.collect()
        for nom, (dz, p) in pngs_zoom.items():
            fait_gif(p, dz / f"seeing_{court}_{nom}_{int(a.zoom_km)}km_H{e0}-{e1}.gif")
        if pngs:
            fait_gif(pngs, dossier / f"seeing_{court}_{nom_zone}_H{e0}-{e1}.gif")
        print(f"Termine en {time.time() - t0:.0f} s")
        return
    tuiles = extrait_zone(run, zone, heures, echeances, lecture, a.tuiles, cle)
    d = calcule_zone(run, heures, garder, a.workers, cle, tuiles)
    if echeances and a.zooms:
        for nom in a.zooms:
            lat0, lon0 = SITES_ZOOM[nom]
            cle_zoom = f"{run.name}__{nom}_{int(a.zoom_km)}km_H{echeances[0]}-{echeances[1]}"
            figures_echeances(zoom(d, (lat0, lon0), a.zoom_km), cle_zoom, court, tuple(a.K), a.vmin, a.vmax,
                              False, site=(nom.replace("_", "-"), lat0, lon0))
    elif echeances:
        figures_echeances(d, cle, court, tuple(a.K), a.vmin, a.vmax, a.zone == "france")
    else:
        figure(d, cle, court, tuple(a.K))


if __name__ == "__main__":
    main()
