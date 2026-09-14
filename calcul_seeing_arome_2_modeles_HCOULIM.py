#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Calcul du seeing optique AROME à Verclause.

IMPORTANT :
- Les GRIB2 ont déjà été téléchargés avec MeteoFetch.
- Ce script ne fait AUCUN téléchargement.
- Chaque échéance H+00 ... H+48 est sélectionnée explicitement
  dans les messages GRIB via la clé "step".
- On ne prend donc plus systématiquement le premier message du fichier.
- Les résultats et diagnostics sont affichés dans Spyder.
- Une seule grande figure matplotlib est créée, avec plusieurs panneaux.

Variables :
    HP1 : t, u, v, pres  (niveaux hauteur AGL)
    HP2 : tke              (niveaux hauteur AGL)
    IP1 : t, u, v, z       (niveaux isobares)
    SP2 : H_COULIM / blh   (hauteur de couche limite)

Physique :
   MODELE de MASCIADRI avec TKE, energie cinétique turbulente
    E = TKE
    k = 6
    lambda = 500 nm
"""

import argparse
from pathlib import Path
import re

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from eccodes import (
    codes_grib_new_from_file,
    codes_get,
    codes_get_array,
    codes_release,
)


# ============================================================================
# CONFIGURATION
# ============================================================================

# Valeur par defaut ; ecrasee par l'argument --data-dir passe en ligne de
# commande (voir parse_args / main).
DATA_DIR = Path(".")

# LAT_SITE = 43.9500;  LON_SITE  =  4.81667   #   Avignon 
# LAT_SITE = 48.8566;  LON_SITE  =  2.3522   #   Paris 
# LAT_SITE = 42.93642; LON_SITE  =  0.14122  #   Pic Du Midi Observatoire 
# LAT_SITE = 45.8326 ;  LON_SITE  =  6.8652    #   Mont Blanc
# -------------   Seeing monitor disponibles :   ------------------------------
# LAT_SITE = 44.5828;  LON_SITE  =  5.9868   #   Asso Copernicus
LAT_SITE = 44.3814;  LON_SITE  =  5.4286   #   VERCLAUSE
LAT_SITE = 44.3814;  LON_SITE  =  5.4286   #   VERCLAUSE


FORECAST_HOURS = 51

# Niveaux communs à T/P/TKE et à U/V.
HEIGHTS = np.array([
    20, 35, 50, 75, 100, 150, 200, 250,
    375, 500, 625, 750, 875, 1000, 1125, 1250,
    1375, 1500, 1750, 2000, 2250, 2500, 2750, 3000
], dtype=float)

# Constantes modèles, et coefficients K pour Masciadri et K Osborn & Sarazin  
K_CN2          = 1    #coef modele TKE
K_Cis          = 6    #coef modèle cisaillement

G              = 9.81
R_OVER_CP      = 0.286
P0_HPA         = 1000.0

LAMBDA         = 500e-9
ARCSEC         = 206265.0


# ============================================================================
# OUTILS GRIB
# ============================================================================

def _get(gid, key, default=None):
    try:
        return codes_get(gid, key)
    except Exception:
        return default


def get_nearest_index(gid):
    """
    Détermine une seule fois le point de grille le plus proche de Verclause.
    Retourne l'indice dans le tableau GRIB et les coordonnées réelles.
    """

    lats = np.asarray(codes_get_array(gid, "latitudes"), dtype=float)
    lons = np.asarray(codes_get_array(gid, "longitudes"), dtype=float)

    lons_norm = ((lons + 180.0) % 360.0) - 180.0
    target_lon = ((LON_SITE + 180.0) % 360.0) - 180.0

    dist2 = (
        (lats - LAT_SITE) ** 2
        + (lons_norm - target_lon) ** 2
    )

    idx = int(np.nanargmin(dist2))

    return idx, float(lats[idx]), float(lons_norm[idx])


def extract_message_value(gid, nearest_index):
    """
    Extrait uniquement la valeur du point de grille voulu.
    """

    values = np.asarray(
        codes_get_array(gid, "values"),
        dtype=float,
    )

    if nearest_index >= values.size:
        raise IndexError(
            f"Indice grille {nearest_index} hors tableau de taille "
            f"{values.size}."
        )

    return float(values[nearest_index])


def get_message_step(gid):
    """
    Récupère l'échéance du message.

    On privilégie "step".
    Fallback sur "endStep" puis "forecastTime".
    """

    for key in ("step", "endStep", "forecastTime"):
        value = _get(gid, key, None)

        if value is not None:
            try:
                return int(round(float(value)))
            except Exception:
                pass

    return None


# ============================================================================
# LECTURE D'UN FICHIER GRIB : TOUS LES PAS TEMPORELS EN UNE SEULE LECTURE
# ============================================================================

def read_grib_package(path, variables, allowed_types=None):
    """
    Lit un fichier GRIB2 une seule fois.

    Retour :
        data[step][variable][level] = valeur au point de grille voulu

    Les niveaux sont conservés dans leurs unités natives :
      - heightAboveGround : altitude AGL en m
      - isobaricInhPa     : pression en hPa
      - surface / autres  : niveau GRIB associé

    Pour H_COULIM/blh, le champ est généralement sans dimension verticale
    utile : on conserve alors level=0.0.
    """

    data = {}
    nearest_index = None
    grid_lat = None
    grid_lon = None
    found_steps = set()

    if allowed_types is None:
        allowed_types = {
            "heightAboveGround",
            "isobaricInhPa",
            "surface",
        }

    with open(path, "rb") as f:
        while True:
            gid = codes_grib_new_from_file(f)
            if gid is None:
                break

            try:
                short_name = _get(gid, "shortName")
                type_of_level = _get(gid, "typeOfLevel")
                level = _get(gid, "level")
                step = get_message_step(gid)

                if short_name not in variables:
                    continue

                if type_of_level not in allowed_types:
                    continue

                # H_COULIM/blh peut être un champ de surface avec level absent.
                if level is None:
                    level = 0.0

                if step is None:
                    continue

                found_steps.add(step)

                if nearest_index is None:
                    nearest_index, grid_lat, grid_lon = get_nearest_index(gid)

                value = extract_message_value(gid, nearest_index)

                step_dict = data.setdefault(step, {})
                var_dict = step_dict.setdefault(short_name, {})
                var_dict[float(level)] = value

            finally:
                codes_release(gid)

    if not data:
        raise RuntimeError(
            f"Aucune donnée utile trouvée dans {path.name}."
        )

    print(
        f"  {path.name} : pas temporels trouvés = "
        f"{sorted(found_steps)}"
    )

    return data, grid_lat, grid_lon


# ============================================================================
# FICHIERS
# ============================================================================

def find_grib_files(package):
    files = sorted(
        DATA_DIR.glob(
            f"arome__0025__{package}__*.grib2"
        )
    )

    if not files:
        raise FileNotFoundError(
            f"Aucun fichier {package} dans {DATA_DIR}"
        )

    return files


def parse_forecast_range(path):
    match = re.search(
        r"__(\d{2})H(\d{2})H__",
        path.name,
    )

    if not match:
        raise ValueError(
            f"Impossible de lire la tranche temporelle de {path.name}"
        )

    return int(match.group(1)), int(match.group(2))


def select_file_for_hour(files, hour):
    for path in files:
        start, end = parse_forecast_range(path)

        if start <= hour <= end:
            return path

    raise FileNotFoundError(
        f"Aucun fichier pour H+{hour}"
    )


# ============================================================================
# LECTURE H_COULIM
# ============================================================================

def get_h_coulim(sp2_data, hour):
    """
    Retourne H_COULIM (hauteur de couche limite) en m AGL.

    On accepte les deux noms rencontrés selon le mapping GRIB :
        - blh
        - h_coulim

    Le champ est traité comme un champ de surface : une seule valeur
    par échéance.
    """
    if hour not in sp2_data:
        return np.nan

    source = sp2_data[hour]

    for name in ("blh", "h_coulim"):
        if name in source and source[name]:
            values = list(source[name].values())
            if values:
                return float(values[0])

    return np.nan


# ============================================================================
# PROFIL ISOBARIQUE POUR LE MODELE CISAILLEMENT
# ============================================================================

def make_isobaric_profile(ip1_data, hour, grid_lat, grid_lon):
    """
    Construit le profil T/U/V/P/Z sur les niveaux isobares IP1.

    Z est le géopotentiel [m²/s²] et est converti en altitude
    géopotentielle z = Z/g [m].
    """
    if hour not in ip1_data:
        raise KeyError(f"H+{hour} absent de IP1.")

    source = ip1_data[hour]

    # On utilise les niveaux disponibles de T/U/V/Z.
    levels = set()
    for variable in ("t", "u", "v", "z"):
        levels.update(source.get(variable, {}).keys())

    pressures = np.array(sorted(levels, reverse=True), dtype=float)

    T = np.full(len(pressures), np.nan)
    U = np.full(len(pressures), np.nan)
    V = np.full(len(pressures), np.nan)
    Z = np.full(len(pressures), np.nan)

    for i, p in enumerate(pressures):
        if "t" in source and p in source["t"]:
            T[i] = source["t"][p]
        if "u" in source and p in source["u"]:
            U[i] = source["u"][p]
        if "v" in source and p in source["v"]:
            V[i] = source["v"][p]
        if "z" in source and p in source["z"]:
            Z[i] = source["z"][p]

    # IP1 Z = geopotential [m²/s²] -> altitude géopotentielle [m].
    z = Z / G

    # On trie impérativement par altitude croissante avant les gradients.
    order = np.argsort(z)
    z = z[order]
    pressures = pressures[order]
    T = T[order]
    U = U[order]
    V = V[order]
    Z = Z[order]

    return {
        "z": z,
        "T": T,
        "U": U,
        "V": V,
        "P": pressures,
        "Z": Z,
        "grid_lat": grid_lat,
        "grid_lon": grid_lon,
    }


# ============================================================================
# CONSTRUCTION DU PROFIL À UNE ÉCHÉANCE
# ============================================================================

def build_profile(hp1_data, hp2_data, hour, grid_lat, grid_lon):
    """
    Construit T/U/V/P/TKE pour UNE échéance explicite.

    Le point essentiel est ici :
        hp1_data[hour]
        hp2_data[hour]

    et non pas le premier message du GRIB.
    """

    if hour not in hp1_data:
        raise KeyError(
            f"H+{hour} absent de HP1."
        )

    if hour not in hp2_data:
        # HP2/TKE commence à H+1 dans les fichiers AROME téléchargés.
        # On ne fabrique pas de TKE à H+0 : le seeing H+0 sera donc NaN.
        hp2 = None
    else:
        hp2 = hp2_data[hour]

    hp1 = hp1_data[hour]

    def make_array(source, variable):
        arr = np.full(
            len(HEIGHTS),
            np.nan,
            dtype=float,
        )

        if variable not in source:
            return arr

        values = source[variable]

        for i, h in enumerate(HEIGHTS):
            if h in values:
                arr[i] = values[h]

        return arr

    T = make_array(hp1, "t")
    U = make_array(hp1, "u")
    V = make_array(hp1, "v")
    P = make_array(hp1, "pres")
    if hp2 is None:
        TKE = np.full(
            len(HEIGHTS),
            np.nan,
            dtype=float,
        )
    else:
        TKE = make_array(hp2, "tke")

    # Pression : GRIB = Pa -> hPa
    if np.nanmedian(P) > 2000:
        P = P / 100.0

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
# PHYSIQUE
# ============================================================================

def calculate_cn2_tke(profile):

    z = profile["z"]
    T = profile["T"]
    U = profile["U"]
    V = profile["V"]
    P = profile["P"]
    E = profile["TKE"]

    # Température potentielle
    theta = T * (P0_HPA / P) ** R_OVER_CP

    # Gradients verticaux
    dtheta_dz = np.gradient(theta, z)
    dU_dz     = np.gradient(U, z)
    dV_dz     = np.gradient(V, z)

    # Longueur de mélange :
    # L = sqrt(2 E / ((g/theta) dtheta/dz))
    L = np.full_like(z, np.nan)

    stable = (
        np.isfinite(E)
        & np.isfinite(theta)
        & np.isfinite(dtheta_dz)
        & (E > 0)
        & (dtheta_dz > 0)
    )

    L[stable] = np.sqrt(
        2 * E[stable]  / (  ( G / theta[stable] )  * dtheta_dz[stable]   ) )

    # Cn²
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
        K_CN2 * ( 80e-6 * P[valid]
            / (T[valid] * theta[valid])) ** 2 * L[valid] ** (4/3) * dtheta_dz[valid] ** 2
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


# ============================================================================
# MODELE CISAILLEMENT — ATMOSPHERE LIBRE
# ============================================================================

def calculate_cn2_shear(profile):
    """
    Modèle Osborn/Sarazin avec E = S², destiné à l'atmosphère libre.

    Le profil est sur les niveaux isobares IP1, convertis en altitude
    géopotentielle via Z/g avant calcul des gradients.
    """
    z = profile["z"]
    T = profile["T"]
    U = profile["U"]
    V = profile["V"]
    P = profile["P"]

    theta = T * (P0_HPA / P) ** R_OVER_CP

    dtheta_dz = np.gradient(theta, z)
    dU_dz = np.gradient(U, z)
    dV_dz = np.gradient(V, z)

    S = np.sqrt(dU_dz**2 + dV_dz**2)

    # Osborn & Sarazin : E = S² pour le modèle basé sur le cisaillement.
    E = S**2

    L = np.full_like(z, np.nan)

    stable = (
        np.isfinite(E)
        & np.isfinite(theta)
        & np.isfinite(dtheta_dz)
        & (E > 0)
        & (dtheta_dz > 0)
    )

    L[stable] = np.sqrt(
        2 * E[stable]
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
        K_Cis
        * (
            80e-6
            * P[valid]
            / (T[valid] * theta[valid])
        ) ** 2
        * L[valid] ** (4 / 3)
        * dtheta_dz[valid] ** 2
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
# COMBINAISON DES DEUX PROFILS
# ============================================================================

def combine_profiles(tke_result, shear_result, h_coulim):
    """
    Sépare les deux modèles par H_COULIM puis concatène leurs grilles
    natives après conversion de la grille isobare en altitude.

    Couche limite :
        z <= H_COULIM  -> modèle TKE

    Atmosphère libre :
        z > H_COULIM   -> modèle cisaillement

    Aucune interpolation verticale n'est imposée.
    """
    z_tke      =  np.asarray(tke_result["z"], dtype=float)
    cn2_tke    =  np.asarray(tke_result["Cn2"], dtype=float)

    z_shear    =  np.asarray(shear_result["z"], dtype=float)
    cn2_shear  =  np.asarray(shear_result["Cn2"], dtype=float)

    if not np.isfinite(h_coulim):
        # Impossible de faire une séparation physique sans H_COULIM.
        return np.array([]), np.array([])

    mask_tke = np.isfinite(z_tke) & (z_tke <= h_coulim)
    mask_shear = np.isfinite(z_shear) & (z_shear > h_coulim)

    z_combined = np.concatenate([
        z_tke[mask_tke],
        z_shear[mask_shear],
    ])

    cn2_combined = np.concatenate([
        cn2_tke[mask_tke],
        cn2_shear[mask_shear],
    ])

    if z_combined.size == 0:
        return z_combined, cn2_combined

    order = np.argsort(z_combined)

    return z_combined[order], cn2_combined[order]


# ============================================================================
# MATRICE D'AFFICHAGE Cn² SUR UNE GRILLE HAUTEUR COMMUNE
# ============================================================================

def interpolate_cn2_for_display(z_target, z_source, cn2_source):
    """
    Interpolation uniquement pour la représentation graphique.

    Le calcul physique et l'intégration du seeing restent effectués
    sur les grilles natives combinées.
    """
    valid = (
        np.isfinite(z_source)
        & np.isfinite(cn2_source)
        & (cn2_source >= 0)
    )

    if np.count_nonzero(valid) < 2:
        return np.full_like(z_target, np.nan, dtype=float)

    z_valid = z_source[valid]
    cn2_valid = cn2_source[valid]

    order = np.argsort(z_valid)
    z_valid = z_valid[order]
    cn2_valid = cn2_valid[order]

    # Supprime les éventuels doublons en altitude.
    z_unique, unique_idx = np.unique(z_valid, return_index=True)
    cn2_unique = cn2_valid[unique_idx]

    out = np.full_like(z_target, np.nan, dtype=float)

    inside = (
        np.isfinite(z_target)
        & (z_target >= z_unique.min())
        & (z_target <= z_unique.max())
    )

    if np.any(inside):
        out[inside] = np.interp(
            z_target[inside],
            z_unique,
            cn2_unique,
        )

    return out


# ============================================================================
# SEEING
# ============================================================================

def calculate_seeing(z, cn2):

    valid = (
        np.isfinite(z)
        & np.isfinite(cn2)
        & (cn2 >= 0)
    )

    if np.count_nonzero(valid) < 2:
        return np.nan, np.nan, np.nan

    integral_cn2 = np.trapezoid(
        cn2[valid],
        z[valid],
    )

    if (
        not np.isfinite(integral_cn2)
        or integral_cn2 <= 0
    ):
        return integral_cn2, np.nan, np.nan

    r0 = (
        0.423
        * (2.0 * np.pi / LAMBDA) ** 2
        * integral_cn2
    ) ** (-3.0 / 5.0)

    seeing_rad = 0.98 * LAMBDA / r0
    seeing_arcsec = seeing_rad * ARCSEC

    return integral_cn2, r0, seeing_arcsec


# ============================================================================
# UNE SEULE GRANDE FIGURE SPYDER
# ============================================================================

def make_one_figure(results_by_hour, df):

    hours = sorted(results_by_hour)

    # ------------------------------------------------------------------
    # Construction des matrices temps x altitude
    # ------------------------------------------------------------------
    z = np.asarray(results_by_hour[hours[0]]["z"], dtype=float)

    def matrix_for(key):
        return np.vstack([
            np.asarray(results_by_hour[h][key], dtype=float)
            for h in hours
        ])

    U = matrix_for("U")
    V = matrix_for("V")
    T = matrix_for("T")
    P = matrix_for("P")
    theta = matrix_for("theta")
    TKE = matrix_for("TKE")
    L = matrix_for("L")
    Cn2 = matrix_for("Cn2")
    H_COULIM = np.array(
        [results_by_hour[h]["H_COULIM"] for h in hours],
        dtype=float,
    )

    # Pour pcolormesh : une colonne par échéance et une ligne par altitude.
    X, Y = np.meshgrid(hours, z, indexing="ij")

    # ------------------------------------------------------------------
    # UNE SEULE GRANDE FIGURE, comme sur ton exemple :
    #
    # U | V | T
    # P | theta | TKE
    # L | Cn² | r0 + seeing
    # ------------------------------------------------------------------
    fig, axes = plt.subplots(
        3,
        3,
        figsize=(18, 13),
        constrained_layout=False,
    )

    fig.suptitle(
        "Profil vertical AROME - TKE dans la couche limite + cisaillement au-dessus",
        fontsize=18,
        fontweight="bold",
        y=0.98,
    )

    fig.text(
        0.5,
        0.955,
        (
            f"Lat = {LAT_SITE:.4f}°  |  "
            f"Lon = {LON_SITE:.4f}°  |  "
            f"λ = {LAMBDA * 1e6:.1f} µm"
        ),
        ha="center",
        fontsize=11,
    )

    def heatmap(ax, data, title, cbar_label, cmap="turbo",
                log_scale=False, vmin=None, vmax=None):
        data_plot = np.array(data, dtype=float)

        if log_scale:
            # Les valeurs <= 0 ne sont pas représentables en échelle log.
            data_plot = np.where(data_plot > 0, data_plot, np.nan)

            from matplotlib.colors import LogNorm

            finite = data_plot[np.isfinite(data_plot)]

            if finite.size == 0:
                norm = None
            else:
                if vmin is None:
                    vmin_eff = np.nanpercentile(finite, 2)
                else:
                    vmin_eff = vmin

                if vmax is None:
                    vmax_eff = np.nanpercentile(finite, 98)
                else:
                    vmax_eff = vmax

                # Sécurité numérique pour LogNorm.
                vmin_eff = max(vmin_eff, np.finfo(float).tiny)

                if vmax_eff <= vmin_eff:
                    vmax_eff = vmin_eff * 10.0

                norm = LogNorm(vmin=vmin_eff, vmax=vmax_eff)
        else:
            norm = None

        mesh = ax.pcolormesh(
            hours,
            z,
            data_plot.T,
            shading="auto",
            cmap=cmap,
            norm=norm,
            vmin=None if norm is not None else vmin,
            vmax=None if norm is not None else vmax,
        )

        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_xlabel("Heure")
        ax.set_ylabel("Altitude [m]")
        ax.set_ylim(z.min(), z.max())
        ax.grid(True, alpha=0.18, linestyle=":")

        cbar = fig.colorbar(
            mesh,
            ax=ax,
            pad=0.02,
            fraction=0.046,
        )
        cbar.set_label(cbar_label)

        return mesh

    # ------------------------------------------------------------------
    # 1 — U
    # ------------------------------------------------------------------
    heatmap(
        axes[0, 0],
        U,
        r"$U$ [m/s]",
        r"$U$ [m/s]",
    )

    # ------------------------------------------------------------------
    # 2 — V
    # ------------------------------------------------------------------
    heatmap(
        axes[0, 1],
        V,
        r"$V$ [m/s]",
        r"$V$ [m/s]",
    )

    # ------------------------------------------------------------------
    # 3 — T
    # ------------------------------------------------------------------
    heatmap(
        axes[0, 2],
        T,
        r"$T$ [K]",
        r"$T$ [K]",
    )

    # ------------------------------------------------------------------
    # 4 — P
    # ------------------------------------------------------------------
    heatmap(
        axes[1, 0],
        P,
        r"$P$ [hPa]",
        r"$P$ [hPa]",
    )

    # ------------------------------------------------------------------
    # 5 — theta
    # ------------------------------------------------------------------
    heatmap(
        axes[1, 1],
        theta,
        r"$\theta$ [K]",
        r"$\theta$ [K]",
    )

    # ------------------------------------------------------------------
    # 6 — TKE
    # ------------------------------------------------------------------
    heatmap(
        axes[1, 2],
        TKE,
        r"TKE [m²/s²]",
        r"TKE [m²/s²]",
    )

    # ------------------------------------------------------------------
    # 7 — L
    # ------------------------------------------------------------------
    heatmap(
        axes[2, 0],
        L,
        r"$L$ [m]",
        r"$L$ [m]",
        
    )


    # ------------------------------------------------------------------
    # 8 — Cn² + seeing
    # ------------------------------------------------------------------
    # Heatmap de Cn² avec le seeing superposé sur le même panneau.
    # Le seeing utilise l'axe Y droit.
    ax_cn2 = axes[2, 1]

    heatmap(
        ax_cn2,
        Cn2,
        r"$C_n^2$ [m$^{-2/3}$]",
        r"$C_n^2$ [m$^{-2/3}$]",
    )

    # ax_seeing_cn2 = ax_cn2.twinx()

    # line_seeing_cn2 = ax_seeing_cn2.plot(
    #     df["forecast_hour"],
    #     df["seeing_arcsec"],
    #     marker="o",
    #     markersize=3,
    #     linewidth=1.5,
    #     color="tab:red",
    #     label="Seeing",
    # )

    # ax_seeing_cn2.set_ylabel("Seeing [arcsec]")

    # ax_seeing_cn2.legend(
    #     line_seeing_cn2,
    #     ["Seeing"],
    #     loc="best",
    # )

    # Hauteur de couche limite superposée en blanc.
    valid_bl = np.isfinite(H_COULIM)
    if np.any(valid_bl):
        ax_cn2.plot(
            np.asarray(hours)[valid_bl],
            H_COULIM[valid_bl],
            color="white",
            linewidth=2.0,
            linestyle="-",
            label=r"$H_{COULIM}$",
            zorder=20,
        )
        ax_cn2.legend(loc="best")


    # ------------------------------------------------------------------
    # 9 — Suppression du panneau r0
    # ------------------------------------------------------------------
    # On ne représente plus r0.
    # ax_r0 = axes[2, 2]
    # ax_r0.axis("off")
    # # ------------------------------------------------------------------
    # # 8 — Cn²
    # # ------------------------------------------------------------------
    # heatmap(
    #     axes[2, 1],
    #     Cn2,
    #     r"$C_n^2$ [m$^{-2/3}$]",
    #     r"$C_n^2$ [m$^{-2/3}$]",
    # )
    # #log_scale=True,    # si on veut echelle log


    # ------------------------------------------------------------------
    # 9 — r0 + seeing
    # ------------------------------------------------------------------
    ax_r0 = axes[2, 2]

    # line_r0 = ax_r0.plot(
    #     df["forecast_hour"],
    #     df["r0_m"],
    #     marker="o",
    #     markersize=3,
    #     linewidth=1.5,
    #     color="tab:red",
    #     label=r"$r_0$",
    # )

    ax_r0.set_title(
        r"seeing",
        fontsize=12,
        fontweight="bold",
    )
    ax_r0.set_xlabel("Heure")
    # ax_r0.set_ylabel(r"$r_0$ [m]")
    # ax_r0.grid(True, alpha=0.25, linestyle=":")

    ax_seeing = ax_r0.twinx()

    line_seeing = ax_seeing.plot(
        df["forecast_hour"],
        df["seeing_arcsec"],
        marker="o",
        markersize=3,
        linewidth=1.5,
        color="tab:red",
        label="Seeing",
    )
    
    # ligne_r0, = ax_R.plot(
    #     resultats["time"],
    #     resultats["r0"],
    #     marker="o",
    #     markersize=4,
    #     linewidth=2,
    #     color="tab:red",
    #     label=r"$r_0$"
    # )

    ax_seeing.set_ylabel("Seeing [arcsec]")

    lines =  line_seeing #+ line_r0
    labels = [line.get_label() for line in lines]
    ax_r0.legend(lines, labels, loc="best")

    # ------------------------------------------------------------------
    # Mise en page
    # ------------------------------------------------------------------
    xticks = [h for h in hours if h % 6 == 0]

    for ax in axes.flat:
        ax.set_xticks(xticks)
        ax.set_xticklabels([f"{int(h):02d} h" for h in xticks])
        ax.set_xlim(min(hours), max(hours))

        # Repères jour/nuit simplifiés : 06 h et 18 h.
        for h in range(6, int(max(hours)) + 1, 24):
            ax.axvline(
                h,
                color="black",
                linestyle="--",
                linewidth=1.0,
                alpha=0.6,
                zorder=15,
            )
        for h in range(18, int(max(hours)) + 1, 24):
            ax.axvline(
                h,
                color="black",
                linestyle="--",
                linewidth=1.0,
                alpha=0.6,
                zorder=15,
            )

    fig.subplots_adjust(
        left=0.055,
        right=0.965,
        bottom=0.07,
        top=0.91,
        wspace=0.28,
        hspace=0.30,
    )

    plt.show()


# ============================================================================
# MAIN
# ============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Calcul du seeing optique AROME a partir des GRIB2 deja telecharges."
    )
    parser.add_argument(
        "data_dir",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Folder containing the downloaded AROME GRIB2 files (default: current directory).",
    )
    return parser.parse_args()


def main():
    global DATA_DIR
    DATA_DIR = parse_args().data_dir

    print()
    print("=" * 80)
    print("CALCUL SEEING AROME — 2 MODÈLES SÉPARÉS PAR H_COULIM")
    print("=" * 80)
    print(f"Dossier : {DATA_DIR}")
    print(
        f"Site    : {LAT_SITE:.4f} N, "
        f"{LON_SITE:.4f} E"
    )
    print(
        f"Hauteurs : {len(HEIGHTS)} niveaux, "
        f"20–3000 m AGL"
    )
    print(f"k       : {K_CN2}")
    print("Modèle BL : TKE")
    print("Modèle FA : cisaillement de vent, E = S²")
    print()

    hp1_files = find_grib_files("HP1")
    hp2_files = find_grib_files("HP2")
    ip1_files = find_grib_files("IP1")
    sp2_files = find_grib_files("SP2")

    print(f"HP1 : {len(hp1_files)} fichiers")
    print(f"HP2 : {len(hp2_files)} fichiers")
    print(f"IP1 : {len(ip1_files)} fichiers")
    print(f"SP2 : {len(sp2_files)} fichiers")
    print()

    # ------------------------------------------------------------------
    # LECTURE DES FICHIERS : UNE SEULE FOIS PAR FICHIER
    # ------------------------------------------------------------------

    hp1_cache = {}
    hp2_cache = {}
    ip1_cache = {}
    sp2_cache = {}

    for path in hp1_files:
        print("Lecture HP1 :")
        data, lat, lon = read_grib_package(
            path,
            {"t", "u", "v", "pres"},
        )

        hp1_cache[path] = {
            "data": data,
            "lat": lat,
            "lon": lon,
        }

    print()

    for path in hp2_files:
        print("Lecture HP2 :")
        data, lat, lon = read_grib_package(
            path,
            {"tke"},
        )

        hp2_cache[path] = {
            "data": data,
            "lat": lat,
            "lon": lon,
        }

    print()

    for path in ip1_files:
        print("Lecture IP1 :")
        data, lat, lon = read_grib_package(
            path,
            {"t", "u", "v", "z"},
            allowed_types={"isobaricInhPa"},
        )

        ip1_cache[path] = {
            "data": data,
            "lat": lat,
            "lon": lon,
        }

    print()

    for path in sp2_files:
        print("Lecture SP2 :")
        data, lat, lon = read_grib_package(
            path,
            {"blh", "h_coulim"},
            allowed_types={"surface"},
        )

        sp2_cache[path] = {
            "data": data,
            "lat": lat,
            "lon": lon,
        }

    print()
    print("=" * 80)
    print("CONSTRUCTION DES PROFILS TEMPORELS")
    print("=" * 80)

    rows = []
    results_by_hour = {}

    for hour in range(
        0,
        FORECAST_HOURS + 1,
    ):

        hp1_file = select_file_for_hour(
            hp1_files,
            hour,
        )
        hp2_file = select_file_for_hour(
            hp2_files,
            hour,
        )

        ip1_file = select_file_for_hour(
            ip1_files,
            hour,
        )

        sp2_file = select_file_for_hour(
            sp2_files,
            hour,
        )

        hp1_data = hp1_cache[hp1_file]["data"]
        hp2_data = hp2_cache[hp2_file]["data"]
        ip1_data = ip1_cache[ip1_file]["data"]
        sp2_data = sp2_cache[sp2_file]["data"]
        
        

        profile_tke = build_profile(
            hp1_data,
            hp2_data,
            hour,
            hp1_cache[hp1_file]["lat"],
            hp1_cache[hp1_file]["lon"],
        )

        result_tke = calculate_cn2_tke(profile_tke)

        profile_shear = make_isobaric_profile(
            ip1_data,
            hour,
            ip1_cache[ip1_file]["lat"],
            ip1_cache[ip1_file]["lon"],
        )

        result_shear = calculate_cn2_shear(profile_shear)

        h_coulim = get_h_coulim(sp2_data, hour)

        z_combined, cn2_combined = combine_profiles(
            result_tke,
            result_shear,
            h_coulim,
        )

        # Profil d'affichage : on conserve les niveaux hauteur HP1/HP2.
        # Cn² est interpolé uniquement pour la figure.
        cn2_display = interpolate_cn2_for_display(
            HEIGHTS,
            z_combined,
            cn2_combined,
        )

        # Résultat conservé pour l'affichage matriciel.
        result = {
            **result_tke,
            "Cn2": cn2_display,
            "H_COULIM": h_coulim,
            "z_combined": z_combined,
            "Cn2_combined": cn2_combined,
            "shear_z": result_shear["z"],
            "shear_Cn2": result_shear["Cn2"],
            "shear_S": result_shear["S"],
        }

        results_by_hour[hour] = result

        integral_cn2, r0, seeing = calculate_seeing(
            z_combined,
            cn2_combined,
        )

        tke_min = np.nanmin(result_tke["TKE"])
        tke_max = np.nanmax(result_tke["TKE"])

        cn2_valid = cn2_combined[np.isfinite(cn2_combined)]
        if cn2_valid.size:
            cn2_min = np.nanmin(cn2_valid)
            cn2_max = np.nanmax(cn2_valid)
        else:
            cn2_min = np.nan
            cn2_max = np.nan

        rows.append({
            "forecast_hour": hour,
            "grid_lat": result["grid_lat"],
            "grid_lon": result["grid_lon"],
            "integral_Cn2": integral_cn2,
            "r0_m": r0,
            "seeing_arcsec": seeing,
            "H_COULIM_m": h_coulim,
            "tke_min": tke_min,
            "tke_max": tke_max,
            "cn2_min": cn2_min,
            "cn2_max": cn2_max,
        })

        if np.isfinite(seeing):
            seeing_txt = f"{seeing:.6f} arcsec"
        else:
            seeing_txt = "NaN (TKE indisponible)"

        if np.isfinite(tke_min):
            tke_txt = f"{tke_min:.3e}→{tke_max:.3e}"
        else:
            tke_txt = "NaN"

        if np.isfinite(cn2_min):
            cn2_txt = f"{cn2_min:.3e}→{cn2_max:.3e}"
        else:
            cn2_txt = "NaN"

        print(
            f"H+{hour:02d} | "
            f"H_COULIM={h_coulim:.1f} m | "
            f"TKE={tke_txt} | "
            f"Cn²={cn2_txt} | "
            f"seeing={seeing_txt}"
        )

    df = pd.DataFrame(rows)

    output = DATA_DIR / "seeing_AROME_local.csv"
    df.to_csv(
        output,
        index=False,
    )

    # ------------------------------------------------------------------
    # DIAGNOSTIC TEMPOREL
    # ------------------------------------------------------------------

    seeing = df["seeing_arcsec"].to_numpy(float)
    tke_max = df["tke_max"].to_numpy(float)
    h_coulim_series = df["H_COULIM_m"].to_numpy(float)
    cn2_integral = df["integral_Cn2"].to_numpy(float)

    # ------------------------------------------------------------------
    # VÉRIFICATION DES VARIATIONS DES VARIABLES BRUTES
    # ------------------------------------------------------------------

    print()
    print("=" * 80)
    print("VÉRIFICATION DES VARIATIONS TEMPORELLES")
    print("=" * 80)

    check_hours = [h for h in [1, 6, 12, 24, 36, 48]
                   if h in results_by_hour]

    for h in check_hours:
        r = results_by_hour[h]
        print(
            f"H+{h:02d} : "
            f"T(surface)={r['T'][0]:.3f} K, "
            f"TKE(20m)={r['TKE'][0]:.6e}, "
            f"U(20m)={r['U'][0]:.3f} m/s, "
            f"V(20m)={r['V'][0]:.3f} m/s"
        )

    print()
    print(
        "Ces valeurs permettent de vérifier directement que les "
        "profils changent bien avec le step GRIB."
    )

    print()
    print("=" * 80)
    print("DIAGNOSTIC TEMPOREL")
    print("=" * 80)

    print(
        f"H_COULIM min/max : "
        f"{np.nanmin(h_coulim_series):.1f} / "
        f"{np.nanmax(h_coulim_series):.1f} m"
    )

    print(
        f"Seeing min/max : "
        f"{np.nanmin(seeing):.6f} / "
        f"{np.nanmax(seeing):.6f} arcsec"
    )

    print(
        f"TKE max min/max : "
        f"{np.nanmin(tke_max):.6e} / "
        f"{np.nanmax(tke_max):.6e}"
    )

    print(
        f"∫Cn² min/max : "
        f"{np.nanmin(cn2_integral):.6e} / "
        f"{np.nanmax(cn2_integral):.6e}"
    )

    if np.allclose(
        seeing,
        seeing[0],
        rtol=1e-10,
        atol=1e-12,
        equal_nan=True,
    ):
        print()
        print(
            "ATTENTION : le seeing est encore strictement constant."
        )
        print(
            "Vérifier alors les valeurs des différents 'step' "
            "dans les lignes 'pas temporels trouvés'."
        )
    else:
        print()
        print(
            "OK : le seeing varie dans le temps."
        )

    print()
    print(
        f"CSV : {output}"
    )

    # ------------------------------------------------------------------
    # UNE SEULE FIGURE DANS SPYDER
    # ------------------------------------------------------------------

    make_one_figure(
        results_by_hour,
        df,
    )


if __name__ == "__main__":
    main()
