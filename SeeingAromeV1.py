#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calcul du seeing optique AROME - profil complet jusqu'aux niveaux isobares.

Base : calcul utilisateur HP1/HP2 + modele cisaillement sur IP1.

Nouveautes :
- SP2:h est utilise comme altitude du relief AROME (confirme sur les GRIB
  locaux de l'utilisateur).
- IP1 fournit T/U/V/Z sur les niveaux isobares 1000--100 hPa.
- IP4 fournit TKE sur les niveaux isobares 1000--100 hPa.
- La limite physique des deux modeles est H_COULIM, pas 3000 m.
- 3000 m est uniquement la limite des grilles HP1/HP2.
- Si H_COULIM <= 3000 m : TKE HP2 jusqu'a H_COULIM, puis cisaillement IP1.
- Si H_COULIM > 3000 m : TKE HP2 jusqu'a 3000 m, puis TKE IP4 jusqu'a
  H_COULIM, puis cisaillement IP1 au-dessus.
- L'integration de Cn2 se fait sur le profil natif combine, sans interpolation.
- L'interpolation verticale n'est utilisee que pour la figure.

IMPORTANT :
- Le script ne telecharge rien.
- Il utilise les GRIB2 deja presents dans DATA_DIR.
"""
from pathlib import Path
import re
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from eccodes import (codes_grib_new_from_file,codes_get,codes_get_array,codes_release,)
# ============================================================================
# CONFIGURATION
# ============================================================================
DATA_DIR = Path("AROME_download_2109_12h30")
FORECAST_HOURS = 51
# ======    Sites d'observations    =========
# LAT_SITE = 43.9500;  LON_SITE  =  4.81667   #   Avignon 
# LAT_SITE = 48.8566;  LON_SITE  =  2.3522   #   Paris 
# LAT_SITE = 42.93642; LON_SITE  =  0.14122  #   Pic Du Midi Observatoire 
# LAT_SITE = 45.8326 ;  LON_SITE  =  6.8652    #   Mont Blanc
# -------------   Seeing monitor disponibles :   ------------------------------
# LAT_SITE = 44.5828;  LON_SITE  =  5.9868   #   Asso Copernicus
# LAT_SITE = 44.3814;  LON_SITE  =  5.4286   #   VERCLAUSE
# LAT_SITE = 38;  LON_SITE  =  -2.55   #espagne

# LAT_SITE = 44.1952; LON_SITE = 5.4716  #cosmodrome

LAT_SITE = 44.6988; LON_SITE =  6.9083   #Observatoire Saint Veran
K_TKE = 1.8 ; K_CIS = 1

# ============================================================================
#                         VERCLAUSE
# ============================================================================
# LAT_SITE = 44.3814;  LON_SITE  =  5.4286   #   VERCLAUSE
# K_TKE = 4 ; K_CIS = 40
# ============================================================================


# SBIG : les dates du CSV d'extraction sont ignorées volontairement.
# Les points correspondent à la nuit du 13 au 14 septembre 2026,
# de 20:50 à 05:45 heure locale France.
# Pour l'affichage AROME/SBIG commun en TU, on retire 2 h.

# OBS_SEEING_CSV = Path(__file__).resolve().parent / "seeing_16-17_septembre_2026_UTC_SaintVeran2.csv"
# SBIG_START_TU = datetime(2026, 9, 16, 18, 10)
# heure_depart_TU = 18.0 + 50.0 / 60.0
# SBIG_SAMPLE_MINUTES = 5

# csv_path = "seeing_16-17_septembre_2026_UTCplus2_SaintVeran3.csv"
# df2 = pd.read_csv(csv_path)
# df2["UTC+2"] = pd.to_datetime(df2["UTC+2"], format="%d/%m/%Y %H:%M")

# csv_path = "Saint_veran_18_09_2026_jour_2.csv"
# df3 = pd.read_csv(csv_path)
# df3["UTC"] = pd.to_datetime(df3["UTC"])
# df3["seeing_median"]=(df3["seeing_arcsec"].rolling(window=5, center=True).median())



#=============================
affichage_altitude = 4000
#======= Coeef ===============
# K_TKE = 4
# K_CIS = 40
#=============================
G           = 9.81
R_OVER_CP   = 0.286
P0_HPA      = 1000.0
LAMBDA      = 500e-9
ARCSEC      = 206265.0

HEIGHTS = np.array([
    10, 20, 35, 50, 75, 100, 150, 200, 250,
    375, 500, 625, 750, 875, 1000, 1125, 1250,
    1375, 1500, 1750, 2000, 2250, 2500, 2750, 3000
], dtype=float)


# ============================================================================
# OUTILS GRIB
# ============================================================================

def _get(gid, key, default=None):
    try:
        return codes_get(gid, key)
    except Exception:
        return default


def get_nearest_index(gid):
    lats = np.asarray(codes_get_array(gid, "latitudes"), dtype=float)
    lons = np.asarray(codes_get_array(gid, "longitudes"), dtype=float)

    lons_norm = ((lons + 180.0) % 360.0) - 180.0
    target_lon = ((LON_SITE + 180.0) % 360.0) - 180.0

    dist2 = (lats - LAT_SITE) ** 2 + (lons_norm - target_lon) ** 2
    idx = int(np.nanargmin(dist2))
    return idx, float(lats[idx]), float(lons_norm[idx])


def extract_message_value(gid, nearest_index):
    values = np.asarray(codes_get_array(gid, "values"), dtype=float)
    if nearest_index >= values.size:
        raise IndexError(
            f"Indice grille {nearest_index} hors tableau de taille {values.size}."
        )
    return float(values[nearest_index])


def get_message_step(gid):
    for key in ("step", "endStep", "forecastTime"):
        value = _get(gid, key, None)
        if value is not None:
            try:
                return int(round(float(value)))
            except Exception:
                pass
    return None


def read_grib_package(path, variables, allowed_types=None):
    """Retourne data[step][shortName][level] = valeur au point cible."""
    data = {}
    nearest_index = None
    grid_lat = None
    grid_lon = None
    found_steps = set()

    if allowed_types is None:
        allowed_types = {"heightAboveGround", "isobaricInhPa", "surface"}

    with open(path, "rb") as f:
        message_number = 0

        while True:
            try:
                gid = codes_grib_new_from_file(f)
            except Exception as exc:
                # Certains fichiers téléchargés peuvent être tronqués en fin
                # de fichier. On conserve les messages GRIB valides déjà lus
                # et on signale clairement le problème.
                print(
                    f"  ⚠️ Fin de fichier GRIB prématurée dans {path.name} "
                    f"(message ~{message_number + 1}) : {exc}"
                )
                break

            if gid is None:
                break

            message_number += 1

            try:
                short_name = _get(gid, "shortName")
                type_of_level = _get(gid, "typeOfLevel")
                level = _get(gid, "level")
                step = get_message_step(gid)

                if short_name not in variables:
                    continue
                if type_of_level not in allowed_types:
                    continue
                if step is None:
                    continue

                if level is None:
                    level = 0.0

                found_steps.add(step)

                # Dans un fichier GRIB AROME, la grille est fixe :
                # calculer la maille la plus proche sur chaque message est
                # tres couteux car cela relit tout le champ lat/lon.
                # On le fait une seule fois par fichier.
                if nearest_index is None:
                    nearest_index, grid_lat, grid_lon = get_nearest_index(gid)

                value = extract_message_value(gid, nearest_index)
                data.setdefault(step, {}).setdefault(short_name, {})[float(level)] = value

            finally:
                codes_release(gid)

    if not data:
        raise RuntimeError(f"Aucune donnée utile trouvée dans {path.name}.")

    print(f"  {path.name} : steps = {sorted(found_steps)}")
    if not found_steps:
        raise RuntimeError(
            f"Aucun message exploitable trouvé dans {path.name}. "
            "Le fichier est probablement vide ou corrompu."
        )
    return data, grid_lat, grid_lon


# ============================================================================
# FICHIERS
# ============================================================================

def find_grib_files(package):
    files = sorted(DATA_DIR.glob(f"arome__0025__{package}__*.grib2"))
    if not files:
        raise FileNotFoundError(f"Aucun fichier {package} dans {DATA_DIR}")
    return files


def parse_forecast_range(path):
    match = re.search(r"__(\d{2})H(\d{2})H__", path.name)
    if not match:
        raise ValueError(f"Impossible de lire la tranche temporelle de {path.name}")
    return int(match.group(1)), int(match.group(2))


def build_hour_file_map(files, max_hour):
    """Associe chaque echeance a son fichier sans reparcourir les fichiers."""
    hour_map = {}
    ranges = [(path, *parse_forecast_range(path)) for path in files]
    for path, start, end in ranges:
        for hour in range(max(0, start), min(max_hour, end) + 1):
            hour_map[hour] = path
    return hour_map


def select_file_for_hour(files_or_map, hour):
    # Compatibilite : accepte encore une liste de fichiers.
    if isinstance(files_or_map, dict):
        try:
            return files_or_map[hour]
        except KeyError:
            raise FileNotFoundError(f"Aucun fichier pour H+{hour}")
    for path in files_or_map:
        start, end = parse_forecast_range(path)
        if start <= hour <= end:
            return path
    raise FileNotFoundError(f"Aucun fichier pour H+{hour}")


# ============================================================================
# SP2 : H_COULIM + ALTITUDE h
# ============================================================================

def get_h_coulim(sp2_data, hour):
    source = sp2_data.get(hour, {})
    for name in ("h_coulim", "blh"):
        values = source.get(name, {})
        if values:
            value = next(iter(values.values()))
            if np.isfinite(value):
                return float(value)
    return np.nan


def read_surface_h(path):
    """Lit directement SP2:h sur la maille la plus proche du site."""
    with open(path, "rb") as f:
        message_number = 0
        while True:
            try:
                gid = codes_grib_new_from_file(f)
            except Exception as exc:
                print(
                    f"  ⚠️ Fin de fichier GRIB prématurée dans {path.name} "
                    f"(message ~{message_number + 1}) : {exc}"
                )
                break

            if gid is None:
                break

            message_number += 1
            try:
                short_name = _get(gid, "shortName")
                type_of_level = _get(gid, "typeOfLevel")
                level = _get(gid, "level")

                if short_name != "h":
                    continue
                if type_of_level != "surface":
                    continue
                if level is not None and float(level) != 0.0:
                    continue

                # Même logique que le script diagnostic : coordonnées et
                # valeurs sont lues sur CE message h lui-même.
                idx, grid_lat, grid_lon = get_nearest_index(gid)
                values = np.asarray(codes_get_array(gid, "values"), dtype=float)
                if idx >= values.size:
                    raise IndexError(
                        f"Indice grille {idx} hors tableau h de taille {values.size}."
                    )

                h = float(values[idx])
                if not np.isfinite(h):
                    raise RuntimeError(f"SP2:h non fini dans {path.name}.")

                return h, grid_lat, grid_lon
            finally:
                codes_release(gid)

    raise RuntimeError(f"SP2:h introuvable dans {path.name}.")


# ============================================================================
# PROFILS HAG
# ============================================================================

def build_hag_profile(hp1_data, hp2_data, hour, grid_lat, grid_lon):
    hp1 = hp1_data.get(hour)
    if hp1 is None:
        raise KeyError(f"H+{hour} absent de HP1.")

    hp2 = hp2_data.get(hour)

    def arr(source, variable):
        out = np.full(len(HEIGHTS), np.nan)
        if source is None or variable not in source:
            return out
        for i, h in enumerate(HEIGHTS):
            if h in source[variable]:
                out[i] = source[variable][h]
        return out

    T = arr(hp1, "t")
    U = arr(hp1, "u")
    V = arr(hp1, "v")
    P = arr(hp1, "pres")
    TKE = arr(hp2, "tke") if hp2 is not None else np.full(len(HEIGHTS), np.nan)

    # MeteoFetch/GRIB : pres peut etre en Pa ou hPa selon le mapping.
    finite_p = P[np.isfinite(P)]
    if finite_p.size and np.nanmedian(finite_p) > 2000:
        P /= 100.0

    return {
        "z": HEIGHTS.copy(),
        "T": T,
        "U": U,
        "V": V,
        "P": P,
        "TKE": TKE,
        "grid_lat": grid_lat,
        "grid_lon": grid_lon,
    }


# ============================================================================
# PROFILS ISOBARIQUES IP1 / IP4
# ============================================================================

def make_isobaric_profile(ip1_data, hour, surface_altitude, grid_lat, grid_lon):
    """Construit le profil IP1 pour une échéance, en altitude AGL."""

    ip1 = ip1_data.get(hour)
    if ip1 is None:
        raise KeyError(f"H+{hour} absent de IP1.")

    # read_grib_package produit :
    # ip1_data[step]["t"][niveau] = valeur
    # et non ip1_data["t"] directement.
    # Une seule liste de niveaux est construite et reutilisee.
    levels = sorted(ip1.get("z", {}).keys())
    z = np.asarray([ip1["z"][lev] for lev in levels], dtype=float) / G
    T = np.asarray([ip1.get("t", {}).get(lev, np.nan) for lev in levels], dtype=float)
    U = np.asarray([ip1.get("u", {}).get(lev, np.nan) for lev in levels], dtype=float)
    V = np.asarray([ip1.get("v", {}).get(lev, np.nan) for lev in levels], dtype=float)

    # IP1 Z -> altitude AGL par rapport au relief SP2/h.
    if np.isfinite(surface_altitude):
        z = z - surface_altitude

    # Niveaux sous le terrain exclus.
    valid = (
        np.isfinite(z)
        & np.isfinite(T)
        & np.isfinite(U)
        & np.isfinite(V)
        & (z > 0)
    )

    z, T, U, V = z[valid], T[valid], U[valid], V[valid]

    order = np.argsort(z)
    z, T, U, V = z[order], T[order], U[order], V[order]

    # Suppression des doublons éventuels en altitude.
    if z.size:
        keep = np.r_[True, np.diff(z) > 1e-6]
        z, T, U, V = z[keep], T[keep], U[keep], V[keep]

    return {
        "z": z,
        "T": T,
        "U": U,
        "V": V,
        "P": np.asarray([lev for lev in levels], dtype=float)[valid][order],
        "surface_altitude": surface_altitude,
        "grid_lat": grid_lat,
        "grid_lon": grid_lon,
    }



def add_ip4_tke(profile_iso, ip4_data, hour):
    """Ajoute TKE IP4 aux niveaux isobares communs avec IP1."""
    source = ip4_data.get(hour, {})
    out = np.full_like(profile_iso["z"], np.nan, dtype=float)

    tke_by_p = source.get("tke", {})
    if not tke_by_p:
        return out

    # Cas normal : les niveaux isobares sont exactement les memes cles.
    missing = []
    for i, p in enumerate(profile_iso["P"]):
        value = tke_by_p.get(float(p))
        if value is None:
            missing.append((i, float(p)))
        else:
            out[i] = value

    # Fallback de compatibilite uniquement pour les rares discrepances
    # de representation flottante.
    if missing:
        p4_keys = np.fromiter(tke_by_p.keys(), dtype=float)
        p4_values = np.fromiter(tke_by_p.values(), dtype=float)
        for i, p in missing:
            j = np.flatnonzero(np.isclose(p4_keys, p, rtol=0, atol=1e-6))
            if j.size:
                out[i] = p4_values[j[0]]

    return out


# ============================================================================
# PHYSIQUE
# ============================================================================

def calculate_cn2_tke(profile):
    z = np.asarray(profile["z"], dtype=float)
    T = np.asarray(profile["T"], dtype=float)
    U = np.asarray(profile["U"], dtype=float)
    V = np.asarray(profile["V"], dtype=float)
    P = np.asarray(profile["P"], dtype=float)
    E = np.asarray(profile["TKE"], dtype=float)

    # Aucun niveau dans la couche TKE :
    # cas possible lorsque H_COULIM est inférieur au premier
    # niveau vertical disponible.
    if z.size < 2:
        return {
            **profile,
            "theta": np.full_like(z, np.nan, dtype=float),
            "dtheta_dz": np.full_like(z, np.nan, dtype=float),
            "dU_dz": np.full_like(z, np.nan, dtype=float),
            "dV_dz": np.full_like(z, np.nan, dtype=float),
            "L": np.full_like(z, np.nan, dtype=float),
            "Cn2": np.full_like(z, np.nan, dtype=float),
        }

    theta = T * (P0_HPA / P) ** R_OVER_CP

    dtheta_dz = np.gradient(theta, z)
    dU_dz = np.gradient(U, z)
    dV_dz = np.gradient(V, z)

    L = np.full_like(z, np.nan)

    stable = (
        np.isfinite(E)
        & np.isfinite(theta)
        & np.isfinite(dtheta_dz)
        & (E > 0)
        & (dtheta_dz > 0)
    )

    L[stable] = np.sqrt(
        2.0 * E[stable]
        / ((G / theta[stable]) * dtheta_dz[stable])
    )

    cn2 = np.full_like(z, np.nan)

    valid = (
        stable
        & np.isfinite(L)
        & (L > 0)
        & np.isfinite(P)
        & np.isfinite(T)
        & (T > 0)
    )

    cn2[valid] = (
        K_TKE
        * (80e-6 * P[valid] / (T[valid] * theta[valid])) ** 2
        * L[valid] ** (4.0 / 3.0)
        * dtheta_dz[valid] ** 2
    )

    return {
        **profile,
        "theta": theta,
        "dtheta_dz": dtheta_dz,
        "dU_dz": dU_dz,
        "dV_dz": dV_dz,
        "L": L,
        "Cn2": cn2,
    }


def calculate_cn2_shear(profile):
    z = np.asarray(profile["z"], dtype=float)
    T = np.asarray(profile["T"], dtype=float)
    U = np.asarray(profile["U"], dtype=float)
    V = np.asarray(profile["V"], dtype=float)
    P = np.asarray(profile["P"], dtype=float)

    theta = T * (P0_HPA / P) ** R_OVER_CP
    dtheta_dz = np.gradient(theta, z)
    dU_dz = np.gradient(U, z)
    dV_dz = np.gradient(V, z)

    S = np.sqrt(dU_dz ** 2 + dV_dz ** 2)
    E = S ** 2

    L = np.full_like(z, np.nan)
    stable = (
        np.isfinite(E) & np.isfinite(theta) & np.isfinite(dtheta_dz)
        & (E > 0) & (dtheta_dz > 0)
    )
    L[stable] = np.sqrt(
        2.0 * E[stable] / ((G / theta[stable]) * dtheta_dz[stable])
    )

    cn2 = np.full_like(z, np.nan)
    valid = (
        stable & np.isfinite(L) & (L > 0) & np.isfinite(P)
        & np.isfinite(T) & (T > 0)
    )
    cn2[valid] = (
        K_CIS * (80e-6 * P[valid] / (T[valid] * theta[valid])) ** 2
        * L[valid] ** (4.0 / 3.0) * dtheta_dz[valid] ** 2
    )

    return {
        **profile,
        "theta": theta,
        "dtheta_dz": dtheta_dz,
        "dU_dz": dU_dz,
        "dV_dz": dV_dz,
        "S": S,
        "E": E,
        "L": L,
        "Cn2": cn2,
    }


# ============================================================================
# ASSEMBLAGE PHYSIQUE
# ============================================================================

def combine_full_profile(hag, iso, h_coulim):
    """
    Profil physique Cn2 en respectant la priorite verticale HAG -> IP1.

    Regles :
      - TKE sur les niveaux HAG jusqu'a H_COULIM si H_COULIM <= 3000 m ;
      - cisaillement sur les niveaux HAG entre H_COULIM et 3000 m ;
      - si H_COULIM > 3000 m, TKE HAG jusqu'a 3000 m puis TKE IP4
        sur les niveaux isobares entre 3000 m et H_COULIM ;
      - au-dessus de max(H_COULIM, 3000 m), cisaillement IP1.

    Ainsi, H_COULIM definit la frontiere entre les modeles, mais ne
    provoque jamais un passage premature des variables HAG vers IP1.
    """
    if not np.isfinite(h_coulim):
        raise RuntimeError("H_COULIM indisponible.")

    keys = ("z", "T", "U", "V", "P", "TKE")
    parts = {key: [] for key in keys}

    # 1) Partie TKE HAG : toujours les niveaux HAG disponibles sous H_COULIM.
    mask_hag_tke = np.isfinite(hag["z"]) & (hag["z"] <= h_coulim)
    for key in keys:
        parts[key].append(np.asarray(hag[key])[mask_hag_tke])

    # 2) Si H_COULIM > 3000 m, prolongement TKE par IP4 au-dessus de 3000 m.
    mask_iso_tke = (
        np.isfinite(iso["z"])
        & (iso["z"] > 3000.0)
        & (iso["z"] <= h_coulim)
    )
    for key in ("z", "T", "U", "V", "P"):
        parts[key].append(np.asarray(iso[key])[mask_iso_tke])
    parts["TKE"].append(np.asarray(iso["TKE"])[mask_iso_tke])

    # 3) Cisaillement : PRIORITE AUX HAG jusqu'a 3000 m.
    #    C'est le point essentiel : si H_COULIM < 3000 m, le cisaillement
    #    utilise les niveaux HAG situes au-dessus de H_COULIM.
    mask_hag_shear = (
        np.isfinite(hag["z"])
        & (hag["z"] > h_coulim)
        & (hag["z"] <= 3000.0)
    )
    for key in ("z", "T", "U", "V", "P"):
        parts[key].append(np.asarray(hag[key])[mask_hag_shear])
    parts["TKE"].append(np.full(np.count_nonzero(mask_hag_shear), np.nan))

    # 4) Au-dessus de la limite HAG (3000 m), cisaillement sur IP1.
    shear_start = max(float(h_coulim), 3000.0)
    mask_iso_shear = np.isfinite(iso["z"]) & (iso["z"] > shear_start)
    for key in ("z", "T", "U", "V", "P"):
        parts[key].append(np.asarray(iso[key])[mask_iso_shear])
    parts["TKE"].append(np.full(np.count_nonzero(mask_iso_shear), np.nan))

    result = {key: np.concatenate(parts[key]) for key in keys}

    order = np.argsort(result["z"])
    for key in result:
        result[key] = result[key][order]

    return result


# ============================================================================
# PROFIL METEOROLOGIQUE POUR AFFICHAGE
# ============================================================================

def build_display_profile(hag, iso):
    """
    Profil complet des variables meteorologiques pour la figure.

    - conserve TOUS les niveaux HAG disponibles jusqu'a 3000 m ;
    - au-dessus de 3000 m, utilise les niveaux IP1 ;
    - ne tronque PAS le profil avec H_COULIM.

    H_COULIM sert uniquement a choisir le modele Cn2 dans
    `combine_full_profile` et dans le calcul physique de la BL/FA.
    """
    keys = ("z", "T", "U", "V", "P", "TKE")

    mask_hag = (
        np.isfinite(hag["z"])
        & (hag["z"] <= 3000.0)
    )
    mask_iso = np.isfinite(iso["z"]) & (iso["z"] > 3000.0)

    out = {}
    for key in keys:
        out[key] = np.concatenate([
            np.asarray(hag[key])[mask_hag],
            np.asarray(iso[key])[mask_iso],
        ])

    order = np.argsort(out["z"])
    for key in keys:
        out[key] = out[key][order]

    return out


def calculate_display_diagnostics(profile):
    """Calcule theta, gradients et L sur le profil meteorologique affiche."""
    z = np.asarray(profile["z"], dtype=float)
    T = np.asarray(profile["T"], dtype=float)
    P = np.asarray(profile["P"], dtype=float)
    U = np.asarray(profile["U"], dtype=float)
    V = np.asarray(profile["V"], dtype=float)
    TKE = np.asarray(profile["TKE"], dtype=float)

    theta = np.full_like(z, np.nan)
    valid_tp = np.isfinite(T) & (T > 0) & np.isfinite(P) & (P > 0)
    theta[valid_tp] = T[valid_tp] * (P0_HPA / P[valid_tp]) ** R_OVER_CP

    dtheta_dz = np.full_like(z, np.nan)
    dU_dz = np.full_like(z, np.nan)
    dV_dz = np.full_like(z, np.nan)

    valid = np.isfinite(z) & np.isfinite(theta)
    if np.count_nonzero(valid) >= 2:
        zv = z[valid]
        tv = theta[valid]
        uv = U[valid]
        vv = V[valid]
        dtheta_dz[valid] = np.gradient(tv, zv)
        dU_dz[valid] = np.gradient(uv, zv)
        dV_dz[valid] = np.gradient(vv, zv)

    L = np.full_like(z, np.nan)
    stable = (
        np.isfinite(TKE) & (TKE > 0)
        & np.isfinite(theta) & np.isfinite(dtheta_dz)
        & (dtheta_dz > 0)
    )
    L[stable] = np.sqrt(
        2.0 * TKE[stable] / ((G / theta[stable]) * dtheta_dz[stable])
    )

    return {
        "theta": theta,
        "dtheta_dz": dtheta_dz,
        "dU_dz": dU_dz,
        "dV_dz": dV_dz,
        "L": L,
    }


# ============================================================================
# SEEING
# ============================================================================

def calculate_seeing(z, cn2):
    z = np.asarray(z, dtype=float)
    cn2 = np.asarray(cn2, dtype=float)
    valid = np.isfinite(z) & np.isfinite(cn2) & (cn2 >= 0)

    if np.count_nonzero(valid) < 2:
        return np.nan, np.nan, np.nan

    zv = z[valid]
    cv = cn2[valid]
    order = np.argsort(zv)
    zv = zv[order]
    cv = cv[order]

    integral = np.trapezoid(cv, zv)
    if not np.isfinite(integral) or integral <= 0:
        return integral, np.nan, np.nan

    r0 = (0.423 * (2.0 * np.pi / LAMBDA) ** 2 * integral) ** (-3.0 / 5.0)
    seeing = 0.98 * LAMBDA / r0 * ARCSEC
    return integral, r0, seeing


# ============================================================================
# INTERPOLATION POUR AFFICHAGE
# ============================================================================

def interp_variable(z_target, z_source, values):
    """Interpolation rapide sur un profil deja trie en altitude."""
    z_source = np.asarray(z_source, dtype=float)
    values = np.asarray(values, dtype=float)

    valid = np.isfinite(z_source) & np.isfinite(values)
    if np.count_nonzero(valid) < 2:
        return np.full_like(z_target, np.nan, dtype=float)

    z = z_source[valid]
    v = values[valid]

    # Les profils construits par le script sont deja tries et sans doublons.
    # On ne refait donc ni argsort ni unique ici.
    out = np.full_like(z_target, np.nan, dtype=float)
    target_valid = np.isfinite(z_target)
    out[target_valid] = np.interp(
        z_target[target_valid],
        z,
        v,
        left=np.nan,
        right=np.nan,
    )
    return out


# ============================================================================
# DATE/HEURE DU CYCLE AROME
# ============================================================================

def get_grib_cycle_datetime(path):
    """Lit la date/heure de reference du cycle directement dans le GRIB."""
    with open(path, "rb") as f:
        while True:
            gid = codes_grib_new_from_file(f)
            if gid is None:
                break
            try:
                data_date = _get(gid, "dataDate", None)
                data_time = _get(gid, "dataTime", None)
                if data_date is not None and data_time is not None:
                    date_str = str(int(data_date))
                    time_int = int(round(float(data_time)))
                    hour = time_int // 100
                    minute = time_int % 100
                    return datetime.strptime(
                        f"{date_str} {hour:02d}{minute:02d}",
                        "%Y%m%d %H%M",
                    )
            finally:
                codes_release(gid)
    raise RuntimeError(
        f"Impossible de lire dataDate/dataTime dans le GRIB {path.name}."
    )


# ============================================================================
# FIGURE
# ============================================================================

def load_observed_seeing(csv_path):
    """Charge la courbe SBIG et reconstruit son axe temporel directement en TU.

    Les colonnes date/heure du CSV d'extraction ne sont pas utilisées pour
    l'axe temporel, car elles contiennent les anciennes dates d'affichage.
    Les valeurs de seeing sont conservées telles quelles.

    La séquence correspond à la nuit :
        12/09/2026 20:45 -> 13/09/2026 05:55 heure locale France
        13/09/2026 18:50 -> 14/09/2026 03:45 TU
    """
    if not csv_path.exists():
        return None, None

    obs = pd.read_csv(csv_path, sep=";")

    required = {"seeing_arcsec"}
    if not required.issubset(obs.columns):
        raise ValueError(
            f"Le CSV {csv_path.name} doit contenir la colonne "
            f"'seeing_arcsec'."
        )

    obs_seeing = pd.to_numeric(obs["seeing_arcsec"], errors="coerce")

    valid = obs_seeing.notna() & np.isfinite(obs_seeing)
    if not np.any(valid):
        return None, None




# ======================    FICHIERS   CSV   ===================================
    # Reconstruction temporelle explicite en TU :
    # 1er point = 13/09/2026 18:50 TU, puis un point toutes les 5 minutes.
    # n = int(np.count_nonzero(valid))
    # obs_dates = np.array(
    #     [
    #         SBIG_START_TU + timedelta(minutes=SBIG_SAMPLE_MINUTES * i)
    #         for i in range(n)
    #     ],
    #     dtype=object,
    # )
    # obs_values = obs_seeing[valid].to_numpy(dtype=float)
    # return obs_dates, obs_values
# ======================    FICHIERS   CSV   ===================================


def make_one_figure(results_by_hour, df, forecast_reference):
    hours = sorted(results_by_hour)
    valid_dates = [forecast_reference + timedelta(hours=int(h)) for h in hours]

    zmax = max(
        np.nanmax(results_by_hour[h]["z_combined"])
        for h in hours
        if np.any(np.isfinite(results_by_hour[h]["z_combined"]))
    )
    display_z = np.arange(10.0, np.ceil(zmax / 100.0) * 100.0 + 100.0, 100.0)

    keys = ["U", "V", "T", "P", "theta", "TKE", "L", "Cn2"]
    matrices = {k: [] for k in keys}

    for h in hours:
        r = results_by_hour[h]

        # Variables meteorologiques et diagnostics : profil d'affichage
        # complet HAG jusqu'a 3000 m, puis IP1.
        z_display = np.asarray(r["z"], dtype=float)

        for key in keys:
            if key == "Cn2":
                # Cn2 : valeurs du modele physique aux niveaux natifs.
                matrices[key].append(
                    interp_variable(
                        display_z,
                        z_display,
                        r["Cn2"],
                    )
                )
            else:
                matrices[key].append(
                    interp_variable(
                        display_z,
                        z_display,
                        r[key],
                    )
                )

    for key in matrices:
        matrices[key] = np.vstack(matrices[key])

    H = np.array([results_by_hour[h]["H_COULIM"] for h in hours])

    fig, axes = plt.subplots(3, 3, figsize=(18, 13), constrained_layout=False)
    fig.suptitle(
        "Profil vertical AROME - TKE dans la couche limite + cisaillement au-dessus",
        fontsize=18, fontweight="bold", y=0.98,
    )
    fig.text(
        0.5, 0.955,
        f"Lat = {LAT_SITE:.4f}° | Lon = {LON_SITE:.4f}° | λ = {LAMBDA*1e6:.1f} µm",
        ha="center", fontsize=11,
    )

    def heatmap(ax, data, title, label, log=False):
        data = np.asarray(data, dtype=float)
        if log:
            from matplotlib.colors import LogNorm
            data = np.where(data > 0, data, np.nan)
            finite = data[np.isfinite(data)]
            norm = None
            if finite.size:
                vmin = max(np.nanpercentile(finite, 40), np.finfo(float).tiny)
                vmax = np.nanpercentile(finite, 100)
                if vmax <= vmin:
                    vmax = vmin * 10.0
                norm = LogNorm(vmin=vmin, vmax=vmax)
        else:
            norm = None

        mesh = ax.pcolormesh(
            valid_dates, display_z, data.T, shading="auto", cmap="turbo", norm=norm
        )
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_xlabel("Heure")
        ax.set_ylabel("Altitude AGL [m]")
        ax.set_ylim(display_z.min(), affichage_altitude)# display_z.max())
        ax.grid(True, alpha=0.18, linestyle=":")
        cb = fig.colorbar(mesh, ax=ax, pad=0.02, fraction=0.046)
        cb.set_label(label)

    heatmap(axes[0, 0], matrices["U"], r"$U$ [m/s]", r"$U$ [m/s]")
    heatmap(axes[0, 1], matrices["V"], r"$V$ [m/s]", r"$V$ [m/s]")
    heatmap(axes[0, 2], matrices["T"], r"$T$ [K]", r"$T$ [K]")
    heatmap(axes[1, 0], matrices["P"], r"$P$ [hPa]", r"$P$ [hPa]")
    heatmap(axes[1, 1], matrices["theta"], r"$\theta$ [K]", r"$\theta$ [K]")
    heatmap(axes[1, 2], matrices["TKE"], r"TKE [m²/s²]", r"TKE [m²/s²]")
    heatmap(axes[2, 0], matrices["L"], r"$L$ [m]", r"$L$ [m]")
    heatmap(axes[2, 1], matrices["Cn2"], r"$C_n^2$ [m$^{-2/3}$]", r"$C_n^2$ [m$^{-2/3}$]", log=True)

    ax = axes[2, 1]
    valid_h = np.isfinite(H)
    if np.any(valid_h):
        ax.plot(np.asarray(valid_dates, dtype=object)[valid_h], H[valid_h], color="white", linewidth=2,
                label=r"$H_{COULIM}$", zorder=20)
        ax.legend(loc="best")

    ax9 = axes[2, 2]
    ax9.set_title("Seeing", fontsize=12, fontweight="bold")
    ax9.set_xlabel("Heure TU")
    ax9.set_ylabel("Seeing [arcsec]")
    # plt.ylim(0, 4)

    # Prediction AROME.
    ax9.plot(
        valid_dates,
        df["seeing_arcsec"].to_numpy(),
        marker="o",
        markersize=3,
        linewidth=1.5,
        color="tab:blue",
        label="AROME",
        zorder=5,
    )


# ======================    FICHIERS   CSV   ===================================
    # Observation SBIG : courbe rouge, axe temporel reconstruit directement en TU.
    # obs_dates, obs_values = load_observed_seeing(OBS_SEEING_CSV)
    # if obs_dates is not None:
    #     ax9.plot(
    #         obs_dates,
    #         obs_values,
    #         color="red",
    #         linewidth=1.8,
    #         label="SBIG (observation)",
    #         zorder=10,
    #     )
    # ax9.plot(df2["UTC+2"], df2["seeing_arcsec"], marker="o", markersize=3, linestyle="-", linewidth=2, color="gold", label="Seeing Nuit")
    # ax9.scatter(df3["UTC"], df3["seeing_arcsec"], marker="o",color="green", alpha = 0.1, label="Seeing jour")
    # ax9.plot(df3["UTC"],df3["seeing_median"], linewidth=1, color="green")

# ======================    FICHIERS   CSV   ===================================


    ax9.legend(loc="best")
    ax9.grid(True, alpha=0.18, linestyle=":")

    # Graduations toutes les 6 h, mais affichees en date/heure reelles.
    tick_dates = [d for d in valid_dates if (d - forecast_reference).total_seconds() % (6 * 3600) == 0]
    tick_labels = [d.strftime("%d/%m %Hh") for d in tick_dates]

    for ax in axes.flat:
        ax.set_xticks(tick_dates)
        ax.set_xticklabels(tick_labels, rotation=45, ha="right")
        ax.set_xlim(valid_dates[0], valid_dates[-1])
        # Lignes verticales quotidiennes conservees a 06 h et 18 h.
        for d in valid_dates:
            if d.hour in (6, 18):
                ax.axvline(d, color="black", linestyle="--", linewidth=1.0, alpha=0.6, zorder=15)

    fig.subplots_adjust(left=0.055, right=0.965, bottom=0.07, top=0.91,
                        wspace=0.28, hspace=0.30)
    plt.show()


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n" + "=" * 80)
    print("CALCUL SEEING AROME — PROFIL COMPLET HAG + ISOBARIQUE")
    print("=" * 80)
    print(f"Dossier : {DATA_DIR}")
    print(f"Site    : {LAT_SITE:.4f} N, {LON_SITE:.4f} E")
    print("BL      : TKE HP2, puis IP4 si H_COULIM > 3000 m")
    print("FA      : cisaillement IP1 au-dessus de H_COULIM")
    print()

    hp1_files = find_grib_files("HP1")
    hp2_files = find_grib_files("HP2")
    ip1_files = find_grib_files("IP1")
    ip4_files = find_grib_files("IP4")
    sp2_files = find_grib_files("SP2")

    # Date/heure reelle du cycle lue directement dans les metadonnees GRIB.
    # Elle sert uniquement a l'axe temporel des figures et n'affecte pas le calcul physique.
    forecast_reference = get_grib_cycle_datetime(hp1_files[0])

    print(f"Cycle AROME : {forecast_reference:%d/%m/%Y %H:%M}")
    
    # ======================    FICHIERS   CSV   ===================================
    # print(f"Seeing SBIG : {OBS_SEEING_CSV}" if OBS_SEEING_CSV.exists() else f"Seeing SBIG : fichier absent ({OBS_SEEING_CSV})")
   # ======================    FICHIERS   CSV   ===================================

    print(f"HP1 : {len(hp1_files)} fichiers")
    print(f"HP2 : {len(hp2_files)} fichiers")
    print(f"IP1 : {len(ip1_files)} fichiers")
    print(f"IP4 : {len(ip4_files)} fichiers")
    print(f"SP2 : {len(sp2_files)} fichiers")
    print()

    hp1_cache = {}
    hp2_cache = {}
    ip1_cache = {}
    ip4_cache = {}
    sp2_cache = {}

    # Une seule recherche des fichiers correspondant aux 52 echeances.
    hp1_hour_file = build_hour_file_map(hp1_files, FORECAST_HOURS)
    hp2_hour_file = build_hour_file_map(hp2_files, FORECAST_HOURS)
    ip1_hour_file = build_hour_file_map(ip1_files, FORECAST_HOURS)
    ip4_hour_file = build_hour_file_map(ip4_files, FORECAST_HOURS)
    sp2_hour_file = build_hour_file_map(sp2_files, FORECAST_HOURS)

    for path in hp1_files:
        print("Lecture HP1 :")
        data, lat, lon = read_grib_package(path, {"t", "u", "v", "pres"})
        hp1_cache[path] = {"data": data, "lat": lat, "lon": lon}

    for path in hp2_files:
        print("Lecture HP2 :")
        data, lat, lon = read_grib_package(path, {"tke"})
        hp2_cache[path] = {"data": data, "lat": lat, "lon": lon}

    for path in ip1_files:
        print("Lecture IP1 :")
        data, lat, lon = read_grib_package(
            path, {"t", "u", "v", "z"}, allowed_types={"isobaricInhPa"}
        )
        ip1_cache[path] = {"data": data, "lat": lat, "lon": lon}

    for path in ip4_files:
        print("Lecture IP4 :")
        data, lat, lon = read_grib_package(
            path, {"tke"}, allowed_types={"isobaricInhPa"}
        )
        ip4_cache[path] = {"data": data, "lat": lat, "lon": lon}

    for path in sp2_files:
        print("Lecture SP2 :")
        data, lat, lon = read_grib_package(
            path, {"blh", "h_coulim"}, allowed_types={"surface"}
        )
        sp2_cache[path] = {"data": data, "lat": lat, "lon": lon}

    # h est un champ de relief statique. On le lit directement sur le message
    # SP2:h, avec sa propre grille, exactement comme dans le diagnostic GRIB.
    surface_altitude, h_grid_lat, h_grid_lon = read_surface_h(sp2_files[0])

    print()
    print(f"Altitude relief SP2:h = {surface_altitude:.2f} m")
    print(f"Maille SP2:h           = {h_grid_lat:.6f}, {h_grid_lon:.6f}")
    print("\n" + "=" * 80)
    print("CONSTRUCTION DES PROFILS TEMPORELS")
    print("=" * 80)

    rows = []
    results_by_hour = {}

    for hour in range(FORECAST_HOURS + 1):
        hp1_file = hp1_hour_file[hour]
        hp2_file = hp2_hour_file[hour]
        ip1_file = ip1_hour_file[hour]
        ip4_file = ip4_hour_file[hour]
        sp2_file = sp2_hour_file[hour]

        hp1_data = hp1_cache[hp1_file]["data"]
        hp2_data = hp2_cache[hp2_file]["data"]
        ip1_data = ip1_cache[ip1_file]["data"]
        ip4_data = ip4_cache[ip4_file]["data"]
        sp2_data = sp2_cache[sp2_file]["data"]

        h_coulim = get_h_coulim(sp2_data, hour)
        if not np.isfinite(h_coulim):
            raise RuntimeError(f"H_COULIM/blh indisponible à H+{hour}.")

        hag = build_hag_profile(
            hp1_data, hp2_data, hour,
            hp1_cache[hp1_file]["lat"], hp1_cache[hp1_file]["lon"]
        )
        iso = make_isobaric_profile(
            ip1_data, hour, surface_altitude,
            ip1_cache[ip1_file]["lat"], ip1_cache[ip1_file]["lon"]
        )
        iso["TKE"] = add_ip4_tke(iso, ip4_data, hour)

        # Profil physique TKE : HP2 + IP4 uniquement jusqu'à H_COULIM.
        # Pour calculer le Cn2 TKE sur une grille continue, on concatene
        # explicitement HP2 et IP4 dans la BL.
        mask_hag_bl = hag["z"] <= h_coulim
        mask_iso_bl = (iso["z"] > 3000.0) & (iso["z"] <= h_coulim)

        tke_bl = {
            "z": np.concatenate([hag["z"][mask_hag_bl], iso["z"][mask_iso_bl]]),
            "T": np.concatenate([hag["T"][mask_hag_bl], iso["T"][mask_iso_bl]]),
            "U": np.concatenate([hag["U"][mask_hag_bl], iso["U"][mask_iso_bl]]),
            "V": np.concatenate([hag["V"][mask_hag_bl], iso["V"][mask_iso_bl]]),
            "P": np.concatenate([hag["P"][mask_hag_bl], iso["P"][mask_iso_bl]]),
            "TKE": np.concatenate([hag["TKE"][mask_hag_bl], iso["TKE"][mask_iso_bl]]),
        }
        result_tke = calculate_cn2_tke(tke_bl)

        # Atmosphere libre : PRIORITE AUX HAG jusqu'a 3000 m.
        # Si H_COULIM < 3000 m, le cisaillement est donc calcule sur les
        # niveaux HAG au-dessus de H_COULIM, puis sur IP1 au-dessus de 3000 m.
        mask_hag_shear = (
            np.isfinite(hag["z"])
            & (hag["z"] > h_coulim)
            & (hag["z"] <= 3000.0)
        )
        mask_iso_shear = (
            np.isfinite(iso["z"])
            & (iso["z"] > max(float(h_coulim), 3000.0))
        )

        shear_profile = {
            k: np.concatenate([
                np.asarray(hag[k])[mask_hag_shear],
                np.asarray(iso[k])[mask_iso_shear],
            ])
            for k in ("z", "T", "U", "V", "P")
        }
        result_shear = calculate_cn2_shear(shear_profile)

        # Profil meteorologique independant de H_COULIM pour l'affichage :
        # tous les niveaux HAG jusqu'a 3000 m sont conserves.
        display_profile = build_display_profile(hag, iso)
        display_diag = calculate_display_diagnostics(display_profile)

        # Cn2 natif combine pour l'integration.
        # L'ordre TKE puis cisaillement est deja croissant en altitude.
        z_cn2 = np.concatenate([result_tke["z"], result_shear["z"]])
        cn2 = np.concatenate([result_tke["Cn2"], result_shear["Cn2"]])

        integral, r0, seeing = calculate_seeing(z_cn2, cn2)

        # Projection rapide de Cn2 sur le profil d'affichage.
        # Les altitudes natives sont communes entre les profils : un
        # dictionnaire evite les recherches np.where/isclose imbriquees.
        cn2_by_z = {}
        for z0, c0 in zip(result_tke["z"], result_tke["Cn2"]):
            if np.isfinite(c0):
                cn2_by_z[round(float(z0), 6)] = float(c0)
        for z0, c0 in zip(result_shear["z"], result_shear["Cn2"]):
            if np.isfinite(c0):
                cn2_by_z[round(float(z0), 6)] = float(c0)

        cn2_display = np.array(
            [cn2_by_z.get(round(float(z0), 6), np.nan)
             for z0 in display_profile["z"]],
            dtype=float,
        )

        display_profile.update(display_diag)
        display_profile["Cn2"] = cn2_display

        results_by_hour[hour] = {
            **display_profile,
            "H_COULIM": h_coulim,
            "z_combined": z_cn2,
            "Cn2_combined": cn2,
            "r0": r0,
            "seeing": seeing,
        }

        rows.append({
            "forecast_hour": hour,
            "grid_lat": hp1_cache[hp1_file]["lat"],
            "grid_lon": hp1_cache[hp1_file]["lon"],
            "surface_altitude_m": surface_altitude,
            "H_COULIM_m": h_coulim,
            "integral_Cn2": integral,
            "r0_m": r0,
            "seeing_arcsec": seeing,
            "tke_min": np.nanmin(display_profile["TKE"]) if np.any(np.isfinite(display_profile["TKE"])) else np.nan,
            "tke_max": np.nanmax(display_profile["TKE"]) if np.any(np.isfinite(display_profile["TKE"])) else np.nan,
        })

        print(
            f"H+{hour:02d} | H_COULIM={h_coulim:7.1f} m | "
            f"IP1 top={np.nanmax(iso['z']):7.0f} m AGL | "
            f"TKE max={rows[-1]['tke_max']:.3e} | "
            f"seeing={seeing:.5f} arcsec"
        )

    df = pd.DataFrame(rows)
    output = DATA_DIR / "seeing_AROME_complet_HAG_isobares.csv"
    df.to_csv(output, index=False)

    print("\n" + "=" * 80)
    print("DIAGNOSTIC FINAL")
    print("=" * 80)
    print(f"Altitude relief SP2:h : {surface_altitude:.2f} m")
    print(f"H_COULIM min/max      : {df['H_COULIM_m'].min():.1f} / {df['H_COULIM_m'].max():.1f} m")
    print(f"Top IP1 max            : {max(np.nanmax(results_by_hour[h]['z']) for h in results_by_hour):.0f} m AGL")
    print(f"Seeing min/max         : {df['seeing_arcsec'].min():.5f} / {df['seeing_arcsec'].max():.5f} arcsec")
    print(f"CSV                   : {output}")

    make_one_figure(results_by_hour, df, forecast_reference)


if __name__ == "__main__":
    main()
