#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vue du ciel a 360 degres (fisheye) du seeing V2 au-dessus d'un observatoire, avec les nuages.

Principe
  1. Zone carree de +/- --rayon-km autour du site, extraite des GRIB une seule fois (carte_seeing.extrait_zone).
  2. Physique V2 INCHANGEE maille par maille (main() de SeeingAromeV2_correction_conv_tke.py, lectures GRIB
     remplacees comme dans carte_seeing.py). On capture, pour chaque maille et chaque echeance, les profils
     Cn2(z) a K = 1, coupes exactement a H_COULIM comme calculate_seeing :
        tke  = modele BL avec la vraie TKE, sous H_COULIM
        conv = fermeture convective (trous de la TKE), sous H_COULIM
        cis  = cisaillement (atmosphere libre), au-dessus de H_COULIM
     sur une grille verticale commune en hauteur au-dessus du sol (Z_AGL = niveaux HEIGHTS du script principal,
     puis 250 m jusqu'a 20 km). Les K se changent donc sans recalcul (cube en cache).
  3. Turbulence selon l'angle de visee : pour chaque direction (azimut, angle zenithal zeta), le rayon part de
     l'observateur (sol modele de la maille du site + 10 m, premier niveau du script principal) ; a l'altitude z
     il est decale horizontalement de (z - z_obs) tan(zeta). On y lit Cn2 dans le cube 3D (interpolation lineaire,
     coordonnee verticale = hauteur au-dessus du sol AROME sous le rayon : la turbulence de couche limite suit le
     relief survole ; sous le sol, Cn2 = 0) et on integre le long du trajet :
        J(az, zeta) = sec(zeta) * integrale Cn2 dz   ->   seeing dans la direction visee (non ramene au zenith).
     Au zenith on retrouve l'integrale du script principal (controle affiche).
  4. Horizon du relief AROME (mailles de 2,5 km, courbure terrestre et refraction) : directions masquees en blanc.
  5. Nuages : nebulosites AROME basse / moyenne / haute (SP2 : lcc, mcc, hcc), supposees a 1,5 / 4,5 / 8 km
     au-dessus de l'observateur ; chaque rayon les traverse a sa hauteur, couches combinees 1 - prod(1 - c).
     Approximation de presentation (pas de transfert radiatif) : voile gris semi-transparent.

Inspire de arome_seeing_meteofetch.py (lancer de rayons, horizon, nuages, fisheye) ; ici avec la physique V2,
les GRIB deja telecharges, 500 nm, tout en TU.

Sorties
  cache_validation/ciel/<run>__ciel_<site>_<R>km_H<A>-<B>__cube.npz  (profils a K = 1, relief, nuages)
  previsions/ciel_seeing_<run>_<site>_H<A>-<B>_K<..>_echelle<..>/
      ciel_<date>_<HH>h_TU.png, ciel_<date>_<HH>h_TU_nuages.png, ciel_<site>.gif, ciel_<site>_nuages.gif

Usage (lance a la demande de l'utilisateur seulement) :
  python ciel_seeing.py <dossier du run> --sites OHP Saint_Veran [--echeances 29-37] [--rayon-km 60]
         [--elev-min 20] [--K 1 6 0.1] [--vmin 0 --vmax 5] [--workers 3] [--gif-ms 1000] [--sans-nuages]
  python ciel_seeing.py <dossier du run> --site "Mon site" 44.1 5.2
  Sans --echeances : premiere nuit complete 20h-04h TU du run (carte_seeing.FENETRE_NUIT_TU).
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import argparse, contextlib, gc, io, math, pickle, time
import numpy as np
import pandas as pd
import carte_seeing as cs

CACHE_CIEL = cs.CACHE_RACINE / "ciel"
HEIGHTS_V2 = np.array([10, 20, 35, 50, 75, 100, 150, 200, 250, 375, 500, 625, 750, 875, 1000, 1125, 1250,
                       1375, 1500, 1750, 2000, 2250, 2500, 2750, 3000], float)   # = HEIGHTS du script principal
Z_AGL = np.concatenate([HEIGHTS_V2, np.arange(3250.0, 20001.0, 250.0)])          # grille verticale du cube (m sol)
COMPOSANTES = ("tke", "conv", "cis")
K_DEFAUT = (1.0, 6.0, 0.1)          # K_TKE, K_CIS, K_conv : derniers K choisis par l'utilisateur pour les cartes (10/10)
M_PAR_DEG = 111_190.0               # longueur d'un degre de latitude (m)
K_REFR = 0.13                       # coefficient de refraction standard
R_EFF = 6.371e6 / (1.0 - K_REFR)    # rayon terrestre effectif (rayons courbes par la refraction -> droits)
PAS_AZ, PAS_ZEN = 5.0, 2.5          # resolution angulaire du fisheye (degres) ; plus fine pres de l'horizon
NUAGES = {"lcc": "bas", "mcc": "moyen", "hcc": "haut"}          # SP2 AROME
HAUTEUR_NUAGES = {"bas": 1500.0, "moyen": 4500.0, "haut": 8000.0}   # m au-dessus de l'observateur (supposees)


# ============================================================================
# PHYSIQUE V2 MAILLE PAR MAILLE + CAPTURE DES PROFILS
# ============================================================================
def profils_sol(z, bl_tke, bl_conv, fa, h, z_cible=Z_AGL):
    """Profils (3, nz) sur z_cible (m au-dessus du sol), coupes a H_COULIM exactement comme calculate_seeing :
    modele BL sous H, cisaillement au-dessus ; valeur en H interpolee ; trous et valeurs < 0 -> 0."""
    z = np.asarray(z, float)
    valid = np.isfinite(z)
    order = np.argsort(z[valid])
    zv = z[valid][order]
    out = np.zeros((3, z_cible.size), np.float32)
    if zv.size < 2:
        return out

    def clean(c):
        c = np.asarray(c, float)[valid][order]
        return np.where(np.isfinite(c) & (c >= 0), c, 0.0)

    hh = float(np.clip(h, zv[0], zv[-1]))
    below, above = zv < hh, zv > hh
    for k, c in enumerate((clean(bl_tke), clean(bl_conv))):
        x = np.r_[zv[below], hh, hh + 0.01]
        y = np.r_[c[below], np.interp(hh, zv, c), 0.0]
        out[k] = np.interp(z_cible, x, y, left=0.0, right=0.0)
    c = clean(fa)
    x = np.r_[hh - 0.01, hh, zv[above]]
    y = np.r_[0.0, np.interp(hh, zv, c), c[above]]
    out[2] = np.interp(z_cible, x, y, left=0.0, right=0.0)
    return out


def calcule_profils(j):
    """Comme carte_seeing.calcule_maille (integrales a K = 1), plus les profils Cn2 des echeances gardees.
    Processus initialise par carte_seeing._init_worker."""
    W = cs._W
    m, champs = W["m"], W["champs"]
    f_display, f_tke, f_seeing, f_empty = W["orig"]
    lat, lon = float(champs["_lat"][j]), float(champs["_lon"][j])
    m.LAT_SITE, m.LON_SITE = lat, lon

    def lecture(path, variables, allowed_types=None):
        c = champs.get(Path(path).name)
        if c is None:                  # fichier non extrait (hors echeances) : echeances incompletes
            return {}, lat, lon
        sous = {st: {v: {lv: float(a[j]) for lv, a in d[v].items()} for v in variables if v in d}
                for st, d in c["data"].items()}
        return sous, lat, lon

    state, rows, profils = {}, [], {}

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
        bl_tke = np.where(np.isfinite(raw), bl, np.nan)
        bl_conv = np.where(~np.isfinite(raw) & np.isfinite(bl), bl, np.nan)
        hh = len(rows)
        rows.append({"h": hh, "H_COULIM": h, "has_tke": state["has_tke"],
                     "I_tke": integral(z, bl_tke, none, h), "I_conv": integral(z, bl_conv, none, h),
                     "I_cis": integral(z, none, fa, h)})
        if W["garder"] is None or hh in W["garder"]:
            profils[hh] = profils_sol(z, bl_tke, bl_conv, fa, h)
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
    if W["garder"] is not None:
        rows = [r for r in rows if r["h"] in W["garder"]]
    return j, rows, profils


# ============================================================================
# NUAGES (SP2 : lcc, mcc, hcc)
# ============================================================================
def extrait_nuages(run, zone, steps):
    """{couche: {echeance: valeurs (N mailles, meme ordre que la zone)}} en fraction 0..1."""
    from eccodes import codes_grib_new_from_file, codes_get, codes_get_array, codes_release
    m = cs._load("m_nuages"); m.DATA_DIR = run
    fs = m.find_grib_files("SP2")
    carte = m.build_hour_file_map(fs, max(steps))
    out, idx = {c: {} for c in NUAGES.values()}, None
    for path in sorted({carte[h] for h in steps if h in carte}):
        with open(path, "rb") as f:
            while True:
                gid = codes_grib_new_from_file(f)
                if gid is None:
                    break
                try:
                    nom = codes_get(gid, "shortName")
                    if nom not in NUAGES:
                        continue
                    step = int(round(float(codes_get(gid, "step"))))
                    if step not in steps:
                        continue
                    if idx is None:
                        la = np.asarray(codes_get_array(gid, "latitudes"), float)
                        lo = np.asarray(codes_get_array(gid, "longitudes"), float)
                        idx = cs.zone_indices(la, lo, zone)
                    out[NUAGES[nom]][step] = np.asarray(codes_get_array(gid, "values"), float)[idx]
                finally:
                    codes_release(gid)
    vmax = max((float(np.nanmax(a)) for d in out.values() for a in d.values()), default=0.0)
    div = 100.0 if vmax > 1.5 else 1.0          # pourcentage (Meteo-France) ou deja une fraction
    return {c: {s: np.clip(a / div, 0.0, 1.0) for s, a in d.items()} for c, d in out.items()}


# ============================================================================
# CALCUL DU CUBE AUTOUR D'UN SITE (avec cache)
# ============================================================================
def cube_site(run, nom, lat0, lon0, rayon_km, echeances, workers, avec_nuages):
    a, b = echeances
    garder = list(range(a, b + 1))
    cle = f"{run.name}__ciel_{nom}_{int(rayon_km)}km_H{a}-{b}"
    fichier = CACHE_CIEL / f"{cle}__cube.npz"
    if fichier.exists():
        print(f"Cube deja calcule : {fichier.name}")
        z = np.load(fichier, allow_pickle=False)
        return {k: z[k] for k in z.files}
    dlat = rayon_km / 111.2
    dlon = rayon_km / (111.32 * math.cos(math.radians(lat0)))
    zone = ("boite", (lat0 - dlat, lat0 + dlat, lon0 - dlon, lon0 + dlon))
    t0 = time.time()
    # tuiles d'environ 6000 mailles (RAM : chaque processus charge sa tuile, ~17 ko par maille et echeance)
    n_estime = (2 * dlat / 0.025) * (2 * dlon / 0.025)
    ntuiles = max(1, int(math.ceil(n_estime / 6000)))
    tuiles = cs.extrait_zone(run, zone, b, (a, b), workers, ntuiles, cle)
    lat_m, lon_m, relief_m, bornes = [], [], [], []
    for t in tuiles:
        with open(t, "rb") as fp:
            ch = pickle.load(fp)
        bornes.append((sum(x.size for x in lat_m), ch["_lat"].size))
        lat_m.append(ch["_lat"].copy()); lon_m.append(ch["_lon"].copy()); relief_m.append(ch["_relief"].copy())
        del ch; gc.collect()
    lat_m, lon_m, relief_m = np.concatenate(lat_m), np.concatenate(lon_m), np.concatenate(relief_m)
    n = lat_m.size

    # mailles -> grille reguliere (lat, lon croissantes), remplie au fil des resultats
    lats, lons = np.unique(lat_m.round(4)), np.unique(lon_m.round(4))
    il, jl = np.searchsorted(lats, lat_m.round(4)), np.searchsorted(lons, lon_m.round(4))
    ny, nx, nt, nz = lats.size, lons.size, len(garder), Z_AGL.size
    print(f"Physique V2 + profils : {n} mailles ({ny}x{nx}), {nt} echeances, {len(tuiles)} tuile(s), "
          f"{workers} processus ; cube {3 * nt * nz * n * 4 / 1e6:.0f} Mo", flush=True)
    cube = np.zeros((3, nt, nz, ny, nx), np.float32)
    integ = np.full((3, nt, ny, nx), np.nan)
    has_tke = np.zeros((nt, ny, nx), bool)
    relief = np.full((ny, nx), np.nan)
    relief[il, jl] = relief_m
    fait = 0
    for t, (debut, nt_tuile) in zip(tuiles, bornes):
        with ProcessPoolExecutor(workers, initializer=cs._init_worker, initargs=(t, run, b, garder)) as ex:
            for jt, rows, prof in ex.map(calcule_profils, range(nt_tuile), chunksize=8):
                j = debut + jt
                for r in rows:
                    k = garder.index(r["h"])
                    integ[:, k, il[j], jl[j]] = r["I_tke"], r["I_conv"], r["I_cis"]
                    has_tke[k, il[j], jl[j]] = r["has_tke"]
                for h, p in prof.items():
                    cube[:, garder.index(h), :, il[j], jl[j]] = p
                fait += 1
                if fait % 2000 == 0 or fait == n:
                    el = time.time() - t0
                    print(f"  {fait}/{n} mailles ({el:.0f} s)", flush=True)
        t.unlink(missing_ok=True)
        gc.collect()
    out = dict(cube=cube, integ=integ, has_tke=has_tke, relief=relief, lats=lats, lons=lons,
               h=np.array(garder), z_agl=Z_AGL)
    if avec_nuages:
        nu = extrait_nuages(run, zone, set(garder))
        for couche, d in nu.items():
            g = np.full((nt, ny, nx), np.nan)
            for s, v in d.items():
                g[garder.index(s), il, jl] = v
            out[f"nuages_{couche}"] = g
    CACHE_CIEL.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(fichier, **out)
    print(f"Cube {nom} : {ny}x{nx} mailles, {nt} echeances, {nz} niveaux, en {time.time() - t0:.0f} s -> {fichier.name}")
    return out


# ============================================================================
# LANCER DE RAYONS, HORIZON, NUAGES VUS DU SITE
# ============================================================================
def trajet(z_obs, z, elev_rad):
    """Rayon rectiligne au-dessus d'une Terre spherique de rayon effectif R_EFF (refraction standard) :
    pour l'altitude z (m) atteinte, renvoie (longueur du trajet s depuis l'observateur, distance au sol d).
    Au zenith s = z - z_obs ; a l'horizon s = sqrt(r^2 - r0^2) (~170 km pour 2 km plus haut)."""
    r0, r = R_EFF + z_obs, R_EFF + np.asarray(z, float)
    se = np.sin(elev_rad)
    s = -r0 * se + np.sqrt(np.maximum((r0 * se) ** 2 + r ** 2 - r0 ** 2, 0.0))
    d = R_EFF * np.arcsin(np.clip(s * np.cos(elev_rad) / r, -1.0, 1.0))
    return s, d


def elevations(elev_min):
    """Elevations calculees (deg) : fines pres de l'horizon (le trajet y varie tres vite), 2,5 deg au-dessus de 10."""
    e = np.r_[0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, np.arange(10.0, 90.01, PAS_ZEN)]
    return e[e >= elev_min - 1e-9]


def geometrie(c, lat0, lon0, elev_min):
    """Positions des points de chaque rayon dans le cube (coordonnees fractionnaires, temps-independantes).
    Courbure terrestre comprise (rayons utilisables jusqu'a l'horizon)."""
    from scipy.ndimage import map_coordinates
    lats, lons, relief = c["lats"], c["lons"], c["relief"]
    j0, i0 = int(np.argmin(np.abs(lats - lat0))), int(np.argmin(np.abs(lons - lon0)))
    la0, lo0, sol0 = float(lats[j0]), float(lons[i0]), float(relief[j0, i0])   # origine = centre de la maille du site
    zen = np.sort(90.0 - elevations(elev_min))
    az = np.arange(0.0, 360.0, PAS_AZ)
    zs = sol0 + Z_AGL                                  # altitudes d'integration ; zs[0] = observateur (sol + 10 m)
    Zn, An = np.meshgrid(np.radians(zen), np.radians(az), indexing="ij")
    s, d = trajet(zs[0], zs[None, None, :], (np.pi / 2 - Zn)[..., None])   # (nzen, 1, nz) : trajet, distance au sol
    s = np.broadcast_to(s, Zn.shape + (zs.size,))
    d = np.broadcast_to(d, Zn.shape + (zs.size,))
    dlat, dlon = float(np.mean(np.diff(lats))), float(np.mean(np.diff(lons)))
    iy = (la0 + d * np.cos(An)[..., None] / M_PAR_DEG - lats[0]) / dlat        # Nord = cos(az)
    ix = (lo0 + d * np.sin(An)[..., None] / (M_PAR_DEG * math.cos(math.radians(la0))) - lons[0]) / dlon   # Est = sin(az)
    sol = map_coordinates(np.nan_to_num(relief), [iy, ix], order=1, mode="nearest")
    agl = zs[None, None, :] - sol                      # hauteur du rayon au-dessus du sol AROME survole
    valide = (agl >= Z_AGL[0] - 1e-6) & (agl <= Z_AGL[-1])
    iz = np.interp(agl, Z_AGL, np.arange(Z_AGL.size))
    dehors = (iy < 0) | (iy > lats.size - 1) | (ix < 0) | (ix > lons.size - 1)
    return dict(zen=zen, az=az, zs=zs, s=np.ascontiguousarray(s), coords=np.stack([iz, iy, ix]).reshape(3, -1),
                forme=iy.shape, valide=valide, dehors=dehors, j0=j0, i0=i0, la0=la0, lo0=lo0, z_obs=float(zs[0]))


def seeing_ciel(c, g, K):
    """Seeing (nt, nzen, naz) dans chaque direction + fraction de turbulence hors de la zone calculee.
    J = integrale de Cn2 le long du trajet (ds) : vaut sec(zeta) x integrale Cn2 dz en atmosphere plane,
    reste fini a l'horizon."""
    from scipy.ndimage import map_coordinates
    kt, kc, kv = K
    nt = c["cube"].shape[1]
    see, dehors = np.full((nt,) + g["forme"][:2], np.nan), np.zeros(nt)
    for t in range(nt):
        cn = (kt * c["cube"][0, t] + kv * c["cube"][1, t] + kc * c["cube"][2, t]).astype(np.float32)
        v = map_coordinates(cn, g["coords"], order=1, mode="nearest").reshape(g["forme"])
        v = np.where(g["valide"], v, 0.0)
        tot = np.trapezoid(v, g["s"], axis=-1)
        see[t] = cs.seeing_arcsec(tot)
        hors = np.trapezoid(v * g["dehors"], g["s"], axis=-1)
        dehors[t] = float(np.nanmean(hors / np.maximum(tot, 1e-30)))
    return see, dehors


def horizon(c, g, pas_m=500.0, k_refr=0.13):
    """Elevation (deg) de l'horizon du relief AROME par azimut, courbure terrestre et refraction comprises.
    Hors de la zone calculee, le relief est inconnu : suppose ne rien masquer."""
    from scipy.ndimage import map_coordinates
    lats, lons, relief = c["lats"], c["lons"], c["relief"]
    dlat, dlon = float(np.mean(np.diff(lats))), float(np.mean(np.diff(lons)))
    dmax = math.hypot(lats.size * dlat * M_PAR_DEG, lons.size * dlon * M_PAR_DEG * math.cos(math.radians(g["la0"])))
    D, A = np.meshgrid(np.arange(pas_m, dmax, pas_m), np.radians(g["az"]), indexing="ij")
    iy = (g["la0"] + D * np.cos(A) / M_PAR_DEG - lats[0]) / dlat
    ix = (g["lo0"] + D * np.sin(A) / (M_PAR_DEG * math.cos(math.radians(g["la0"]))) - lons[0]) / dlon
    sol = map_coordinates(np.nan_to_num(relief), [iy, ix], order=1, mode="constant", cval=-1e9)
    chute = (1.0 - k_refr) * D ** 2 / (2.0 * 6.371e6)
    return np.maximum(np.degrees(np.arctan2(sol - chute - g["z_obs"], D)).max(axis=0), 0.0)


def nuages_ciel(c, g):
    """Nebulosite vue dans chaque direction (nt, nzen, naz), ou None si pas de nuages dans le cube."""
    from scipy.ndimage import map_coordinates
    couches = [k for k in HAUTEUR_NUAGES if f"nuages_{k}" in c]
    if not couches:
        return None
    lats, lons = c["lats"], c["lons"]
    dlat, dlon = float(np.mean(np.diff(lats))), float(np.mean(np.diff(lons)))
    Zn, An = np.meshgrid(np.radians(g["zen"]), np.radians(g["az"]), indexing="ij")
    nt = c[f"nuages_{couches[0]}"].shape[0]
    clair = np.ones((nt,) + Zn.shape)
    for k in couches:
        d = trajet(g["z_obs"], g["z_obs"] + HAUTEUR_NUAGES[k], np.pi / 2 - Zn)[1]   # distance au sol ou le rayon perce la couche
        iy = (g["la0"] + d * np.cos(An) / M_PAR_DEG - lats[0]) / dlat
        ix = (g["lo0"] + d * np.sin(An) / (M_PAR_DEG * math.cos(math.radians(g["la0"]))) - lons[0]) / dlon
        for t in range(nt):
            clair[t] *= 1.0 - map_coordinates(np.nan_to_num(c[f"nuages_{k}"][t]), [iy, ix], order=1, mode="nearest")
    return np.clip(1.0 - clair, 0.0, 1.0)


# ============================================================================
# PLANETES (course dans le ciel du site)
# ============================================================================
# Elements kepleriens approches JPL (Standish, valables 1800-2050) : a (ua), e, I, L, longitude du perihelie,
# longitude du noeud (deg) et leurs derivees par siecle julien. Precision ~ quelques minutes d'arc.
ELEMENTS = {
    "Terre":   ((1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0),
                (0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0)),
    "Mars":    ((1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891),
                (0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343)),
    "Jupiter": ((5.20288700, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909),
                (-0.00011607, -0.00013253, -0.00183714, 3034.74612775, 0.21252668, 0.20469106)),
    "Saturne": ((9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448),
                (-0.00125060, -0.00050991, 0.00193609, 1222.49362201, -0.41897216, -0.28867794)),
}


def _helio(nom, T):
    """Position heliocentrique ecliptique J2000 (ua) au siecle julien T (tableau)."""
    el0, d = ELEMENTS[nom]
    a, e, I, L, w_bar, Om = (x0 + dx * T for x0, dx in zip(el0, d))
    I, Om, w = np.radians(I), np.radians(Om), np.radians(w_bar - Om)
    M = np.radians((L - w_bar + 180.0) % 360.0 - 180.0)
    E = M + e * np.sin(M)
    for _ in range(8):                                   # equation de Kepler (Newton)
        E = E - (E - e * np.sin(E) - M) / (1.0 - e * np.cos(E))
    xp, yp = a * (np.cos(E) - e), a * np.sqrt(1.0 - e * e) * np.sin(E)
    x = (np.cos(w) * np.cos(Om) - np.sin(w) * np.sin(Om) * np.cos(I)) * xp \
        + (-np.sin(w) * np.cos(Om) - np.cos(w) * np.sin(Om) * np.cos(I)) * yp
    y = (np.cos(w) * np.sin(Om) + np.sin(w) * np.cos(Om) * np.cos(I)) * xp \
        + (-np.sin(w) * np.sin(Om) + np.cos(w) * np.cos(Om) * np.cos(I)) * yp
    z = np.sin(w) * np.sin(I) * xp + np.cos(w) * np.sin(I) * yp
    return np.array([x, y, z])


def planete_altaz(nom, temps_tu, lat, lon):
    """(azimut depuis le Nord vers l'Est, hauteur apparente) en degres, pour des instants TU (DatetimeIndex)."""
    jd = pd.DatetimeIndex(temps_tu).to_julian_date().to_numpy()
    T = (jd - 2451545.0) / 36525.0
    g = _helio(nom, T) - _helio("Terre", T)              # vecteur geocentrique ecliptique J2000
    eps = np.radians(23.43928)
    x, y, z = g[0], g[1] * np.cos(eps) - g[2] * np.sin(eps), g[1] * np.sin(eps) + g[2] * np.cos(eps)
    ra, dec = np.arctan2(y, x), np.arcsin(z / np.sqrt(x * x + y * y + z * z))
    # precession J2000 -> date (IAU 1976)
    zeta, zz, th = (np.radians(v / 3600.0) for v in (2306.2181 * T + 0.30188 * T ** 2,
                                                      2306.2181 * T + 1.09468 * T ** 2,
                                                      2004.3109 * T - 0.42665 * T ** 2))
    A = np.cos(dec) * np.sin(ra + zeta)
    B = np.cos(th) * np.cos(dec) * np.cos(ra + zeta) - np.sin(th) * np.sin(dec)
    C = np.sin(th) * np.cos(dec) * np.cos(ra + zeta) + np.cos(th) * np.sin(dec)
    ra, dec = np.arctan2(A, B) + zz, np.arcsin(np.clip(C, -1, 1))
    gmst = np.radians((280.46061837 + 360.98564736629 * (jd - 2451545.0)) % 360.0)
    H, phi = gmst + np.radians(lon) - ra, np.radians(lat)
    alt = np.degrees(np.arcsin(np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.cos(H)))
    az = np.degrees(np.arctan2(-np.sin(H) * np.cos(dec), np.cos(phi) * np.sin(dec) - np.sin(phi) * np.cos(dec) * np.cos(H))) % 360.0
    refr = np.where(alt > -1.0, 1.02 / np.tan(np.radians(alt + 10.3 / (alt + 5.11))) / 60.0, 0.0)   # Saemundsson
    return az, alt + refr


def course_astre(nom, debut, fin, t, lat, lon):
    """Course diurne complete (24 h autour de t, pas de 2 min : tout l'arc au-dessus de l'horizon),
    positions horaires de debut a fin, position a l'instant t et 10 min apres (sens du mouvement)."""
    tj = pd.date_range(t - pd.Timedelta(hours=12), t + pd.Timedelta(hours=12), freq="2min")
    az_j, alt_j = planete_altaz(nom, tj, lat, lon)
    th = pd.date_range(debut, fin, freq="1h")
    az_h, alt_h = planete_altaz(nom, th, lat, lon)
    az_t, alt_t = planete_altaz(nom, pd.DatetimeIndex([t, t + pd.Timedelta(minutes=10)]), lat, lon)
    return dict(nom=nom, az=az_j, alt=alt_j, az_h=az_h, alt_h=alt_h, az_t=az_t, alt_t=alt_t)


# ============================================================================
# FISHEYE
# ============================================================================
def _cmap_nuages():
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("nuages", [(0.80, 0.80, 0.84, 0.0), (0.42, 0.42, 0.47, 0.82)])


def _couche_cartesienne(fig, ax, z_ordre):
    """Axe cartesien -1..1 superpose exactement au disque du fisheye."""
    fig.canvas.draw()
    ov = fig.add_axes(ax.get_position(), zorder=ax.get_zorder() + z_ordre)
    ov.set_axis_off(); ov.patch.set_alpha(0.0)
    ov.set_xlim(-1, 1); ov.set_ylim(-1, 1)
    return ov


def _pixels(n=480):
    x = np.linspace(-1, 1, n)
    X, Y = np.meshgrid(x, x)
    r = np.hypot(X, Y)
    return r, np.degrees(np.arctan2(-X, Y)) % 360.0           # Nord en haut, Est a gauche


def _voile_nuages(fig, ax, zen, az, couv):
    from scipy.interpolate import RegularGridInterpolator
    ov = _couche_cartesienne(fig, ax, 5)
    c = np.concatenate([couv, couv[:, :1]], axis=1)
    f = RegularGridInterpolator((zen, np.append(az, 360.0)), c, bounds_error=False, fill_value=None)
    r, azp = _pixels()
    val = f(np.stack([np.clip(r * 90.0, 0, zen[-1]), azp], axis=-1))
    val = np.where(r <= 1.0, np.clip(val, 0, 1), np.nan)
    ov.imshow(np.ma.masked_invalid(val), origin="lower", extent=(-1, 1, -1, 1), cmap=_cmap_nuages(),
              vmin=0, vmax=1, interpolation="bilinear", aspect="auto")


FOND, TEXTE = "black", "white"      # fond noir (demande utilisateur 12/10)


def _masque_horizon(fig, ax, az, hor, elev_min, anneaux):
    """Couleur de fond sous max(horizon du relief, elevation minimale) ; cercle = horizon a 0 deg."""
    from matplotlib.colors import to_rgba
    ov = _couche_cartesienne(fig, ax, 10)
    ax.spines["polar"].set_visible(False)
    r, azp = _pixels()
    seuil = np.maximum(np.interp(azp, np.append(az, 360.0), np.append(hor, hor[0])), elev_min)
    cache = ((90.0 - r * 90.0) < seuil) & (r <= 1.03)
    rgba = np.zeros(r.shape + (4,), np.float32)
    rgba[cache] = to_rgba(FOND)
    ov.imshow(rgba, origin="lower", extent=(-1, 1, -1, 1), interpolation="nearest", aspect="auto")
    th = np.radians(np.linspace(0, 360, 721))
    ov.plot(-np.sin(th), np.cos(th), color=TEXTE, lw=1.2)
    a = math.radians(135.0)
    for e in anneaux:
        rr = (90.0 - e) / 90.0
        ov.text(-rr * math.sin(a), rr * math.cos(a), f"{e:g}°", fontsize=8, ha="center", va="center", color=TEXTE)
    ov.set_xlim(-1, 1); ov.set_ylim(-1, 1)


COULEUR_ASTRE = {"Jupiter": "white", "Saturne": "#ffe14d", "Mars": "#ff8a65"}   # demande utilisateur 12/10

# Bandeau sous le fisheye (demande utilisateur 12/10) : mesures du seeing monitor + V2 au zenith du site,
# trait vertical a l'heure de l'image. Mesures lues par historique_sites.observations (memes filtres).
MONITEUR = {"Saint_Veran": "Saint-Veran", "OHP": "OHP", "Copernic": "Copernic", "Verclause": "Drôme"}
COULEUR_V2, COULEUR_MESURES = "#2a78d6", "#eb6834"      # = COULEUR_AROME / COULEUR_MESURES de historique_sites


def mesures_site(nom, debut, fin):
    """Mesures brutes et mediane par heure ronde (comme historique_sites) entre debut et fin, ou None."""
    if nom not in MONITEUR:
        return None
    try:
        import historique_sites as hs
        o = hs.observations(MONITEUR[nom])
    except Exception as exc:     # noqa: BLE001 - pas de mesures : bandeau avec V2 seule
        print(f"  [i] mesures {nom} illisibles ({type(exc).__name__}: {exc})")
        return None
    o = o[(o.t >= debut) & (o.t <= fin)]
    if not len(o):
        return None
    th, med, _ = hs.hourly_median(o)
    return dict(t=o.t.to_numpy(), s=o.seeing.to_numpy(), th=np.asarray(th), med=np.asarray(med))


def serie_v2_site(run, nom, g, e0, e1, workers, K):
    """Seeing V2 au zenith de la maille du site pour les echeances e0..e1 (toute la largeur du bandeau) :
    zone de quelques mailles, physique V2 inchangee (carte_seeing), integrales en cache dans cache_validation/carte."""
    d = 0.013
    zone = ("boite", (g["la0"] - d, g["la0"] + d, g["lo0"] - d, g["lo0"] + d))
    cle = f"{run.name}__site_{nom}_H{e0}-{e1}"
    tuiles = cs.extrait_zone(run, zone, e1, (e0, e1), workers, 1, cle)
    dd = cs.calcule_zone(run, e1, list(range(e0, e1 + 1)), workers, cle, tuiles)
    for t in tuiles:
        t.unlink(missing_ok=True)
    dd = cs.ajoute_seeing(dd, K)
    proche = ((dd.lat - g["la0"]) ** 2 + (dd.lon - g["lo0"]) ** 2).groupby(dd.maille).first().idxmin()
    s = dd[dd.maille == proche].sort_values("t")
    return pd.DatetimeIndex(s.t), s.seeing.to_numpy()


def _bandeau(fig, rect, b):
    """Serie temporelle : mesures (points + mediane horaire), V2 au zenith, trait vertical a l'instant t."""
    import matplotlib.dates as mdates
    ax = fig.add_axes(rect, facecolor=FOND)
    m = b.get("mes")
    if m is not None:
        ax.plot(m["t"], m["s"], ".", ms=2.5, color=COULEUR_MESURES, alpha=0.45, lw=0)
        ax.plot(m["th"], m["med"], "-o", ms=3.5, lw=1.4, color=COULEUR_MESURES, label=f"mesures {b['moniteur']}")
    elif b.get("moniteur"):
        ax.text(0.01, 0.85, f"pas de mesures {b['moniteur']} sur la période", transform=ax.transAxes,
                fontsize=7.5, color="0.7")
    ax.plot(b["tv"], b["v2"], "-o", ms=3.5, lw=1.6, color=COULEUR_V2, label="AROME V2 (zénith)")
    ax.axvline(b["t"], color=TEXTE, lw=1.3)
    vals = np.concatenate([np.asarray(b["v2"], float)] + ([m["med"]] if m is not None else []))
    haut = float(np.nanmax(vals)) if np.isfinite(vals).any() else 3.0
    ax.set_ylim(0, min(max(3.0, 1.25 * haut), 10.0))
    ax.set_xlim(b["xlim"])
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Hh"))
    ax.set_ylabel('seeing (")', color=TEXTE, fontsize=8)
    ax.tick_params(colors=TEXTE, labelsize=7.5)
    for sp in ax.spines.values():
        sp.set_color("0.6")
    ax.grid(color="0.35", lw=0.5)
    ax.legend(loc="upper right", fontsize=7, facecolor=FOND, edgecolor="0.5", labelcolor=TEXTE, ncol=2)
    ax.set_title("heure TU", fontsize=7.5, color="0.7", loc="left", pad=2)


def _xy(az, alt):
    """Fisheye : Nord en haut, Est a gauche, rayon proportionnel a la distance zenithale."""
    r = (90.0 - np.asarray(alt, float)) / 90.0
    return -r * np.sin(np.radians(az)), r * np.cos(np.radians(az))


def _courses(fig, ax, astres, az_h, hor, elev_min):
    """Courses des planetes au-dessus de max(elev_min, horizon du relief) :
    fine ligne continue = arc diurne complet dans le ciel ; petits points = positions heure par heure sur la nuit ;
    gros point + fleche = position a l'instant de l'image et sens du mouvement."""
    import matplotlib.patheffects as pe
    ov = _couche_cartesienne(fig, ax, 15)
    halo = [pe.withStroke(linewidth=2.4, foreground="k")]
    azb, horb = np.append(az_h, 360.0), np.append(hor, hor[0])
    visible = lambda az, alt: alt >= np.maximum(np.interp(az, azb, horb), elev_min)   # noqa: E731
    for a in astres:
        coul = COULEUR_ASTRE.get(a["nom"], "white")
        x, y = _xy(a["az"], a["alt"])
        vis = visible(a["az"], a["alt"])
        ov.plot(np.where(vis, x, np.nan), np.where(vis, y, np.nan), lw=0.9, color=coul)
        xh, yh = _xy(a["az_h"], a["alt_h"])
        vh = visible(a["az_h"], a["alt_h"])
        ov.plot(xh[vh], yh[vh], "o", ms=3.2, color=coul, mec="k", mew=0.6)
        if visible(a["az_t"][0], a["alt_t"][0]):
            (x0, x1), (y0, y1) = _xy(a["az_t"], a["alt_t"])
            ov.plot(x0, y0, "o", ms=9, color=coul, mec="k", mew=1.2)
            n = math.hypot(x1 - x0, y1 - y0) or 1.0
            ux, uy = (x1 - x0) / n, (y1 - y0) / n
            ov.annotate("", xy=(x0 + 0.11 * ux, y0 + 0.11 * uy), xytext=(x0 + 0.03 * ux, y0 + 0.03 * uy),
                        arrowprops=dict(arrowstyle="-|>", color=coul, lw=1.6, mutation_scale=12))
            ov.annotate(f"{a['nom']} {a['alt_t'][0]:.0f}°", (x0, y0), xytext=(8, -12), textcoords="offset points",
                        fontsize=8.5, fontweight="bold", color=coul, path_effects=halo)
    ov.set_xlim(-1, 1); ov.set_ylim(-1, 1)


def fisheye(png, see, zen, az, hor, elev_min, vmin, vmax, titre, pied, couv=None, astres=(), bandeau=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import textwrap
    if bandeau is None:
        fig = plt.figure(figsize=(7.6, 7.6), dpi=100, facecolor=FOND)
        ax = fig.add_subplot(111, projection="polar", facecolor=FOND)
    else:                                # fisheye en haut, bandeau temporel en bas
        fig = plt.figure(figsize=(7.6, 9.2), dpi=100, facecolor=FOND)
        ax = fig.add_axes([0.04, 0.25, 0.74, 0.66], projection="polar", facecolor=FOND)
        _bandeau(fig, [0.11, 0.075, 0.72, 0.12], bandeau)
    data = np.concatenate([see, see[:, :1]], axis=1)
    im = ax.pcolormesh(np.radians(np.append(az, 360.0)), zen, data, cmap=cs.CMAP, vmin=vmin, vmax=vmax,
                       shading="gouraud")
    ax.set_theta_zero_location("N"); ax.set_theta_direction(1)     # Est a gauche : ciel vu depuis le sol
    ax.set_rlim(0, 90)
    anneaux = [e for e in (60, 45, 30, 15) if e > elev_min] + ([elev_min] if elev_min >= 5 else []) + [0]
    ax.set_yticks([90.0 - e for e in anneaux]); ax.set_yticklabels([])
    ax.set_xticks(np.radians([0, 90, 180, 270]))
    ax.set_xticklabels(["N", "E", "S", "O"], fontsize=12, fontweight="bold", color=TEXTE)
    ax.grid(color="white", alpha=0.45, lw=0.6)
    ax.plot([0], [0], "+", color="k", ms=9, mew=1.5)
    ax.set_title(titre, fontsize=9, pad=18, color=TEXTE)
    if bandeau is None:
        cb = fig.colorbar(im, ax=ax, extend="max", shrink=0.78, pad=0.09)
    else:
        cb = fig.colorbar(im, cax=fig.add_axes([0.84, 0.33, 0.022, 0.5]), extend="max")
    cb.set_label('seeing dans la direction visée (")', color=TEXTE)
    cb.ax.tick_params(colors=TEXTE)
    cb.outline.set_edgecolor(TEXTE)
    fig.text(0.02, 0.008 if bandeau is not None else 0.015, "\n".join(textwrap.wrap(pied, 120)),
             fontsize=7.5 if bandeau is None else 6.8, color="0.7")
    if couv is not None:
        _voile_nuages(fig, ax, zen, az, couv)
    _masque_horizon(fig, ax, az, hor, elev_min, anneaux)
    if astres:
        _courses(fig, ax, astres, az, hor, elev_min)
    fig.savefig(png, facecolor=FOND)     # taille fixe (pas de bbox_inches) : images du GIF identiques
    plt.close(fig)


# ============================================================================
# PROGRAMME
# ============================================================================
def premiere_nuit(run):
    """Echeances de la premiere nuit complete FENETRE_NUIT_TU du run (H >= 1)."""
    m = cs._load("m_cycle"); m.DATA_DIR = run
    cycle = pd.Timestamp(m.get_grib_cycle_datetime(m.find_grib_files("HP1")[0]))
    h0, h1 = cs.FENETRE_NUIT_TU
    debut = cycle.normalize() + pd.Timedelta(hours=h0)
    while debut < cycle + pd.Timedelta(hours=1):
        debut += pd.Timedelta(days=1)
    a = int((debut - cycle) / pd.Timedelta(hours=1))
    return cycle, (a, a + (h1 - h0) % 24)


def traite_site(run, nom, lat0, lon0, a, cycle):
    court = run.name.replace("AROME_download_", "")
    e0, e1 = a.echeances
    c = cube_site(run, nom, lat0, lon0, a.rayon_km, a.echeances, a.workers, not a.sans_nuages)
    K = tuple(a.K)
    g = geometrie(c, lat0, lon0, a.elev_min)
    see, dehors = seeing_ciel(c, g, K)
    hor = horizon(c, g)
    masque = (90.0 - g["zen"])[:, None] < hor[None, :]
    couv = None if a.sans_nuages else nuages_ciel(c, g)
    kt, kc, kv = K
    I = c["integ"][:, :, g["j0"], g["i0"]]
    J_carte = kt * I[0] + kv * I[1] + kc * I[2]
    zen_carte = cs.seeing_arcsec(J_carte)
    print(f"{nom} : maille {g['la0']:.4f} N {g['lo0']:.4f} E, sol AROME {g['z_obs'] - Z_AGL[0]:.0f} m ; "
          f"horizon du relief jusqu'a {hor.max():.1f}° ; {100 * masque.mean():.0f} % des directions masquees")
    print(f"  controle zenith (rayon / integrale V2 a la maille) : ecart moyen "
          f"{100 * np.nanmean(np.abs(see[:, 0, 0] / zen_carte - 1)):.1f} %")
    if dehors.max() > 0.05:
        print(f"  [!] jusqu'a {100 * dehors.max():.0f} % de la turbulence des rayons passe hors de la zone "
              f"(+/- {a.rayon_km:g} km) : augmenter --rayon-km")
    dossier = cs.OUT / (f"ciel_seeing_{court}_{nom}_H{e0}-{e1}_K{kt:g}-{kc:g}-{kv:g}_echelle{a.vmin:g}-{a.vmax:g}"
                        + ("" if cs.CMAP == "viridis" else f"_{cs.CMAP}"))
    dossier.mkdir(parents=True, exist_ok=True)
    pngs, pngs_n = [], []
    t_debut, t_fin = cycle + pd.Timedelta(hours=int(c["h"][0])), cycle + pd.Timedelta(hours=int(c["h"][-1]))
    xlim = (t_debut - pd.Timedelta(hours=1), t_fin + pd.Timedelta(hours=1))
    tv, v2 = pd.DatetimeIndex([cycle + pd.Timedelta(hours=int(h)) for h in c["h"]]), zen_carte
    mes = None if a.sans_bandeau else mesures_site(nom, *xlim)
    if not a.sans_bandeau:
        b0, b1 = max(1, e0 - 1), e1 + 1               # prevision sur toute la largeur du bandeau
        try:
            tv, v2 = serie_v2_site(run, nom, g, b0, b1, a.workers, K)
            commun = np.isin(tv, [cycle + pd.Timedelta(hours=int(h)) for h in c["h"]])
            print(f"  bandeau : V2 au site de H+{b0} a H+{b1} (ecart avec le cube aux heures communes : "
                  f"{100 * np.nanmax(np.abs(v2[commun] / zen_carte - 1)):.2g} %)")
        except Exception as exc:     # noqa: BLE001 - on garde les heures du cube
            print(f"  [i] V2 au site sur tout le bandeau indisponible ({type(exc).__name__}: {exc})")
        print(f"  bandeau : {'aucune mesure' if mes is None else f'{len(mes['s'])} mesures'} "
              f"{MONITEUR.get(nom, '(pas de seeing monitor)')} entre {xlim[0]:%d/%m %H}h et {xlim[1]:%d/%m %H}h TU")
    for nom_a in a.astres:
        az_a, alt_a = planete_altaz(nom_a, pd.date_range(t_debut, t_fin, freq="1h"), g["la0"], g["lo0"])
        print(f"  {nom_a} : hauteur {', '.join(f'{x:.0f}' for x in alt_a)}° (de {t_debut:%H}h a {t_fin:%H}h TU), "
              f"azimut {az_a[0]:.0f}° -> {az_a[-1]:.0f}°")
    for k, h in enumerate(c["h"]):
        t = cycle + pd.Timedelta(hours=int(h))
        astres = [course_astre(n_a, t_debut, t_fin, t, g["la0"], g["lo0"]) for n_a in a.astres]
        bandeau = None if a.sans_bandeau else dict(tv=tv, v2=v2, t=t, xlim=xlim, mes=mes,
                                                   moniteur=MONITEUR.get(nom))
        s = np.where(masque, np.nan, see[k])
        if not c["has_tke"][k, g["j0"], g["i0"]] or not np.isfinite(s).any():
            print(f"  {t:%d/%m %H}h TU : pas de seeing (echeance incomplete ou sans TKE)")
            continue
        titre = (f"{nom.replace('_', ' ')} — {t:%d/%m/%Y %H}h TU (H+{int(h):02d})\n"
                 f"zénith {see[k, 0, 0]:.2f}\", min {np.nanmin(s):.2f}\", max {np.nanmax(s):.2f}\"")
        pied = f"run {court} — K_TKE = {kt:g}  K_CIS = {kc:g}  K_conv = {kv:g} — physique V2"
        png = dossier / f"ciel_{t:%Y-%m-%d_%H}h_TU.png"
        if astres:
            pied += (f" — {', '.join(a.astres)} : arc diurne complet, un point par heure de {t_debut:%H}h "
                     f"à {t_fin:%H}h TU, flèche = sens du mouvement")
        fisheye(png, see[k], g["zen"], g["az"], hor, a.elev_min, a.vmin, a.vmax, titre, pied, astres=astres,
                bandeau=bandeau)
        pngs.append(png)
        if couv is not None:
            png = dossier / f"ciel_{t:%Y-%m-%d_%H}h_TU_nuages.png"
            fisheye(png, see[k], g["zen"], g["az"], hor, a.elev_min, a.vmin, a.vmax,
                    titre + f"\ngris : nuages AROME projetés (approx.), {100 * np.nanmean(couv[k]):.0f} % du ciel",
                    pied, couv=couv[k], astres=astres, bandeau=bandeau)
            pngs_n.append(png)
        print(f"  {t:%d/%m %H}h TU : zenith {see[k, 0, 0]:.2f}\", visible {np.nanmin(s):.2f}-{np.nanmax(s):.2f}\""
              + (f", nuages {100 * np.nanmean(couv[k]):.0f} %" if couv is not None else ""), flush=True)
    if pngs:
        cs.fait_gif(pngs, dossier / f"ciel_{nom}.gif", a.gif_ms)
    if pngs_n:
        cs.fait_gif(pngs_n, dossier / f"ciel_{nom}_nuages.gif", a.gif_ms)


def main():
    p = argparse.ArgumentParser(description="Vue du ciel a 360 degres du seeing V2 (fisheye) avec nuages")
    p.add_argument("run")
    p.add_argument("--sites", nargs="+", default=[], choices=sorted(cs.SITES_ZOOM))
    p.add_argument("--site", nargs=3, action="append", default=[], metavar=("NOM", "LAT", "LON"))
    p.add_argument("--echeances", help="A-B (defaut : premiere nuit 20h-04h TU du run)")
    p.add_argument("--rayon-km", type=float, default=250.0,
                   help="demi-cote de la zone calculee : a 1° de hauteur le rayon est a ~8 km au-dessus de "
                        "l'observateur a 250 km (au-dela : maille du bord)")
    p.add_argument("--elev-min", type=float, default=1.0,
                   help="hauteur minimale calculee (1° : demande utilisateur 12/10 ; en dessous, blanc)")
    p.add_argument("--K", type=float, nargs=3, default=K_DEFAUT, metavar=("K_TKE", "K_CIS", "K_CONV"))
    p.add_argument("--vmin", type=float, default=0.0)
    p.add_argument("--vmax", type=float, default=5.0)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--gif-ms", type=int, default=cs.GIF_MS)
    p.add_argument("--sans-nuages", action="store_true")
    p.add_argument("--sans-bandeau", action="store_true", help="pas de bandeau mesures + V2 sous le fisheye")
    p.add_argument("--astres", nargs="*", default=["Jupiter", "Saturne"], choices=["Mars", "Jupiter", "Saturne"],
                   help="courses de planetes a tracer (--astres sans nom : aucune)")
    a = p.parse_args()
    run = Path(a.run)
    sites = [(n, *cs.SITES_ZOOM[n]) for n in a.sites] + [(n.replace(" ", "_"), float(la), float(lo)) for n, la, lo in a.site]
    if not sites:
        p.error("donner au moins un site (--sites ou --site NOM LAT LON)")
    cycle, nuit = premiere_nuit(run)
    a.echeances = tuple(int(x) for x in a.echeances.split("-")) if a.echeances else nuit
    print(f"Run {cycle:%d/%m/%Y %H}Z, echeances H+{a.echeances[0]} a H+{a.echeances[1]} "
          f"({cycle + pd.Timedelta(hours=a.echeances[0]):%d/%m %H}h -> "
          f"{cycle + pd.Timedelta(hours=a.echeances[1]):%d/%m %H}h TU), sites : {', '.join(s[0] for s in sites)}")
    for nom, lat0, lon0 in sites:
        traite_site(run, nom, lat0, lon0, a, cycle)


if __name__ == "__main__":
    main()
