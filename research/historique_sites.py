#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Historique : toutes les previsions AROME et toutes les mesures, par site.

- Previsions : tous les runs deja calcules par validation_sites.py
  (dossier cache_validation). Les runs sont recolles bout a bout ; si deux
  runs se recouvrent, l'echeance du run le plus recent est gardee.
- Mesures : tous les fichiers connus (collecteurs, releves, exports), mis en
  TU et dedoublonnes ; affichees en brut + mediane horaire (heure ronde,
  mesures a +/-30 min, echelle des echeances AROME), sans filtre glissant. Les fichiers en heure locale sont convertis avec le
  fuseau Europe/Paris (heure d'ete / d'hiver geree).
- A chaque nouveau run (passe par validation_sites.py) ou nouveau releve,
  relancer ce script : les K sont recalibres par site sur toutes les periodes
  disponibles (coefficients_calibres.json garde l'historique), puis la frise
  est refaite avec la courbe la mieux correlee.
"""
from pathlib import Path
import sys as _sys; _sys.path.insert(0, str(Path(__file__).resolve().parent))  # chemins.py est a cote
from chemins import CACHE, MESURES, TESTS as TESTS_DIR, PREVISIONS, MESURES_V1
import json
import re

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

V2 = Path(__file__).resolve().parent
CACHE_DIR = CACHE
CLAUDE = MESURES
TESTS = TESTS_DIR
OUTPUT = PREVISIONS / "historique_sites.png"
# Historique des coefficients recalibres (une entree par lancement)
COEFF_FILE = PREVISIONS / "coefficients_calibres.json"

# K = (K_TKE, K_CIS, K_TKE_CONV)
# 08/10 soir, demande utilisateur "meilleure correlation possible pour chaque site" : rapports entre K qui donnent
# r >= r_max - 0.03, puis erreur relative minimale, puis niveau (moyenne de log(prevu/mesure) = 0).
# Valeurs precedentes : Drome 10/33.5/0.1, Copernic 3/30/0.3, Saint-Veran 2/63/0.56, OHP 0.85/20/0.68, Villeneuve 2/71.1/0.1.
# 09/10 : decalage temporel essaye puis retire (demande utilisateur) -> retour aux K "meilleure correlation" sans
# decalage. K essayes avec decalage : Drome 7.78/43.7/0.008, Copernic 108/271.3/0.108, St-V 0.385/108.5/0.385,
# OHP 0.838/29.7/0.838, Villeneuve 3.27/51.9/0.003.
# 09/10 20h40 : recalibration de tous les sites (methode habituelle, toutes les heures, apres releve).
# Avant : Drome 15.8/11.2/0.1, Copernic 66.3/166.4/0.1, Saint-Veran 6/12/0.1 (script), OHP 0.829/20.8/0.659,
# Villeneuve 2.32/65.5/0.002. Drome et Copernic inchanges (deja a l'optimum ; K_conv sans effet la nuit).
SITES = {
    # 09/10 22h : JEUX JOUR / NUIT separes (regle utilisateur), cales separement sur toutes les donnees.
    # Drome : K du script jour et nuit (choix utilisateur recent ; cale nuit possible : 10.9/13.7/0.1, r 0.63).
    # Saint-Veran : jour = script (non cale, effets de cheminee), nuit calee (8 h).
    # Copernic : pas d'heure de jour mesuree -> jour = ancien K. Avant (un seul jeu) : Copernic 66.3/166.4/0.1,
    # Saint-Veran 3.16/39.8/0.1, OHP 0.799/20.1/0.635, Villeneuve 1.80/40.2/0.002.
    # 09/10 22h15 : regle jour / nuit ANNULEE par l'utilisateur -> retour a un seul jeu par site (valeurs d'avant).
    # (le code accepte toujours {"jour": K, "nuit": K} si la regle revient ; essai jour/nuit : OHP jour 0.00882/8.82/1.4
    #  nuit 0.776/38.9/0.635, Villeneuve jour 1.19/1.88/0.473 nuit 4.84/153/0.002, Copernic nuit 68.3/171/0.1)
    # 09/10 22h30 : REGLE "tous les sites cales sur la NUIT uniquement". K_conv non contraint la nuit -> inchange.
    # Avant : Drome 8/40/0.1, Copernic 66.3/166.4/0.1, St-V 3.16/39.8/0.1, OHP 0.799/20.1/0.635, Villeneuve 1.80/40.2/0.002.
    # 09/10 22h40 : calibration TOTALE (jour + nuit, demande utilisateur). Avant (calage nuit) : Drome 9.53/12/0.1,
    # Copernic 68.3/171/0.1, St-V 3.21/40.4/0.1, OHP 0.709/44.8/0.635, Villeneuve 4.88/154/0.002.
    # 10/10 01h40 : recalibration totale apres releve (avant : Drome 9.21/11.6/0.1, St-V 0.145/129/0.182,
    # OHP 0.353/28.1/0.353, Villeneuve 1.19/42.3/0.001). OHP avec K_TKE >= K_conv.
    # 10/10 02h10 : recalage sur les donnees de NUIT seulement (K_conv non contraint la nuit -> inchange).
    # Avant (calage total 01h40) : Drome 10.9/8.67/0.1, Copernic 68.3/171.5/0.1, St-V 0.137/136.9/0.086,
    # OHP 0.344/27.3/0.344, Villeneuve 1.71/43.0/0.002.
    # 10/10 02h30 : recalage NUIT, heures NON ponderees, rapports BORNES (K_CIS/K_TKE 0.1-100, K_conv/K_TKE 0.1-10).
    # Avant (nuit, ponderee, non bornee) : Drome 10.9/8.67/0.1, Copernic 68.3/171/0.1, St-V 7.02/22.2/0.086,
    # OHP 1.1/27.7/0.344, Villeneuve 4.52/143/0.002.
    "Drôme":       {"cache_tag": "Dr_me",       "K_script": (8, 40, 0.1), "K_new": (3.94, 49.7, 0.1)},  # V2bd cale nuit 18/10 : TOUTES les mesures, SANS AUCUN filtre, capture ROSA du 16/10 incluse
    "Copernic":    {"cache_tag": "Copernic",    "K_script": (3, 30, 0.3), "K_new": (11.2, 112, 0.1)},  # V2bd cale nuit 18/10 : TOUTES les mesures, SANS AUCUN filtre, capture ROSA du 16/10 incluse
    "Saint-Veran": {"cache_tag": "Saint_Veran", "K_script": (6, 12, 0.1), "K_new": (5.17, 41.1, 0.086)},  # V2bd cale nuit 18/10 : TOUTES les mesures, SANS AUCUN filtre, capture ROSA du 16/10 incluse
    "OHP":         {"cache_tag": "OHP",         "K_script": (8, 40, 0.1), "K_new": (0.767, 48.4, 0.01)},  # V2bd cale nuit 18/10 : TOUTES les mesures, SANS AUCUN filtre, capture ROSA du 16/10 incluse ; K_conv = 0.01 impose par l'utilisateur
    "Seeing monitor 5": {"cache_tag": "Villeneuve",  "K_script": (8, 40, 0.1), "K_new": (5.08, 80.5, 0.002)},  # V2bd 17/10 (utilisateur) : cale SANS les nuits du 08 et 13/10 (les 2 plus au-dessus de la droite), sans autre filtre
    # 12/10 : Pic du Midi ajoute (mesures : fichier transmis par l'utilisateur, 17/10/2025 -> 02/10/2026, TU).
    # K par defaut du script V2 en attendant un calage ; maille AROME a 2195 m pour un sommet a 2877 m (682 m d'ecart).
    "Pic du Midi": {"cache_tag": "Pic_du_Midi", "K_script": (8, 40, 0.1), "K_new": (1.8, 22.6, 0.1)},  # V2bd cale nuit 18/10 : TOUTES les mesures, SANS AUCUN filtre, capture ROSA du 16/10 incluse
    # 15/10 : Cosmodrome ajoute (DIMM de l'utilisateur, nuit du 14 au 15/10, 00h25-01h16 TU) ; K de depart = K de la carte
    # 15/10 : NIVEAU seul cale sur les 51 min de DIMM (2 heures), rapport K_CIS/K_TKE de la carte (17,5) ; V2b (0.908, 15.9) ;
    # equivalents : V2bd (1.026, 18.0), V2 (0.709, 12.4). Integrales tirees des profils pan_Cosmodrome2_* (disque F: absent)
    "Cosmodrome": {"cache_tag": "Cosmodrome", "K_script": (2, 35, 0.1), "K_new": (1.03, 18, 0.1)},  # V2bd : niveau cale sur les 2 medianes (mesures > 5 arcsec retirees), rapport CIS/TKE garde (non contraint)
}
# Modele V1 (code/V1/SeeingAromeV1.py, sans convection, voir seeing_v1_sites.py) : K = (K_TKE, K_CIS).
# Valeurs du script V1 : Drome 4/40, Saint-Veran 1.8/1, autres 4/40 (K actifs, Verclause).
# 08/10 : meilleurs K (erreur relative minimale, grille 1e-3..1e4, run 06/10) pour Copernic, OHP, Villeneuve ;
# Drome (pas de mesure sur le run) et Saint-Veran (optimum en butee, K_TKE -> 0, correlation negative) : script V1.
# 08/10 soir : OHP (1, 20) -> (0.71, 25.1), Villeneuve (0.63, 31.6) -> (1.78, 63.1), recales avec les nuits du 08/10.
# Copernic : retour aux K du script V1 (4, 40) le 08/10 soir, a la demande de l'utilisateur (avant 70.8, 398).
# 08/10 soir, meilleure correlation (meme methode que la V2) ; Drome : pas de mesure sur les runs V1 -> script V1.
# 09/10 : sans decalage (essai avec decalage retire : Copernic 180.4/254.8, St-V 0.09/90.3, OHP 0.565/31.75, Villeneuve 2.585/46).
# 09/10 recale avec la nuit 08-09 : Copernic (76.3, 382.5) -> (57.6, 144.7), OHP (0.76, 24.0) -> (0.618, 27.6).
# 09/10 : Villeneuve (1.63, 64.7) -> (0.896, 74.5), correlation maximale depart K=1.
# 09/10 : Saint-Veran remis aux K du script V1 (1.8, 1) (avant 0.159, 159.2).
# 09/10 : Copernic remis aux K du script V1 (4, 40), K recales (57.6, 144.7) non physiques.
# 09/10 soir : Copernic calage libre demande -> (57.6, 144.7) (avant 4, 40).
# 09/10 20h40 recalibration (toutes les heures) : St-V (1.8, 1) -> (0.147, 147.4) EN BUTEE, OHP (0.618, 27.6) -> (0.518, 26.0),
# Villeneuve (0.896, 74.5) -> (1.454, 36.5) ; Drome (pas de mesure V1) et Copernic inchanges.
# 09/10 21h : OHP recale ; Saint-Veran V1 remis au script (1.8, 1) : 2 h de nuit seulement, calage de nuit impossible.
# 09/10 22h : V1 en jeux jour / nuit (avant : Copernic 57.6/144.7, OHP 0.527/26.4, Villeneuve 1.454/36.5).
# 09/10 22h15 : regle jour / nuit annulee -> un seul jeu (valeurs d'avant).
# 09/10 22h30 : V1 calee sur la nuit (Drome, St-V : 2 h de nuit -> script). Avant : Copernic 57.6/144.7, OHP 0.527/26.4,
# Villeneuve 1.454/36.5.
# 09/10 22h40 calibration totale (avant : St-V 1.8/1, OHP 0.386/48.6, Villeneuve 3.04/152).
# 10/10 01h40 : recalibration totale (Drome V1 calable : 7 h).
# 10/10 02h10 : V1 recalee sur la NUIT seulement. Avant : Drome 4/40 et St-V 1.8/1 (remis a la demande de l'utilisateur),
# Copernic 54.8/173.4, OHP 0.177/35.3, Villeneuve 1.364/38.4.
# 10/10 02h30 : V1 recalee nuit, non ponderee, rapports bornes. Avant : Drome 0.447/224, Copernic 54.8/173,
# St-V 0.214/214, OHP 0.373/47, Villeneuve 2.86/143.
# 12/10 : Drome V1 essai (4, 40) (avant cale nuit 1.19, 119)
# 14/10 : Drome V1 calee sur les mesures 3-5" (PLAGE_MESURE), butee CIS/TKE = 100 ; avant (5.89, 23.5)
# 14/10 : Drome V1 (4, 40) impose par l'utilisateur (avant 1.16, 116)
# 14/10 apres-midi : Drome V1 (4, 40) impose par l'utilisateur (avant cale 3.4, 21.4)
# 14/10 : Drome V1 calee nuit sur les mesures 2.5-5.5" (32 h), BUTEE CIS/TKE = 100 ; avant (4, 40) impose
# 14/10 soir : Drome V1 calee nuit hors saturation 2.3-5.3" (29 h), BUTEE CIS/TKE = 100 ; avant (1.15, 115)
# 14/10 soir : Drome V1 calee nuit sur les mesures 3-4.5" (11 h, r -0.24) ; avant (1.08, 108)
# 14/10 soir : Drome V1 calee nuit sur TOUTES les mesures (43 h, r 0.57) ; avant (2.36, 18.8)
# 14/10 soir : Drome V1 calee nuit sur les mesures 0-3.3" (12 h, r 0.87) ; avant (3.4, 21.4)
# 14/10 soir : Drome V1 calee nuit, toutes les mesures, portions < 3 h successives retirees (43 h, r 0.57) ; avant (5.8, 23.1)
# 14/10 nuit : Drome V1 calee nuit sur les mesures 2-5.2" (32 h, r 0.66) ; avant (3.4, 21.4)
# 15/10 : Drome V1 calee nuit EN ENTIER (toutes les donnees, 44 h, r 0.58) ; avant (3.63, 11.5)
K_V1 = {"Drôme": (2.26, 45.1),   # Drome : essai demi-nuits du 15/10 annule (utilisateur)
 "Copernic": (6.06, 96.1), "Saint-Veran": (4.5, 28.4), "OHP": (0.459, 45.9),   # OHP 15/10 essai nuit du 10/10 seule (avant 0.475, 47.5)

        "Seeing monitor 5": (3, 75.4), "Pic du Midi": (1.1, 21.9),
        "Cosmodrome": (0.352, 15.8)}   # 15/10 : niveau seul cale sur les 2 medianes du DIMM (rapport garde)
# 17/10 : Seeing monitor 5 cale SANS les nuits du 02, 08, 10, 13/10 ; Saint-Veran, tous les modeles cales sans les 10 % d'heures ou la mesure depasse le plus la prevision (selection sur toutes les mesures)
# 15/10 soir (utilisateur : tous les modeles, chacun cale) : K de nuit de la V2 d'origine et de la V2b ; V2bd = SITES[...]['K_new'], V1 = K_V1
K_AUTRES_MODELES = {'V2': {'Drôme': (4.35, 34.5, 0.1), 'Copernic': (35.2, 55.7, 0.1), 'Saint-Veran': (4.03, 40.3, 0.086), 'OHP': (1.66, 26.4, 0.01), 'Seeing monitor 5': (5.3, 66.7, 0.002), 'Pic du Midi': (1.71, 21.6, 0.1), 'Cosmodrome': (0.706, 12.4, 0.1)}, 'V2b': {'Drôme': (4.21, 42.1, 0.1), 'Copernic': (10.7, 107.0, 0.1), 'Saint-Veran': (4.12, 41.2, 0.086), 'OHP': (0.871, 43.6, 0.01), 'Seeing monitor 5': (4.78, 75.7, 0.002), 'Pic du Midi': (1.72, 21.7, 0.1), 'Cosmodrome': (0.909, 15.9, 0.1)}}
TRACER_V1 = True
COULEUR_V1 = "#0b3d91"          # bleu fonce, tirets : AROME modele V1
COULEUR_V1_CORR = "#e34948"     # rouge : modele V1 sur les nuages de correlation
MIRATLAS_DIR = CLAUDE / "seeing-miratlas"
PREFIXE_MIRATLAS = {"Seeing monitor 5": "villeneuve"}   # 13/10 : site renomme a l'affichage (demande utilisateur)

# Coordonnees des sites (lat, lon) et definition de la nuit (grise sur les figures)
# Copernic corrige le 09/10 (coordonnees donnees par l'utilisateur ; avant 44.5828, 5.9868, ~2.4 km trop au nord)
COORDS = {"Drôme": (44.3814, 5.4286), "Copernic": (44.56179, 5.99762), "Saint-Veran": (44.6988, 6.9083),
          "OHP": (43.9317, 5.7133), "Seeing monitor 5": (43.9015, 5.8659), "Pic du Midi": (42.93642, 0.14122),
          "Cosmodrome": (44.203477, 5.510984)}   # 15/10 : position donnee par l'utilisateur (maille AROME 44.2000 / 5.5000, 1110 m)
NUIT_SOLEIL_DEG = -12           # ancienne definition de la nuit (Soleil sous cette hauteur), plus utilisee
# 08/10 (regle utilisateur) : nuit = plage horaire fixe en TU, de NUIT_DEBUT a NUIT_FIN, pour tous les sites
NUIT_DEBUT = (17, 30)
NUIT_FIN = (6, 0)
NUIT_TEXTE = "nuit 17h30-06h00 TU"
COULEUR_NUIT = "#e4e3df"


def est_nuit(t):
    """True pour les instants (TU) entre NUIT_DEBUT et NUIT_FIN."""
    t = pd.DatetimeIndex(t)
    minutes = t.hour.values * 60 + t.minute.values
    return (minutes >= NUIT_DEBUT[0] * 60 + NUIT_DEBUT[1]) | (minutes < NUIT_FIN[0] * 60 + NUIT_FIN[1])


def sun_elevation(t, lat, lon):
    """Hauteur du Soleil (degres), formule approchee NOAA, t en TU."""
    t = pd.DatetimeIndex(t)
    doy = t.dayofyear.values
    hr = t.hour.values + t.minute.values / 60
    g = 2 * np.pi / 365 * (doy - 1 + (hr - 12) / 24)
    decl = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g) - 0.006758 * np.cos(2 * g)
            + 0.000907 * np.sin(2 * g) - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    eqt = 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g)
                    - 0.014615 * np.cos(2 * g) - 0.040849 * np.sin(2 * g))
    ha = np.radians((hr * 60 + eqt + 4 * lon) / 4 - 180)
    la = np.radians(lat)
    return np.degrees(np.arcsin(np.sin(la) * np.sin(decl) + np.cos(la) * np.cos(decl) * np.cos(ha)))


def est_jour_nuit(K):
    """True si K est un jeu jour / nuit : {"jour": K, "nuit": K} (regle utilisateur du 09/10)."""
    return isinstance(K, dict)


def K_heure(K, t):
    """K a utiliser a l'instant t (TU) : jeu de nuit (17h30-06h) ou de jour."""
    if not est_jour_nuit(K):
        return K
    return K["nuit"] if bool(est_nuit([t])[0]) else K["jour"]


def texte_K(K):
    """Coefficients ecrits en clair sur les figures."""
    if est_jour_nuit(K):
        return f"jour : {texte_K(K['jour'])}   |   nuit : {texte_K(K['nuit'])}"
    return f"K_TKE = {K[0]:g}   K_CIS = {K[1]:g}   K_conv = {K[2]:g}"


def dernier_recalage(nom):
    """(K, heures) de la derniere recalibration 'erreur relative' enregistree, ou None."""
    if not COEFF_FILE.exists():
        return None
    for entree in reversed(json.loads(COEFF_FILE.read_text(encoding="utf-8"))):
        s = entree.get("sites", {}).get(nom)
        if s and entree.get("methode") == "erreur relative":
            return (s["K_TKE"], s["K_CIS"], s["K_TKE_CONV"]), s["heures"]
    return None


def texte_K_v1(K):
    if est_jour_nuit(K):
        return f"jour : K_TKE = {K['jour'][0]:g}  K_CIS = {K['jour'][1]:g}   |   nuit : K_TKE = {K['nuit'][0]:g}  K_CIS = {K['nuit'][1]:g}"
    return f"K_TKE = {K[0]:g}   K_CIS = {K[1]:g}   (pas de convection)"


def seeing_v1_k(v1m, d, K):
    """Seeing V1 pour un jeu de K simple ou jour / nuit."""
    if not est_jour_nuit(K):
        return v1m.seeing_v1(d, K, seeing_arcsec)
    return np.where(est_nuit(d.t), v1m.seeing_v1(d, K["nuit"], seeing_arcsec), v1m.seeing_v1(d, K["jour"], seeing_arcsec))


def v1():
    """Module seeing_v1_sites (charge a la demande)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("seeing_v1_sites", V2 / "seeing_v1_sites.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def encadre_K(ax, nom, K_utilises, complet=False, v1_trace=False):
    """
    Encadre des coefficients (en haut a droite du panneau). complet=False :
    seulement ceux des courbes tracees ; sinon aussi script/defaut et recales.
    """
    cfg = SITES[nom]
    if v1_trace:
        lignes = [f"{nom_v2()} : {texte_K(K_utilises)}", f"V1 : {texte_K_v1(K_V1[nom])}"]
    else:
        lignes = [f"utilises : {texte_K(K_utilises)}"]
    if complet:
        script = "script   " if nom in ("Drôme", "Copernic", "Saint-Veran") else "defaut   "
        lignes.append(f"{script}: {texte_K(cfg['K_script'])}")
        r = dernier_recalage(nom)
        if r:
            lignes.append(f"recales ({r[1]} h) : {texte_K(tuple(round(k, 3) for k in r[0]))}")
    ax.text(0.995, 0.97, "\n".join(lignes), transform=ax.transAxes, ha="right", va="top", fontsize=7,
            family="monospace", zorder=30,
            bbox=dict(boxstyle="round,pad=0.35", facecolor="#fcfcfb", edgecolor="#c9c8c3", alpha=0.92))
HORAIRE_MIN_POINTS = 1      # 09/10 21h "a partir de maintenant, prends tout en compte" (avant 5 mesures minimum par heure)
COULEUR_AROME = "#2a78d6"   # bleu : previsions AROME
COULEUR_MESURES = "#eb6834" # orange : mesures des seeing monitors


# ============================================================================
# MESURES
# ============================================================================
def to_utc(series, local=False, dayfirst=False):
    t = pd.to_datetime(series, dayfirst=dayfirst, utc=not local) if not local else pd.to_datetime(series, dayfirst=dayfirst)
    if local:
        t = t.dt.tz_localize("Europe/Paris", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    return t.dt.tz_localize(None)


def read(path, col_t, col_s, local=False, dayfirst=False, fallback=None):
    if not Path(path).exists():
        return None
    df = pd.read_csv(path)
    s = df[col_s]
    if fallback:
        s = s.fillna(df[fallback])
    return pd.DataFrame({"t": to_utc(df[col_t], local, dayfirst), "seeing": pd.to_numeric(s, errors="coerce"),
                         "source": Path(path).name})


# 13/10 (demande utilisateur) : sites sans mesures recentes, retires des figures de prevision (prevision collee, Cn2 collee)
SITES_HORS_PREVISION = {"Pic du Midi"}

# 12/10 (demande utilisateur) : heures retirees des mesures (pic horaire de l'OHP le 12/10 a 01h TU : 4 mesures seulement)
HEURES_EXCLUES = {}   # 15/10 (utilisateur) : pic de l'OHP remis ; avant {"OHP": ["2026-10-12 01:00"]}
PICS_GARDES = {}   # 15/10 (utilisateur) : regle des pics remise pour toutes les heures ; essai precedent {"OHP": ["2026-10-12 01:00"]}

# 12/10 (regle utilisateur) : un PIC horaire forme de quelques mesures seulement, bien moins que d'habitude,
# n'est ni trace ni pris dans le calage. Pic = mediane horaire au-dessus de celles de l'heure d'avant ET de
# l'heure d'apres (quand elles existent, au moins une) ; "quelques mesures" = moins de PIC_FRACTION_MESURES x le
# nombre habituel de mesures par heure du site (mediane des comptes horaires).
LIMITES_INSTRUMENT = {}   # 13/10 : retrait sur la MESURE abandonne (remplace par PLAGE_PREVUE ci-dessous) ; ex. {"Drôme": (2.0, 6.0)}
# 13/10 (regle utilisateur) : ROSA ne mesure qu'entre 2 et 6" -> pour la Drome, les heures dont la PREVISION AROME est
# hors de [2, 6]" sont tracees en gris sur les figures de correlation et exclues de la correlation et du calage
PLAGE_PREVUE = {}   # 13/10 soir : {"Drôme": (2.1, 5.6)} sur mesure ET prevision ; remplace le 14/10 par PLAGE_MESURE ci-dessous
ECHELLE_Y_HISTORIQUE = {"Drôme": (1.8, 6.2)}   # 14/10 (utilisateur) : axe vertical fixe de la figure historique
PLAGE_PREVISION = {}   # 14/10 soir : annule ; avant {"Drôme": (0.0, 5.5)} (prevision AROME > 5.5" retiree)
PLAGE_MESURE = {}   # 18/10 (utilisateur) : calage sur TOUTES les donnees ; 16/10 Drome 2.8-5.3" ; 15/10 Drome entiere ; avant (2.0, 5.2), (2.0, 6.0), (0, 3.3), (3.0, 4.5), (2.3, 5.3), (2.5, 5.5)
                    # avant : aucun seuil ; plus tot {"Drôme": (3.0, 5.0)}
                    # (mesures seules, hors plage en gris et exclues ; remplacait PLAGE_PREVUE 2.1-5.6)
HEURES_HORS_PLAGE = {}                        # site -> heures retirees car trop pres des bornes (information)
PIC_FRACTION_MESURES = 0.25
PIC_DEPASSEMENT = 1.15     # pic = au moins 15 % au-dessus de la plus haute des deux heures voisines (les deux doivent exister)
PICS_RETIRES = {}          # site -> liste des heures retirees automatiquement (pour information)


def pics_peu_mesures(o):
    """Heures rondes a retirer selon la regle des pics a peu de mesures."""
    if not len(o):
        return pd.DatetimeIndex([])
    hr = o.t.dt.round("1h")
    g = o.groupby(hr).seeing.agg(med="median", n="size")
    habituel = g.n.median()
    av = g.med.reindex(g.index - pd.Timedelta(hours=1)).to_numpy()
    ap = g.med.reindex(g.index + pd.Timedelta(hours=1)).to_numpy()
    # vrai pic : les deux heures voisines existent (une heure de debut ou de fin de serie n'est pas un pic,
    # elle a juste peu de mesures parce que la mesure commence ou s'arrete) et on les depasse nettement
    pic = np.isfinite(av) & np.isfinite(ap) & (g.med.to_numpy() > PIC_DEPASSEMENT * np.fmax(av, ap))
    peu = g.n.to_numpy() < PIC_FRACTION_MESURES * habituel
    return g.index[pic & peu]


def observations(site):
    releves = sorted(d for d in (CLAUDE / "releves").iterdir() if d.is_dir()) if (CLAUDE / "releves").exists() else []
    parts = []
    if site == "Drôme":
        parts += [read(CLAUDE / "seeing-rosa/seeing_rosa.csv", "datetime", "seeing_brut_arcsec", local=True),
                  read(CLAUDE / "seeing-rosa/seeing_rosa_2026-09-19_UTC.csv", "datetime_utc", "seeing_brut_arcsec"),
                  read(CLAUDE / "seeing-rosa/seeing_rosa_2026-09-26_UTC.csv", "datetime_utc", "seeing_brut_arcsec")]
        parts += [read(d / "rosa_UTC.csv", "datetime_utc", "seeing_brut_arcsec") for d in releves]
        # 18/10 (utilisateur) : capture d'ecran du site ROSA du 16/10 03h locale, numerisee (nuit du 15 au 16/10, releve en echec)
        parts.append(read(CLAUDE / "seeing-rosa/rosa_capture_2026-10-16_UTC.csv", "datetime_utc", "seeing_brut_arcsec"))
    elif site == "Copernic":
        parts += [read(CLAUDE / "seeing-copernic/seeing_copernic.csv", "datetime", "seeing_arcsec", local=True),
                  read(CLAUDE / "seeing-copernic/seeing_copernic_2026-09-25_UTC.csv", "datetime_utc", "seeing_arcsec")]
        parts += [read(d / "copernic_UTC.csv", "datetime_utc", "seeing_arcsec") for d in releves]
    elif site in ("OHP", "Seeing monitor 5"):   # 13/10 : nom affiche "Seeing monitor 5" (fichiers Miratlas : prefixe interne)
        parts += [read(f, "datetime_utc", "day_ssm_arcsec", fallback="night_cdimm_arcsec")
                  for f in sorted(MIRATLAS_DIR.glob(f"{PREFIXE_MIRATLAS.get(site, site.lower())}_*_UTC.csv"))]
    elif site == "Saint-Veran":
        parts += [read(TESTS / "seeing_16-17_septembre_2026_UTC_SaintVeran2.csv", "UTC", "seeing_arcsec", dayfirst=True),
                  read(TESTS / "Saint_veran_UTC_Diurne_vert.csv", "UTC", "seeing_arcsec"),
                  read(MESURES_V1 / "Saint_veran_18_09_2026_jour_2.csv", "UTC", "seeing_arcsec", dayfirst=True),
                  read(TESTS / "Saint_veran_2026-09-25_27_UTC_capture.csv", "datetime_utc", "seeing_arcsec")]
        parts += [read(d / "saint_veran_UTC.csv", "datetime_utc", "day_ssm_arcsec", fallback="night_cdimm_arcsec")
                  for d in releves]
    elif site == "Cosmodrome":
        # 15/10 : DIMM de l'utilisateur, seeing au zenith (axe transverse), 1 point / 10 s, prepare par import_cosmodrome.py
        for fp in sorted((CLAUDE / "seeing-cosmodrome").glob("cosmodrome_*_UTC.csv")):
            d = pd.read_csv(fp)
            parts.append(pd.DataFrame({"t": pd.to_datetime(d.datetime_utc).dt.tz_localize(None),
                                       "seeing": pd.to_numeric(d.seeing_arcsec, errors="coerce"), "source": fp.name}))
    elif site.startswith("Pic du Midi"):
        # fichiers "Seeing_Data_*.txt" : colonnes separees par "|", 2e ligne = formats ; DATE1 en TU (verifie avec le jour julien)
        for fp in sorted((CLAUDE / "seeing_picdumidi").glob("Seeing_Data_*.txt")):
            d = pd.read_csv(fp, sep=r"\s*\|\s*", engine="python", skiprows=[1])
            d.columns = [c.strip() for c in d.columns]
            parts.append(pd.DataFrame({"t": pd.to_datetime(d.DATE1, format="%d/%m/%Y %H:%M:%S"),
                                       "seeing": pd.to_numeric(d.SEEING, errors="coerce"), "source": fp.name}))
    o = pd.concat([p for p in parts if p is not None], ignore_index=True).dropna(subset=["t", "seeing"])
    # meme mesure presente dans plusieurs fichiers : une seule fois
    # (Pic du Midi : une mesure toutes les ~30 s -> cle a la seconde, sinon une mesure sur deux serait perdue)
    o["cle"] = o.t.dt.round("1s" if site.startswith("Pic du Midi") or site == "Cosmodrome" else "1min")   # Cosmodrome : 1 point / 10 s
    o = o.drop_duplicates("cle").sort_values("t").reset_index(drop=True)
    o.attrs["site"] = site
    if site in SEUIL_MESURE_MAX:   # 15/10 (utilisateur) : points du monitor au-dessus du seuil retires (figures, stats, calage)
        o = o[o.seeing <= SEUIL_MESURE_MAX[site]].reset_index(drop=True); o.attrs["site"] = site
    if site in DEUX_MEDIANES and len(o) and CALAGE_DEUX_MEDIANES:
        # 15/10 (utilisateur) : pour le CALAGE seulement, les deux medianes (periode mesuree coupee en deux moities egales),
        # placees au milieu de chaque moitie ; les scripts de calage mettent CALAGE_DEUX_MEDIANES = True
        t0, t1 = o.t.min(), o.t.max(); mi = t0 + (t1 - t0) / 2; g = (o.t >= mi).astype(int)
        o = pd.DataFrame({"t": [t0 + (mi - t0) / 2, mi + (t1 - mi) / 2], "seeing": o.seeing.groupby(g).median().values,
                          "source": "deux medianes", "cle": [t0, mi]})
    # heures retirees a la demande de l'utilisateur (toutes leurs mesures, heure ronde +/- 30 min)
    exclues = pd.DatetimeIndex(HEURES_EXCLUES.get(site, []))
    if len(exclues):
        o = o[~o.t.dt.round("1h").isin(exclues)].reset_index(drop=True)
    # pics horaires a peu de mesures (regle du 12/10) : retires partout (figures, stats, calage)
    pics = pics_peu_mesures(o)
    pics = pd.DatetimeIndex(pics).difference(pd.DatetimeIndex(PICS_GARDES.get(site, [])))   # 15/10 : pics remis par l'utilisateur
    PICS_RETIRES[site] = list(pics)
    if len(pics):
        o = o[~o.t.dt.round("1h").isin(pics)].reset_index(drop=True)
    # 13/10 (utilisateur) : plage de fonctionnement de l'instrument ; une heure dont la mediane est trop pres d'une borne
    # (sous lo x 1.1 ou au-dessus de hi x 0.92) est retiree (la vraie valeur peut etre hors de la plage mesurable)
    if site in LIMITES_INSTRUMENT and len(o):
        lo, hi = LIMITES_INSTRUMENT[site]
        hr = o.t.dt.round("1h"); med = o.groupby(hr).seeing.transform("median")
        hors = (med < lo * 1.1) | (med > hi * 0.92)
        HEURES_HORS_PLAGE[site] = sorted(set(hr[hors]))
        o = o[~hors.values].reset_index(drop=True)
    # sites dont toutes les mesures de NUIT sont gardees, sans la regle des 3 h (colonne "libre")
    o["libre"] = (site in NUIT_SANS_REGLE_3H) & est_nuit(o.t)
    return filtre_sequences(o)


# Regle utilisateur du 08/10 : une mesure n'est prise en compte que si son heure fait partie
# d'au moins SEQUENCE_MIN_HEURES points horaires successifs (heures rondes consecutives ayant
# chacune >= HORAIRE_MIN_POINTS mesures). Les heures isolees (1 ou 2 points horaires) sont ignorees.
SEQUENCE_MIN_HEURES = 1     # 09/10 21h "prends tout en compte" : plus de regle des 3 h successives (avant 3)
# 09/10 (demande utilisateur) : a l'OHP, toutes les mesures de nuit sont prises en compte (pas de regle des 3 h la nuit)
NUIT_SANS_REGLE_3H = {"OHP"}
# 09/10 (regle utilisateur) : sites cales sur les heures de NUIT uniquement (effets de cheminee le jour a Saint-Veran)
NUIT_SEULE_CALAGE = {"Drôme", "Copernic", "Saint-Veran", "OHP", "Seeing monitor 5"}   # 09/10 22h30 : TOUS les sites


def filtre_sequences(o):
    heure = o.t.dt.round("1h")
    n = heure.value_counts()
    ok = n[n >= HORAIRE_MIN_POINTS].index.sort_values()
    libre = o["libre"].values if "libre" in o else np.zeros(len(o), dtype=bool)
    if not len(ok):
        return o[libre].reset_index(drop=True)
    seq = (ok.to_series().diff() != pd.Timedelta(hours=1)).cumsum()
    taille = seq.map(seq.value_counts())
    garde = ok[(taille >= SEQUENCE_MIN_HEURES).values]
    return o[heure.isin(garde).values | libre].reset_index(drop=True)


def heures_libres(o):
    """Heures rondes exemptees de la regle des 3 h (mesures de nuit des sites NUIT_SANS_REGLE_3H)."""
    return set(o.t[o["libre"]].dt.round("1h")) if "libre" in o else set()


def masque_sequences(index, libres=()):
    """Meme regle pour les heures COMPAREES (prevision ET mesure) : True si l'heure appartient a
    au moins SEQUENCE_MIN_HEURES heures comparees consecutives (ex. fin d'un run qui coupe une sequence),
    ou si c'est une heure exemptee (libres)."""
    t = pd.Series(pd.DatetimeIndex(index))
    ordre = t.sort_values()
    seq = (ordre.diff() != pd.Timedelta(hours=1)).cumsum()
    taille = seq.map(seq.value_counts())
    return (taille >= SEQUENCE_MIN_HEURES).reindex(t.index).values | t.isin(libres).values


def hourly_median(o, stats=False):
    """Mediane par heure ronde (mesures a +/-30 min), si au moins HORAIRE_MIN_POINTS mesures.
    15/10 : sites de SANS_MEDIANE_AFFICHEE -> rien pour les figures (stats=False) ; les stats (paires_horaires) la gardent."""
    if not stats and (o.attrs.get("site") in SANS_MEDIANE_AFFICHEE or o.attrs.get("source_site") in SANS_MEDIANE_AFFICHEE):
        return pd.DatetimeIndex([]), np.array([]), np.array([], bool)
    g = o.groupby(o.t.dt.round("1h"))["seeing"]
    h = pd.DataFrame({"mediane": g.median(), "n": g.size()})
    h = h[h.n >= HORAIRE_MIN_POINTS]
    return h.index, h.mediane.values, (h.index.to_series().diff() > pd.Timedelta(hours=1)).values


# ============================================================================
# PREVISIONS
# ============================================================================
def seeing_arcsec(integral, lam=500e-9):
    integral = np.asarray(integral, dtype=float)
    out = np.full_like(integral, np.nan)
    ok = integral > 0
    out[ok] = 0.98 * lam * (0.423 * (2 * np.pi / lam) ** 2 * integral[ok]) ** 0.6 * 206265.0
    return out


def forecasts_site(nom):
    """Previsions V2 du site (tous les runs recolles)."""
    return forecasts(SITES[nom]["cache_tag"])


def forecasts_v1_site(v1m, nom):
    """Previsions V1 du site (tous les runs recolles)."""
    return v1m.forecasts_v1(SITES[nom]["cache_tag"])


MODELE_V2 = "V2bd"   # 15/10 soir (utilisateur) : V2bd dans la chaine (cisaillement V2b + transition douce 100 m) ; avant "V2b" - "V2b" = cisaillement comme la V1 (cache_validation\v2b, recalcule des
                    # profils par scratchpad v2b_caches.py) ; runs sans cache V2b -> V2. "V2" = revenir a la V2 d'origine.
CACHE_V2B = CACHE_DIR / "v2b"
COULEUR_V2_ORIGINE = "#d63ca8"   # 15/10 : V2 d'origine (magenta, pointilles)
COULEUR_V2B = "#1baf7a"          # 15/10 : V2b (vert, pointilles)


def forecasts_modele(nom, modele):
    """Previsions d'une variante ("V2", "V2b", "V2bd"), quel que soit MODELE_V2."""
    global MODELE_V2
    m = MODELE_V2; MODELE_V2 = modele
    try:
        return forecasts_site(nom)
    finally:
        MODELE_V2 = m


def forecasts_v2_origine(nom):
    """Previsions de la V2 d'ORIGINE (caches V2), quel que soit MODELE_V2."""
    return forecasts_modele(nom, "V2")


def autres_modeles(nom):
    """15/10 (utilisateur : tous les modeles sur les figures) : variantes V2 non actives, chacune avec SES K calees
    (K_AUTRES_MODELES) -> liste (nom, couleur, previsions, K)."""
    out = []
    for mod, coul in (("V2", COULEUR_V2_ORIGINE), ("V2b", COULEUR_V2B)):
        K = globals().get("K_AUTRES_MODELES", {}).get(mod, {}).get(nom)
        if mod == MODELE_V2 or K is None:
            continue
        f = forecasts_modele(nom, mod)
        if f is not None and len(f):
            out.append((mod, coul, f, tuple(K)))
    return out


def nom_v2():
    """Nom du modele V2 actif pour les figures (15/10 : V2bd affichee partout)."""
    return MODELE_V2 if MODELE_V2 in VARIANTES_V2 else "V2"


VARIANTES_V2 = {"V2b": ("v2b", "V2b"), "V2bd": ("v2bd_100", "V2bd")}   # 15/10 : V2bd = cisaillement V2b + transition douce 100 m


def forecasts(tag):
    runs = []
    for f in CACHE_DIR.glob(f"*__{tag}__*.csv"):
        if MODELE_V2 in VARIANTES_V2:
            dossier, suf = VARIANTES_V2[MODELE_V2]
            fb = CACHE_DIR / dossier / f"{f.name.split('__')[0]}__{tag}__{suf}.csv"
            if fb.exists():
                f = fb
        d = pd.read_csv(f, parse_dates=["t"])
        d["run"] = d.t.iloc[0]          # echeance 0 = heure du run
        d["run_dir"] = f.name.split("__")[0]
        runs.append(d)
    if not runs:
        return None
    d = pd.concat(runs, ignore_index=True)
    # recouvrement : le run le plus recent l'emporte, sauf ses echeances sans TKE (H+0) si un autre run couvre l'heure
    d = d[~(~d.has_tke.astype(bool) & d.t.duplicated(keep=False))]
    # 17/10 (utilisateur) : runs PRINCIPAUX (00/06/12/18Z) prioritaires ; un run intermediaire ne sert qu'a combler les trous
    d["principal"] = (pd.DatetimeIndex(d.run).hour % 6 == 0)
    d = d.sort_values(["t", "principal", "run"]).drop_duplicates("t", keep="last").sort_values("t").reset_index(drop=True)
    return d


def arome(d, K):
    """Seeing AROME pour un jeu de K (simple ou jour / nuit) ; gap = debut d'un run non contigu."""
    if est_jour_nuit(K):
        tj, sj, gap = arome(d, K["jour"])
        _, sn, _ = arome(d, K["nuit"])
        return tj, np.where(est_nuit(d.t), sn, sj), gap
    k_tke, k_cis, k_conv = K
    s = seeing_arcsec(k_tke * d.I_tke + k_conv * d.I_conv + k_cis * d.I_cis)
    s = np.where(d.has_tke, s, np.nan)
    gap = (d.t.diff() > pd.Timedelta(hours=1)).values
    return d.t, s, gap


def plot_line(ax, t, s, gap, **kw):
    t, s = np.asarray(t), np.asarray(s, dtype=float)
    cuts = np.flatnonzero(gap)
    for a, b in zip(np.r_[0, cuts], np.r_[cuts, len(t)]):
        ax.plot(t[a:b], s[a:b], **kw)
        kw.pop("label", None)


# ============================================================================
# EPISODES (previsions ET mesures) ET AXE COMPRESSE
# ============================================================================
COUPURE_MESURES_H = 2       # trou de mesures qui separe deux episodes
MARGE_H = 0.5               # marge autour des mesures dans un episode
ECART_EPISODES_H = 1.5      # espace laisse entre deux episodes sur l'axe compresse
ETIREMENT_Y = 1.45          # haut de l'axe Y = max(medianes horaires, previsions) x ce facteur (place pour legende)


def intervals(t, max_gap_h):
    """Intervalles continus d'une serie de dates (coupure si trou > max_gap_h)."""
    t = pd.Series(sorted(t))
    if t.empty:
        return []
    cut = (t.diff() > pd.Timedelta(hours=max_gap_h)).cumsum()
    return [(g.iloc[0], g.iloc[-1]) for _, g in t.groupby(cut)]


def episodes(f, o):
    """Periodes ou il y a a la fois une prevision AROME et des mesures."""
    if f is None:
        return []
    t_prev = f.t[np.isfinite(arome(f, (1, 1, 1))[1])]
    prev = intervals(t_prev, 1)
    eps = []
    for a, b in intervals(o.t, COUPURE_MESURES_H):
        for pa, pb in prev:
            lo, hi = max(a, pa) - pd.Timedelta(hours=MARGE_H), min(b, pb) + pd.Timedelta(hours=MARGE_H)
            if hi > lo and ((o.t >= lo) & (o.t <= hi)).sum() >= HORAIRE_MIN_POINTS:
                e = (max(lo, pa), min(hi, pb + pd.Timedelta(minutes=30)))
                # regle des 3 h : la periode doit garder au moins SEQUENCE_MIN_HEURES points horaires
                # successifs une fois limitee a la prevision (sinon on n'affiche qu'un bout de prevision)
                if len(filtre_sequences(o[(o.t >= e[0]) & (o.t <= e[1])])):
                    eps.append(e)
    return eps


class AxeCompresse:
    """Convertit une date en position (heures) sur l'axe sans les vides."""

    def __init__(self, eps):
        self.eps, self.x0, x = eps, [], 0.0
        for a, b in eps:
            self.x0.append(x)
            x += (b - a) / pd.Timedelta(hours=1) + ECART_EPISODES_H

    def x(self, t, i):
        a = self.eps[i][0]
        return self.x0[i] + (pd.DatetimeIndex(t) - a) / pd.Timedelta(hours=1)

    def masque(self, t, i):
        a, b = self.eps[i]
        t = pd.DatetimeIndex(t)
        return (t >= a) & (t <= b)


# Poids d'une heure comparee selon l'echeance de la prevision : une prevision
# recente (echeance courte) compte plus. poids = exp(-echeance / TAU_POIDS_H).
TAU_POIDS_H = 24


PONDERATION_ECHEANCE = False    # 10/10 : regle supprimee par l'utilisateur (toutes les heures ont le meme poids)


def poids(echeance_h):
    """Poids d'une heure comparee : 1 pour toutes (avant le 10/10 : exp(-echeance / TAU_POIDS_H))."""
    e = np.asarray(echeance_h, dtype=float)
    return np.exp(-e / TAU_POIDS_H) if PONDERATION_ECHEANCE else np.ones_like(e)


def wcorr(x, y, w):
    """Correlation de Pearson ponderee."""
    x, y, w = (np.asarray(v, dtype=float) for v in (x, y, w))
    if len(x) < 3 or w.sum() <= 0:
        return np.nan
    mx, my = np.average(x, weights=w), np.average(y, weights=w)
    cov = np.average((x - mx) * (y - my), weights=w)
    sx, sy = np.sqrt(np.average((x - mx) ** 2, weights=w)), np.sqrt(np.average((y - my) ** 2, weights=w))
    return cov / (sx * sy) if sx > 0 and sy > 0 else np.nan


def wmedian(x, w):
    """Mediane ponderee. 12/10 : quand la moitie du poids tombe pile entre deux valeurs (nombre pair de
    poids egaux), on prend leur moyenne, comme une mediane ordinaire (avant : la valeur du bas)."""
    x, w = np.asarray(x, dtype=float), np.asarray(w, dtype=float)
    i = np.argsort(x)
    c = np.cumsum(w[i])
    k = int(np.searchsorted(c, 0.5 * c[-1]))
    if k + 1 < len(c) and np.isclose(c[k], 0.5 * c[-1]):
        return 0.5 * (x[i][k] + x[i][k + 1])
    return x[i][k]


def correlation(f, o, K, eps):
    """Correlation (ponderee par l'echeance) AROME / mediane horaire mesuree, sur les episodes."""
    p = paires_horaires(f, o, K, eps)
    return (wcorr(p.prevu, p.mesure, p.poids) if len(p) >= 3 else np.nan), len(p)


CALIBRATION_MIN_HEURES = 10     # heures comparees minimum pour recalibrer
CALIBRATION_FACTEUR = 10        # rapports entre K cherches a x/÷ ce facteur des valeurs de reference
# La recalibration par correlation seule degrade le niveau et l'amplitude
# (constat du 06/10) : les K recales sont notes dans le JSON mais pas traces.
AFFICHER_K_RECALES = False     # K recales (erreur relative) notes dans le JSON, non traces
# Jeu de K trace : "K_new" (nouveaux K, retenu par l'utilisateur le 07/10),
# "K_recal" (recales), "K_script", ou "meilleure_correlation". Si "K_recal" est
# choisi mais n'existe pas pour un site, le site retombe sur K_new.
K_AFFICHES = "K_new"
NOMS_K = {"K_script": "K script", "K_new": "nouveaux K", "K_recal": "K recales"}


CALIBRATION_MARGE = 100         # chaque K cherche entre K0/MARGE et K0*MARGE


def coefficients(nom):
    """
    Jeu de K a utiliser pour un site : K_AFFICHES ; pour "K_recal", la derniere
    recalibration enregistree dans COEFF_FILE, sinon K_new.
    """
    cfg = SITES[nom]
    if K_AFFICHES != "K_recal":
        return K_AFFICHES, cfg[K_AFFICHES]
    if cfg.get("K_recal"):
        return "K_recal", cfg["K_recal"]
    if COEFF_FILE.exists():
        for entree in reversed(json.loads(COEFF_FILE.read_text(encoding="utf-8"))):
            s = entree.get("sites", {}).get(nom)
            if s and entree.get("methode") == "erreur relative":
                return "K_recal", (s["K_TKE"], s["K_CIS"], s["K_TKE_CONV"])
    return "K_new", cfg["K_new"]


def calibrate(f, o, eps, K0):
    """
    Recalibration (methode du 07/10) : minimise l'erreur relative ponderee par
    l'echeance, sqrt(sum w log(prevu/mesure)^2 / sum w), sur toutes les heures
    comparees. K_TKE, K_CIS et K_TKE_CONV sont cherches independamment, chacun
    entre K0/CALIBRATION_MARGE et K0*CALIBRATION_MARGE (grille logarithmique).
    K_TKE_CONV n'est cherche que si la convection a joue sur ces heures.
    (La contrainte K_TKE >= K_TKE_CONV du 07/10 a ete supprimee le 09/10, a la demande de l'utilisateur.)
    Retourne (K, correlation ponderee, n_heures, bornes) ou None.
    """
    th, mh, _ = hourly_median(o, stats=True)
    med = pd.Series(mh, index=th)
    dans = np.zeros(len(med), dtype=bool)
    for a, b in eps:
        dans |= (med.index >= a) & (med.index <= b)
    comp = f.set_index("t")[["I_tke", "I_conv", "I_cis", "has_tke", "h"]]
    x = comp.join(med[dans].rename("mesure"), how="inner").dropna()
    x = x[x.has_tke.astype(bool)]
    x = x[masque_sequences(x.index, heures_libres(o))]
    if len(x) < CALIBRATION_MIN_HEURES:
        return None
    w = poids(x.h.values)
    conv = (x.I_conv > 0).sum() >= 3
    echelle = np.logspace(-np.log10(CALIBRATION_MARGE), np.log10(CALIBRATION_MARGE), 49)
    kts, kcs = K0[0] * echelle, K0[1] * echelle
    kvs = K0[2] * echelle[::2] if conv else np.array([K0[2]])
    KT, KC = np.meshgrid(kts, kcs, indexing="ij")
    mes = x.mesure.values
    best = (np.inf, None)
    for kv in kvs:
        I = KT[..., None] * x.I_tke.values + kv * x.I_conv.values + KC[..., None] * x.I_cis.values
        s = seeing_arcsec(I.reshape(-1, len(x))).reshape(I.shape)
        err = np.sqrt(np.nansum(w * np.log(s / mes) ** 2, axis=2) / w.sum())
        i = np.unravel_index(np.nanargmin(err), err.shape)
        if err[i] < best[0]:
            best = (err[i], (KT[i], KC[i], kv), i)
    if best[1] is None:
        return None
    K = tuple(round(float(k), 3) for k in best[1])
    s = seeing_arcsec(K[0] * x.I_tke + K[2] * x.I_conv + K[1] * x.I_cis)
    bornes = [nom for nom, k, grille in (("K_TKE", K[0], kts), ("K_CIS", K[1], kcs), ("K_TKE_CONV", K[2], kvs))
              if len(grille) > 1 and (np.isclose(k, grille[0]) or np.isclose(k, grille[-1]))]
    return K, wcorr(s, mes, w), len(x), bornes


def calibrate_correlation(f, o, eps, K0):
    """
    Recalibration sur toutes les heures comparees (AROME vs mediane horaire) :
    1) rapports K_CIS/K_TKE et K_TKE_CONV/K_TKE qui maximisent la correlation
       (la correlation ne depend pas du niveau global) ;
    2) niveau global tel que la mediane de log(AROME/mesure) soit nulle.
    K_TKE_CONV n'est recale que si la convection a joue sur ces heures.
    Retourne (K, correlation, n_heures) ou None si pas assez d'heures.
    """
    th, mh, _ = hourly_median(o, stats=True)
    med = pd.Series(mh, index=th)
    dans = np.zeros(len(med), dtype=bool)
    for a, b in eps:
        dans |= (med.index >= a) & (med.index <= b)
    comp = f.set_index("t")[["I_tke", "I_conv", "I_cis", "has_tke", "h"]]
    x = comp.join(med[dans].rename("mesure"), how="inner").dropna()
    x = x[x.has_tke.astype(bool)]
    w = poids(x.h)
    if len(x) < CALIBRATION_MIN_HEURES:
        return None
    conv = (x.I_conv > 0).sum() >= 3
    # Recherche limitee a un facteur CALIBRATION_FACTEUR autour des rapports de
    # K0 : sans cette limite, maximiser la seule correlation sur quelques
    # dizaines d'heures pousse les rapports aux extremes (modele degenere).
    r_cis = (K0[1] / K0[0]) * np.logspace(-1, 1, 41) ** np.log10(CALIBRATION_FACTEUR)
    r_conv = ((K0[2] / K0[0]) * np.logspace(-1, 1, 21) ** np.log10(CALIBRATION_FACTEUR)) if conv \
        else np.array([K0[2] / K0[0]])
    best = (-np.inf, None)
    for rc in r_cis:
        for rv in r_conv:
            s = seeing_arcsec(x.I_tke + rv * x.I_conv + rc * x.I_cis)
            ok = np.isfinite(s)
            if ok.sum() < 3 or np.std(s[ok]) == 0:
                continue
            c = wcorr(s[ok], x.mesure.values[ok], w[ok])
            if c > best[0]:
                best = (c, (rc, rv))
    if best[1] is None:
        return None
    rc, rv = best[1]
    s1 = seeing_arcsec(x.I_tke + rv * x.I_conv + rc * x.I_cis)       # K_TKE = 1
    ok = np.isfinite(s1)
    m = wmedian(np.log(s1[ok] / x.mesure.values[ok]), w[ok])
    k_tke = float(np.exp(-m / 0.6))                                    # seeing ~ K^(3/5)
    K = (round(k_tke, 3), round(k_tke * rc, 3), round(k_tke * rv, 3))
    bornes = []
    if rc in (r_cis[0], r_cis[-1]):
        bornes.append("K_CIS/K_TKE")
    if conv and rv in (r_conv[0], r_conv[-1]):
        bornes.append("K_TKE_CONV/K_TKE")
    return K, best[0], len(x), bornes


# 09/10 (demande utilisateur) : FACTEUR D'ECHELLE pour ces sites. La prevision affichee est multipliee par le
# facteur qui annule l'ecart moyen (moyenne geometrique ponderee de mesure/prevu), recalcule a chaque figure.
# Copernic : sa mesure ne semble pas a la meme echelle que les autres moniteurs. La correlation ne change pas.
FACTEUR_ECHELLE_SITES = set()   # 09/10 : facteur d'echelle de Copernic retire (demande utilisateur) ; {"Copernic"} pour le remettre


def facteur_echelle(nom, p):
    """Facteur multiplicatif applique a la prevision (1 si le site n'est pas concerne)."""
    if nom not in FACTEUR_ECHELLE_SITES or p is None or len(p) < 3:
        return 1.0
    return float(np.exp(np.average(np.log(p.mesure / p.prevu), weights=p.poids)))


HISTORIQUE_NUIT_SEULE = True   # 17/10 (utilisateur) : journees retirees de la figure historique (nuits 17h30-06h TU seulement)


def nuits_seules(eps, o):
    """Coupe les periodes a la nuit ; garde les morceaux qui ont encore une sequence de mesures valable."""
    out = []
    for a, b in eps:
        fine = pd.date_range(a, b, freq="10min")
        for na, nb in intervals(fine[est_nuit(fine)], 0.5):
            if len(filtre_sequences(o[(o.t >= na) & (o.t <= nb)])):
                # 18/10 : +/- 30 min (dans la periode) pour garder la mediane horaire de bord (mesures de 22h30-23h -> heure 23h)
                s, e = na - pd.Timedelta(minutes=30), nb + pd.Timedelta(minutes=30)
                s = s if est_nuit(pd.DatetimeIndex([s.round("1h")]))[0] else na     # pas d'heure de jour (17h, 06h) ajoutee
                e = e if est_nuit(pd.DatetimeIndex([e.round("1h")]))[0] else nb
                out.append((max(a, s), min(b, e)))
    return out


def plot_compresse(ax, nom, cfg, f, o):
    eps = episodes(f, o)
    if HISTORIQUE_NUIT_SEULE:
        eps = nuits_seules(eps, o)
    if not eps:
        ax.text(0.5, 0.5, "Aucune periode avec previsions et mesures", transform=ax.transAxes, ha="center")
        return 0, None
    axe = AxeCompresse(eps)
    th, mh, _ = hourly_median(o)
    cles = [k for k in NOMS_K if cfg.get(k) and (k != "K_recal" or AFFICHER_K_RECALES)]
    candidats = {key: correlation(f, o, cfg[key], eps) for key in cles}
    if K_AFFICHES in candidats:
        best = K_AFFICHES
    elif K_AFFICHES == "K_recal" and "K_new" in candidats:
        best = "K_new"
    else:
        best = max(candidats, key=lambda k: -np.inf if np.isnan(candidats[k][0]) else candidats[k][0])
    series = [(best, COULEUR_AROME, "-", NOMS_K[best])]
    v1m = v1() if TRACER_V1 else None
    f1 = forecasts_v1_site(v1m, nom) if v1m else None
    autres = autres_modeles(nom)   # 15/10 : V2 d'origine et V2b superposees (chacune ses K)
    v1_trace = False
    fac2 = facteur_echelle(nom, paires_horaires(f, o, cfg[best], eps))
    e1 = episodes(f1, o) if f1 is not None else []
    fac1 = facteur_echelle(nom, paires_horaires(f1, o, K_V1[nom], e1, v1m)) if e1 else 1.0
    suf2 = f" x {fac2:.2f} (facteur d'echelle)" if fac2 != 1 else ""
    suf1 = f" x {fac1:.2f} (facteur d'echelle)" if fac1 != 1 else ""
    ticks, labels, haut = [], [], 0
    for i, (a, b) in enumerate(eps):
        first = i == 0
        fine = pd.date_range(a, b, freq="10min")
        nuit = est_nuit(fine)
        ax.fill_between(axe.x(fine, i), 0, 1, where=nuit, transform=ax.get_xaxis_transform(),
                        color=COULEUR_NUIT, lw=0, zorder=0)
        # regle des 3 heures successives reappliquee DANS la periode affichee (une coupure de la
        # periode ne doit pas laisser de bout de 1-2 points horaires)
        oo = filtre_sequences(o[axe.masque(o.t, i)])
        # 14/10 : mesures non utilisees par le calage (jour, hors plage) en gris
        trace_mesures(ax, nom, oo.t, oo.seeing, x=axe.x(oo.t, i), par_heure=True, lw=0, marker="o", ms=1.8, alpha=0.3,
                      label=f"Mesures brutes" if first else None)
        th_i, mh_i, _ = hourly_median(oo)
        if len(mh_i):
            haut = max(haut, np.nanmax(mh_i))   # echelle : medianes horaires et previsions, pas les mesures brutes
        hors_h = non_cale(nom, th_i, mh_i)
        ax.plot(axe.x(th_i, i), np.where(hors_h, np.nan, mh_i), color=COULEUR_MESURES, lw=1.6, marker="s", ms=4,
                label=f"Mediane horaire (>= {HORAIRE_MIN_POINTS} mesures)" if first else None)
        if np.any(hors_h):
            ax.plot(axe.x(th_i, i), np.where(hors_h, mh_i, np.nan), color=COULEUR_NON_CALE, lw=1.6, marker="s", ms=4,
                    label="Mesures non utilisees pour le calage (jour, hors plage)" if first else None)
        mf = axe.masque(f.t, i)
        for key, color, ls, lab in series:
            k = cfg[key]
            s = arome(f, k)[1][mf] * fac2
            haut = max(haut, np.nanmax(s) if np.any(np.isfinite(s)) else 0)
            ax.plot(axe.x(f.t[mf], i), s, color=color, ls=ls, lw=1.6, marker="o", ms=3,
                    label=f"AROME {nom_v2()} ({lab}, voir encadre){suf2}" if first else None)
            grise_previsions(ax, f.t[mf], s, heures_hors_plage(nom, th_i, mh_i), x=axe.x(f.t[mf], i))
        for mod_a, coul_a, fa_, Ka in autres:   # 15/10 : autres variantes, chacune avec ses K
            m0 = axe.masque(fa_.t, i)
            if m0.any():
                s0 = arome(fa_, Ka)[1][m0] * fac2
                ax.plot(axe.x(fa_.t[m0], i), s0, color=coul_a, ls=":", lw=1.4, marker=".", ms=3,
                        label=f"AROME {mod_a} (ses K)" if first else None)
        if f1 is not None:
            m1 = axe.masque(f1.t, i)
            if m1.any():
                s1 = seeing_v1_k(v1m, f1, K_V1[nom])[m1] * fac1
                haut = max(haut, np.nanmax(s1) if np.any(np.isfinite(s1)) else 0)
                ax.plot(axe.x(f1.t[m1], i), s1, color=COULEUR_V1, ls="--", lw=1.4, marker="^", ms=3,
                        label=None if v1_trace else f"AROME V1 (sans convection){suf1}")
                grise_previsions(ax, f1.t[m1], s1, heures_hors_plage(nom, th_i, mh_i), x=axe.x(f1.t[m1], i), marker="^")
                v1_trace = True
        # graduation a chaque heure ; heure ecrite aux heures paires, date a 00 h
        for h in pd.date_range(a.ceil("1h"), b, freq="1h"):
            ticks.append(axe.x([h], i)[0])
            labels.append("" if h.hour % 2 else (f"{h:%d/%m %Hh}" if h.hour == 0 else f"{h:%Hh}"))
        ax.text(axe.x([a], i)[0], 1.0, f" {a:%d/%m}", transform=ax.get_xaxis_transform(),
                fontsize=9, fontweight="bold", va="top", color="#0b0b0b")
        if i > 0:
            xs = axe.x([a], i)[0] - ECART_EPISODES_H / 2
            for dx in (-0.12, 0.12):
                ax.axvline(xs + dx, color="#52514e", lw=0.9)
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, fontsize=7, rotation=90)
    ax.set_xlim(-0.3, axe.x0[-1] + (eps[-1][1] - eps[-1][0]) / pd.Timedelta(hours=1) + 0.3)
    corr_v1 = None
    if v1_trace:
        p1 = paires_horaires(f1, o, K_V1[nom], eps, v1m)
        corr_v1 = (wcorr(p1.prevu, p1.mesure, p1.poids) if len(p1) >= 3 else np.nan, len(p1))
    return haut, (best, candidats, v1_trace, corr_v1)


OUTPUT_CORR = OUTPUT.with_name("correlation_sites.png")
OUTPUT_CORR_V2 = OUTPUT.with_name("correlation_sites_V2.png")
COULEURS_PERIODES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]


def paires_horaires(f, o, K, eps, v1m=None):
    """AROME et mediane horaire mesuree aux memes heures, avec la periode de chaque heure.
    v1m : module seeing_v1_sites -> f et K sont ceux du modele V1."""
    th, mh, _ = hourly_median(o, stats=True)
    med = pd.Series(mh, index=th)
    prevu = seeing_v1_k(v1m, f, K) if v1m else arome(f, K)[1]
    s = pd.DataFrame({"prevu": prevu, "echeance_h": f.h.values}, index=f.t)
    out = []
    for a, b in eps:
        m = med[(med.index >= a) & (med.index <= b)].rename("mesure")
        p = s.join(m, how="inner").dropna()
        out.append(p.assign(periode=f"{a:%d/%m %Hh}"))
    cols = ["prevu", "echeance_h", "mesure", "periode", "poids"]
    if not out:
        return pd.DataFrame(columns=cols)
    p = pd.concat(out)
    p = p[masque_sequences(p.index, heures_libres(o))]
    p["poids"] = poids(p.echeance_h)
    return p


DEMI_PERIODE_MIN_HEURES = 2     # heures comparees minimum dans une (demi-)nuit / (demi-)journee
TAILLE_POINTS = 40              # 08/10 : tous les points horaires a la meme taille (le poids reste dans les stats)
COUPER_EN_DEUX = False         # 08/10 : un point par nuit et par journee (True : deux par nuit et par journee)
COUPER_EN_DEUX_SITES = set()   # 15/10 soir : essai Drome annule (utilisateur : "je me suis trompe")


def demi_periodes(p, nom):
    """
    Medianes (ponderees par l'echeance) prevu / mesure par demi-nuit et demi-journee :
    chaque nuit (est_nuit : 17h30-06h00 TU) et chaque journee est coupee en deux a
    son milieu, soit 4 points par 24 h. Colonnes : nuit, mesure, prevu, heures.
    """
    if len(p) == 0:
        return pd.DataFrame(columns=["nuit", "mesure", "prevu", "heures"])
    lat, lon = COORDS[nom]
    t = pd.DatetimeIndex(p.index)
    fine = pd.date_range(t.min().floor("D") - pd.Timedelta(days=1), t.max().ceil("D") + pd.Timedelta(days=1), freq="5min")
    nuit = est_nuit(fine)
    seg = np.r_[0, np.cumsum(nuit[1:] != nuit[:-1])]
    debut = pd.Series(fine).groupby(seg).min()
    fin = pd.Series(fine).groupby(seg).max()
    i = np.clip(fine.searchsorted(t), 0, len(fine) - 1)
    s = seg[i]
    milieu = (debut[s].values + (fin[s].values - debut[s].values) / 2)
    moitie = (t.values >= milieu).astype(int) if (COUPER_EN_DEUX or nom in COUPER_EN_DEUX_SITES) else np.zeros(len(t), dtype=int)
    cle = pd.DataFrame({"seg": s, "moitie": moitie, "nuit": nuit[i]}, index=p.index)
    rows = []
    for (_, _, n), g in cle.groupby(["seg", "moitie", "nuit"]):
        q = p.loc[g.index]
        if len(q) >= DEMI_PERIODE_MIN_HEURES:
            rows.append({"nuit": bool(n), "mesure": wmedian(q.mesure, q.poids), "prevu": wmedian(q.prevu, q.poids),
                         "heures": len(q)})
    return pd.DataFrame(rows, columns=["nuit", "mesure", "prevu", "heures"])


COULEUR_SOLEIL = "#e34948"      # rouge : jour, figure V2 seule (08/10, choix utilisateur)
COULEUR_LUNE = COULEUR_AROME    # bleu : nuit, figure V2 seule


def trace_demi_periodes(ax, d, couleur, nom_modele, couleur_soleil=None, couleur_lune=None):
    """Gros soleils (journees) et lunes (nuits) sur le nuage de correlation."""
    demi = "demi-" if COUPER_EN_DEUX else ""
    for nuit, symbole, lab in ((False, "$☼$", f"{demi}journee"), (True, "$☾$", f"{demi}nuit")):   # soleil creux, lune
        q = d[d.nuit == nuit]
        if len(q):
            if not nuit:   # fond sous le soleil creux : les points horaires ne se voient pas au travers
                ax.scatter(q.mesure, q.prevu, s=230, marker="o", color="#fcfcfb", linewidth=0, zorder=9)
            c = (couleur_lune if nuit else couleur_soleil) or couleur
            ax.scatter(q.mesure, q.prevu, s=520, marker=symbole, color=c, edgecolor=c, linewidth=0.2,
                       zorder=11 if nuit else 10,   # lunes (nuit) devant les soleils (jour)
                       label=f"{nom_modele} : mediane par {lab} ({len(q)})")


def texte_r_nuit_jour(p):
    """11/10 (demande utilisateur) : correlations nuit et jour separees, affichees sur les figures de correlation."""
    out = []
    for lab, m in (("nuit", est_nuit(p.index)), ("jour", ~est_nuit(p.index))):
        q = p[m]
        r = wcorr(q.mesure, q.prevu, q.poids) if len(q) > 2 else np.nan
        out.append(f"r {lab} = {r:+.2f} ({len(q)} h)" if np.isfinite(r) else f"r {lab} = -- ({len(q)} h)")
    return "   " + "   |   ".join(out)


CORR_NUIT_MIN_HEURES = 1   # 13/10 : regle des nuits de moins de 3 h ANNULEE (toutes les heures et nuits) ; 3 = la remettre
SEGMENTS_MIN_HEURES = {}   # 14/10 soir (utilisateur) : toutes les donnees, aucune portion retiree ; avant {n: 4 for n in SITES}
DEUX_MEDIANES = {"Cosmodrome"}   # 15/10 (utilisateur) : calage sur par les medianes des deux moities de la periode mesuree
SEUIL_MESURE_MAX = {"Cosmodrome": 5.0}   # 15/10 (utilisateur) : mesures > 5" retirees
CALAGE_DEUX_MEDIANES = False   # 15/10 : True dans les scripts de calage ; figures = mesures brutes
SANS_MEDIANE_AFFICHEE = {"Cosmodrome"}   # 15/10 (utilisateur) : figures avec les mesures brutes seulement, aucune mediane tracee
SANS_REGLE_3H = {"Cosmodrome"}   # 15/10 (utilisateur) : seules mesures du site (51 min) -> gardees malgre la regle des 3 h
CORR_NUIT_MIN_CONSECUTIVES = 3   # 15/10 (utilisateur) : REMISE (nuits sans au moins 3 h consecutives retirees) ; 14/10 soir : annulee - 14/10 (utilisateur) : nuits sans au moins 3 h comparees consecutives retirees (correlation et calage) ; 1 = annuler


def hors_plage_prevue(nom, p):
    """(heures gardees, heures exclues) selon PLAGE_PREVUE (prevision AROME hors de la plage mesurable du monitor)."""
    if p is None or not len(p) or (nom not in PLAGE_PREVUE and nom not in PLAGE_MESURE and nom not in PLAGE_PREVISION):
        return p, (p.iloc[:0] if p is not None else p)
    hors = _hors_plages(nom, p)
    return p[~hors], p[hors]


def _hors_plages(nom, d):
    """Masque des lignes exclues : PLAGE_PREVUE (mesure ou prevision hors plage) et PLAGE_MESURE (mesure seule)."""
    hors = pd.Series(False, index=d.index)
    if nom in PLAGE_PREVUE:
        lo, hi = PLAGE_PREVUE[nom]
        hors |= (d.prevu < lo) | (d.prevu > hi) | (d.mesure < lo) | (d.mesure > hi)
    if nom in PLAGE_MESURE:
        lo, hi = PLAGE_MESURE[nom]
        hors |= (d.mesure < lo) | (d.mesure > hi)
    if nom in PLAGE_PREVISION:
        lo, hi = PLAGE_PREVISION[nom]
        hors |= (d.prevu < lo) | (d.prevu > hi)
    return hors.to_numpy()


COULEUR_NON_CALE = "#a9a8a3"   # 14/10 : mesures non utilisees pour le calage (jour, hors plage) en gris sur les series


NUITS_HORS_CALAGE = {}   # 18/10 (utilisateur) : monitor 5 cale sans les 2 nuits les plus au-dessus de la droite ; 17/10 monitor 5 sans 02, 08, 10, 13/10 -   # 17/10 (utilisateur) : nuits (date du soir) retirees du calage du 5, en gris sur les figures


def non_cale(nom, t, v, med=None):
    """True pour les mesures NON utilisees par le calage : hors nuit (17h30-06h), ou hors PLAGE_MESURE du site
    (valeur elle-meme, ou mediane horaire med de son heure)."""
    t = pd.DatetimeIndex(t); v = np.asarray(v, float)
    hors = ~est_nuit(t)
    if nom in NUITS_HORS_CALAGE:   # 17/10 : nuits retirees du calage (affichees en gris)
        hors |= (t - pd.Timedelta(hours=12)).normalize().isin(pd.DatetimeIndex(NUITS_HORS_CALAGE[nom]))
    if nom in PLAGE_MESURE:
        lo, hi = PLAGE_MESURE[nom]
        hors |= (v < lo) | (v > hi)
        if med is not None:
            med = np.asarray(med, float); hors |= (med < lo) | (med > hi)
    return hors


def heures_hors_plage(nom, th, mh):
    """Heures dont la mediane mesuree est hors PLAGE_MESURE (exclues avec leur prevision AROME)."""
    th = pd.DatetimeIndex(th); out = pd.DatetimeIndex([])
    if not len(th):
        return out
    if nom in NUITS_HORS_CALAGE:   # 17/10 : heures des nuits retirees du calage
        out = out.union(th[(th - pd.Timedelta(hours=12)).normalize().isin(pd.DatetimeIndex(NUITS_HORS_CALAGE[nom]))])
    if nom in PLAGE_MESURE:
        lo, hi = PLAGE_MESURE[nom]; mh = np.asarray(mh, float)
        out = out.union(th[(mh < lo) | (mh > hi)])
    return out


def grise_previsions(ax, t, s, exclues, x=None, marker="o", ms=4.5):
    """Previsions AROME des heures exclues (mesure hors plage) recouvertes en gris."""
    t = pd.DatetimeIndex(t); m = t.isin(exclues)
    if m.any():
        ax.plot(np.asarray(t if x is None else x)[m], np.asarray(s, float)[m], lw=0, marker=marker, ms=ms, color=COULEUR_NON_CALE, zorder=12)


def trace_mesures(ax, nom, t, v, x=None, **kw):
    """Mesures en orange (utilisees par le calage) et en gris (non utilisees) ; kw communs, label sur la partie orange."""
    t = pd.DatetimeIndex(t); v = np.asarray(v, float); x = t if x is None else x
    med = pd.Series(v, index=t).groupby(t.round("1h")).transform("median").values if kw.pop("par_heure", False) else None
    hors = non_cale(nom, t, v, med)
    lab = kw.pop("label", None); couleur = kw.pop("color", COULEUR_MESURES)
    ax.plot(np.asarray(x)[~hors], v[~hors], color=couleur, label=lab, **kw)
    if hors.any():
        ax.plot(np.asarray(x)[hors], v[hors], color=COULEUR_NON_CALE, **kw)
    return hors


def texte_plage(nom):
    if nom in PLAGE_PREVISION:
        return "prevision AROME hors {:g}-{:g}\"".format(*PLAGE_PREVISION[nom])
    if nom in PLAGE_MESURE:
        return "mesure hors {:g}-{:g}\"".format(*PLAGE_MESURE[nom])
    if nom in PLAGE_PREVUE:
        return "prevision hors {:g}-{:g}\"".format(*PLAGE_PREVUE[nom])
    return ""


def brutes_dans_plage(nom, bru):
    """Mesures brutes gardees / exclues : TOUTES les valeurs (mesure ou prevision a l'instant de la mesure) hors de
    PLAGE_PREVUE sont exclues (13/10, demande utilisateur : pas seulement les heures)."""
    if bru is None or not len(bru) or (nom not in PLAGE_PREVUE and nom not in PLAGE_MESURE and nom not in PLAGE_PREVISION):
        return bru, (bru.iloc[:0] if bru is not None else bru)
    hors = _hors_plages(nom, bru)
    return bru[~hors], bru[hors]


def sans_nuits_courtes(p, nom=None):
    """Retire les heures des nuits (17h30-06h, rattachees au soir) qui ont moins de CORR_NUIT_MIN_HEURES heures comparees.
    Les heures de jour ne sont pas touchees. Sites de SEGMENTS_MIN_HEURES : chaque portion d'heures successives plus courte
    que N heures est retiree (meme dans une nuit qui a une longue portion)."""
    if p is None or not len(p):
        return p
    if nom in SEGMENTS_MIN_HEURES:
        t = pd.Series(p.index, index=p.index).sort_values()
        bloc = (t.diff() != pd.Timedelta(hours=1)).cumsum()
        p = p.loc[t.index[(bloc.map(bloc.value_counts()) >= SEGMENTS_MIN_HEURES[nom]).values]].sort_index()
        if not len(p):
            return p
    nt = est_nuit(p.index)
    cle = pd.Series((p.index - pd.Timedelta(hours=12)).normalize(), index=p.index).where(nt)
    n = cle.map(cle.value_counts())
    garde = ~nt | (n >= CORR_NUIT_MIN_HEURES).values
    if CORR_NUIT_MIN_CONSECUTIVES > 1 and nom not in SANS_REGLE_3H:      # 14/10 : la nuit doit avoir au moins N heures comparees CONSECUTIVES
        t = pd.Series(p.index[nt], index=p.index[nt]).sort_values()
        bloc = (t.diff() != pd.Timedelta(hours=1)).cumsum()
        plus_long = bloc.map(bloc.value_counts()).groupby(cle[nt].reindex(t.index).values).max()
        ok = cle.map(plus_long) >= CORR_NUIT_MIN_CONSECUTIVES
        garde &= (~nt | ok.values)
    return p[garde]


ECHELLE_CORR = 10.0  # 13/10 : axes des figures de correlation fixes de 0 a 10" (None = automatique)
TAILLE_BRUTES = 7    # 11/10 : mesures brutes sur les figures de correlation, plus petites que les medianes horaires


def texte_r_echelles(bru, p):
    """12/10 (demande utilisateur) : correlation a trois echelles - mesures brutes (face a la courbe prevue),
    medianes horaires, medianes par nuit / par journee (nuit = 17h30-06h, rattachee au soir)."""
    def r(a, b):
        return np.corrcoef(a, b)[0, 1] if len(a) > 2 else np.nan
    if p is None or not len(p):
        return ""
    nt = est_nuit(p.index)
    cle = np.where(nt, (p.index - pd.Timedelta(hours=12)).normalize().strftime("%Y-%m-%d N"),
                   p.index.normalize().strftime("%Y-%m-%d J"))
    g = p.groupby(cle).agg(prevu=("prevu", "median"), mesure=("mesure", "median"), n=("mesure", "size"))
    g = g[g.n >= DEMI_PERIODE_MIN_HEURES]   # memes nuits / journees que les lunes et soleils traces
    rb, rh, rn = r(bru.mesure, bru.prevu) if len(bru) else np.nan, r(p.mesure, p.prevu), r(g.mesure, g.prevu)
    f = lambda v: f"{v:+.2f}" if np.isfinite(v) else "--"
    return f"   R brut = {f(rb)} ({len(bru)} mes.)  |  R heures = {f(rh)} ({len(p)} h)  |  R nuits = {f(rn)} ({len(g)})"


def mesures_brutes(o, p, f, K, v1m=None, fac=1.0):
    """Mesures brutes des heures comparees, chacune face a la COURBE de prevision a son instant exact
    (11/10, demande utilisateur : interpolation lineaire entre deux echeances horaires consecutives,
    jamais a travers un trou de plus d'une heure)."""
    if p is None or not len(p):
        return pd.DataFrame(columns=["mesure", "prevu"])
    b = o.assign(h=o.t.dt.round("1h"))
    b = b[b.h.isin(p.index)]
    s = pd.Series(np.asarray(seeing_v1_k(v1m, f, K) if v1m else arome(f, K)[1], dtype=float) * fac,
                  index=pd.DatetimeIndex(f.t)).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    x = s.index.values.astype("int64"); y = s.values
    tb = b.t.values.astype("int64")
    i = np.clip(np.searchsorted(x, tb), 1, len(x) - 1)
    x0, x1, y0, y1 = x[i - 1], x[i], y[i - 1], y[i]
    ok = (x1 - x0) <= pd.Timedelta(hours=1).value
    prevu = np.where(ok, y0 + (y1 - y0) * (tb - x0) / np.where(x1 > x0, x1 - x0, 1), np.nan)
    prevu = np.where(tb == x0, y0, prevu)
    return pd.DataFrame({"mesure": b.seeing.values, "prevu": prevu}, index=pd.DatetimeIndex(b.t)).dropna()


def plot_correlations(data, choix_par_site, debut=None, fin=None, sortie=None, titre=None, avec_v1=True, nuit_seule=False):
    """
    Nuage prevu / mesure par site. Avec debut/fin : seules les heures de cette
    periode, et le jeu de K retenu est le mieux correle sur cette periode.
    """
    bg = "#fcfcfb"
    sortie = sortie or OUTPUT_CORR
    if debut is not None or fin is not None:
        lo = pd.Timestamp(debut) if debut else pd.Timestamp.min
        hi = pd.Timestamp(fin) if fin else pd.Timestamp.max
        limite = {}
        for nom, (f, o) in data.items():
            eps = [(max(a, lo), min(b, hi)) for a, b in episodes(f, o) if b >= lo and a <= hi]
            limite[nom] = eps
            cfg = SITES[nom]
            cand = {}
            for k in [c for c in ("K_script", "K_new", "K_recal") if cfg.get(c)]:
                p = paires_horaires(f, o, cfg[k], eps) if eps else pd.DataFrame()
                cand[k] = wcorr(p.mesure, p.prevu, p.poids) if len(p) > 2 else -np.inf
            retenu = K_AFFICHES if K_AFFICHES in cand else \
                "K_new" if K_AFFICHES == "K_recal" else max(cand, key=cand.get)
            choix_par_site = {**choix_par_site, nom: retenu} if eps else \
                {k: v for k, v in choix_par_site.items() if k != nom}
    else:
        limite = None
    v1m = v1() if TRACER_V1 and avec_v1 else None
    ncol = 2
    nlig = int(np.ceil(len(SITES) / ncol))
    fig, axes = plt.subplots(nlig, ncol, figsize=(6.6 * ncol, 8.8 * nlig), dpi=110, squeeze=False)
    fig.patch.set_facecolor(bg)
    for ax in axes.flat[len(SITES):]:
        ax.set_visible(False)
    for ax, (nom, cfg) in zip(axes.flat, SITES.items()):
        f, o = data[nom]
        ax.set_facecolor(bg)
        best = choix_par_site.get(nom)
        if f is None or best is None:
            ax.text(0.5, 0.5, "Pas de periode commune", transform=ax.transAxes, ha="center")
            continue
        K = cfg[best]
        p = paires_horaires(f, o, K, limite[nom] if limite is not None else episodes(f, o))
        if nuit_seule:          # 12/10 (demande utilisateur) : figure V2 avec les heures de nuit seulement
            p = p[est_nuit(p.index)]
        p = sans_nuits_courtes(p, nom)
        fac2 = facteur_echelle(nom, p)
        p = p.assign(prevu=p.prevu * fac2)
        p, p_hors = hors_plage_prevue(nom, p)
        if len(p_hors):
            ax.scatter(p_hors.mesure, np.minimum(p_hors.prevu, (ECHELLE_CORR or 99) * 0.99), s=TAILLE_POINTS, color="#b9b8b3",
                       edgecolor=bg, linewidth=1.0, zorder=2.5, label=f"{nom_v2()} : {texte_plage(nom)} (exclue, {len(p_hors)} h)")
        bru = mesures_brutes(o, pd.concat([p, p_hors]).sort_index(), f, K, fac=fac2)
        bru, bru_hors = brutes_dans_plage(nom, bru)
        if len(bru_hors):
            ax.scatter(bru_hors.mesure, np.minimum(bru_hors.prevu, (ECHELLE_CORR or 99) * 0.99), s=TAILLE_BRUTES, color="#b9b8b3",
                       alpha=0.5, lw=0, zorder=1.5, label=f"{nom_v2()} : brutes exclues, {texte_plage(nom)} ({len(bru_hors)})")
        if avec_v1:
            ax.scatter(bru.mesure, bru.prevu, s=TAILLE_BRUTES, color=COULEUR_AROME, alpha=0.35, lw=0,
                       label=f"{nom_v2()} : mesures brutes ({len(bru)})", zorder=2)
        else:
            nb = est_nuit(bru.index)
            for m, c, lab in ((~nb, COULEUR_SOLEIL, "jour"), (nb, COULEUR_LUNE, "nuit")):
                if m.any():
                    ax.scatter(bru.mesure[m], bru.prevu[m], s=TAILLE_BRUTES, color=c, alpha=0.35, lw=0,
                               label=f"{nom_v2()} : mesures brutes de {lab} ({m.sum()})", zorder=2)
        if avec_v1:
            ax.scatter(p.mesure, p.prevu, s=TAILLE_POINTS, color=COULEUR_AROME, edgecolor=bg, linewidth=1.0,
                       label=f"{nom_v2()} : heures comparees ({len(p)})", zorder=3)
        else:   # figure V2 seule : heures de jour en jaune, de nuit en bleu
            nuit = est_nuit(p.index)
            for m, c, lab in ((~nuit, COULEUR_SOLEIL, "jour"), (nuit, COULEUR_LUNE, "nuit")):
                if m.any():
                    ax.scatter(p.mesure[m], p.prevu[m], s=TAILLE_POINTS, color=c, edgecolor=bg, linewidth=1.0,
                               label=f"{nom_v2()} : heures de {lab} ({m.sum()})", zorder=3)
        lim = max(p.prevu.max(), p.mesure.max()) * 1.08
        trace_demi_periodes(ax, demi_periodes(p, nom), COULEUR_AROME, nom_v2(),
                            couleur_soleil=None if avec_v1 else COULEUR_SOLEIL,
                            couleur_lune=None if avec_v1 else COULEUR_LUNE)
        r = wcorr(p.mesure, p.prevu, p.poids) if len(p) > 2 else np.nan
        e = p.prevu - p.mesure
        titre_site = (f"{nom}\n{nom_v2()} {texte_K(K)}" + (f"   x {fac2:.2f} (echelle)" if fac2 != 1 else "") + "\n"
                      f"   r = {r:+.2f}   n = {len(p)} h   biais {np.average(e, weights=p.poids):+.2f}\"   "
                      f"ecart moyen {np.average(e.abs(), weights=p.poids):.2f}\"\n" + texte_r_nuit_jour(p))
        cadre_r = [nom_v2() + " " + texte_r_echelles(bru, p).strip()]
        # Modele V1 en rouge, sur les heures ou il a ete calcule
        f1 = forecasts_v1_site(v1m, nom) if v1m else None
        if f1 is not None:
            eps1 = episodes(f1, o)
            if limite is not None:
                eps1 = [(max(a, lo), min(b, hi)) for a, b in eps1 if b >= lo and a <= hi]
            p1 = paires_horaires(f1, o, K_V1[nom], eps1, v1m) if eps1 else pd.DataFrame()
            fac1 = facteur_echelle(nom, p1) if len(p1) else 1.0
            if len(p1):
                p1 = sans_nuits_courtes(p1.assign(prevu=p1.prevu * fac1), nom)
                p1, p1_hors = hors_plage_prevue(nom, p1)
                if len(p1_hors):
                    ax.scatter(p1_hors.mesure, np.minimum(p1_hors.prevu, (ECHELLE_CORR or 99) * 0.99), s=TAILLE_POINTS, color="#b9b8b3",
                               edgecolor=bg, linewidth=1.0, marker="^", zorder=2.5, label=f"V1 : {texte_plage(nom)} (exclue, {len(p1_hors)} h)")
                bru1 = mesures_brutes(o, pd.concat([p1, p1_hors]).sort_index(), f1, K_V1[nom], v1m, fac1)
                bru1, bru1_hors = brutes_dans_plage(nom, bru1)
                if len(bru1_hors):
                    ax.scatter(bru1_hors.mesure, np.minimum(bru1_hors.prevu, (ECHELLE_CORR or 99) * 0.99), s=TAILLE_BRUTES, color="#b9b8b3",
                               alpha=0.5, lw=0, marker="^", zorder=1.5)
                ax.scatter(bru1.mesure, bru1.prevu, s=TAILLE_BRUTES, color=COULEUR_V1_CORR, alpha=0.35, lw=0,
                           marker="^", label=f"V1 : mesures brutes ({len(bru1)})", zorder=2)
                ax.scatter(p1.mesure, p1.prevu, s=TAILLE_POINTS, color=COULEUR_V1_CORR, edgecolor=bg,
                           linewidth=1.0, marker="^", label=f"V1 : heures comparees ({len(p1)})", zorder=4)
                lim = max(lim, max(p1.prevu.max(), p1.mesure.max()) * 1.08)
                trace_demi_periodes(ax, demi_periodes(p1, nom), COULEUR_V1_CORR, "V1")
                r1 = wcorr(p1.mesure, p1.prevu, p1.poids) if len(p1) > 2 else np.nan
                e1 = p1.prevu - p1.mesure
                titre_site += (f"\nV1 {texte_K_v1(K_V1[nom])}" + (f"   x {fac1:.2f} (echelle)" if fac1 != 1 else "") + "\n"
                               f"   r = {r1:+.2f}   n = {len(p1)} h   biais {np.average(e1, weights=p1.poids):+.2f}\"   "
                               f"ecart moyen {np.average(e1.abs(), weights=p1.poids):.2f}\"\n" + texte_r_nuit_jour(p1))
                cadre_r.append("V1 " + texte_r_echelles(bru1, p1).strip())
        lim = ECHELLE_CORR if ECHELLE_CORR else lim   # 13/10 (demande utilisateur) : echelle fixe 0-10"
        ax.plot([0, lim], [0, lim], color="#52514e", lw=1, ls=":", label="prevu = mesure")
        ax.set_title(titre_site + ("   (ponderes)" if PONDERATION_ECHEANCE else ""), loc="left", fontsize=9.5)
        ax.set_xlim(0, lim); ax.set_ylim(0, lim); ax.set_aspect("equal")
        # 12/10 (demande utilisateur) : correlations brut / horaire / par nuit DANS le diagramme (pas en titre)
        ax.text(0.98, 0.02, "\n".join(l.replace("  |  ", "\n    ") for l in cadre_r), transform=ax.transAxes,
                ha="right", va="bottom", fontsize=10.5, family="monospace", fontweight="bold", zorder=20,
                bbox=dict(boxstyle="round,pad=0.4", facecolor="#fcfcfb", edgecolor="#b9b8b3", alpha=0.92))
        ax.set_xlabel("Seeing mesure [arcsec]\n(gros points : mediane horaire ; petits : mesures brutes / courbe prevue)", fontsize=8.5)
        ax.set_ylabel("Seeing prevu AROME [arcsec]")
        ax.grid(color="#e4e3df", lw=0.8); ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.suptitle((titre or "Correlation seeing prevu / mesure (toutes periodes)")
                 + (f"   -   poids = exp(-echeance / {TAU_POIDS_H} h)" if PONDERATION_ECHEANCE else "   -   heures non ponderees"),
                 x=0.01, y=0.99, ha="left", fontsize=13)
    fig.tight_layout(rect=(0, 0.01, 1, 1 - 0.035 / nlig), h_pad=2.5)   # 11/10 : titres plus longs (r nuit / r jour)
    fig.savefig(sortie, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


# ============================================================================
# FIGURE
# ============================================================================
def main():
    bg = "#fcfcfb"
    data = {nom: (forecasts_site(nom), observations(nom)) for nom in SITES}

    # Recalibration sur toutes les donnees disponibles, avant la figure
    histo = json.loads(COEFF_FILE.read_text(encoding="utf-8")) if COEFF_FILE.exists() else []
    entree = {"date_calcul": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"), "methode": "erreur relative",
              "marge": CALIBRATION_MARGE, "tau_poids_h": TAU_POIDS_H, "sites": {}}
    for nom, cfg in SITES.items():
        f, o = data[nom]
        res = calibrate(f, o, episodes(f, o), cfg["K_new"]) if f is not None else None
        if res:
            K, c, n, bornes = res
            cfg["K_recal"] = K
            entree["sites"][nom] = {"K_TKE": K[0], "K_CIS": K[1], "K_TKE_CONV": K[2],
                                    "correlation": round(float(c), 3), "heures": int(n),
                                    "rapport_en_butee": bornes,
                                    "mesures_jusqu_au": f"{o.t.max():%Y-%m-%d %H:%M}"}
            alerte = f"   ⚠️ en butee : {', '.join(bornes)}" if bornes else ""
            print(f"{nom:12s} recalibre : {texte_K(K)}   (corr {c:+.2f}, {n} heures){alerte}")
        else:
            print(f"{nom:12s} pas de recalibration (moins de {CALIBRATION_MIN_HEURES} heures comparees)")
    histo.append(entree)
    COEFF_FILE.write_text(json.dumps(histo, indent=2, ensure_ascii=False), encoding="utf-8")

    fig, axes = plt.subplots(len(SITES), 1, figsize=(20, 4.2 * len(SITES)), dpi=110)
    fig.patch.set_facecolor(bg)
    choix_par_site = {}
    for ax, (nom, cfg) in zip(axes, SITES.items()):
        f, o = data[nom]
        ax.set_facecolor(bg)
        haut, choix = plot_compresse(ax, nom, cfg, f, o)
        if choix:
            choix_par_site[nom] = choix[0]
        n_ep = len(episodes(f, o))
        txt = ""
        if choix:
            best, cand, _, c1 = choix
            txt = f"   correlation {nom_v2()} {cand[best][0]:+.2f}   [{cand[best][1]} heures]"
            if c1 and c1[1] >= 3:
                txt += f"   |   V1 {c1[0]:+.2f}   [{c1[1]} heures]"
            print(f"{nom:12s} {txt.strip()}")
        ax.set_title(f"{nom}   ({n_ep} periode(s) avec previsions et mesures){txt}", loc="left", fontsize=11.5, pad=14)
        ax.set_ylabel("Seeing [arcsec]")
        # 08/10 : echelle automatique sur les medianes horaires et les previsions affichees ; les mesures
        # brutes isolees (outsiders) au-dessus sortent du cadre
        ax.set_ylim(*ECHELLE_Y_HISTORIQUE.get(nom, (0, max(haut, 1.0) * ETIREMENT_Y)))
        ax.grid(axis="y", color="#e4e3df", lw=0.8)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.legend(frameon=False, loc="upper right", fontsize=8, ncol=4, bbox_to_anchor=(1, 1.12))
        if choix:
            encadre_K(ax, nom, cfg[choix[0]], complet=False, v1_trace=choix[2])
    axes[-1].set_xlabel(f"TU  (gris : {NUIT_TEXTE} ; axe compresse : seules les periodes"
                        " avec previsions ET mesures ; || = coupure)")
    fig.suptitle("Historique : previsions AROME et mesures", x=0.01, y=0.998, ha="left", fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT)
    plot_correlations(data, choix_par_site)
    print(OUTPUT_CORR)
    # meme figure avec la V2 seule
    plot_correlations(data, choix_par_site, sortie=OUTPUT_CORR_V2, avec_v1=False, nuit_seule=True,
                      titre=f"Correlation seeing prevu / mesure, {nom_v2()} seule, NUIT seulement ({NUIT_TEXTE})")
    print(OUTPUT_CORR_V2)
    for nom, (f, o) in data.items():
        runs = ", ".join(f"{pd.Timestamp(r):%d/%m %Hh}" for r in sorted(f.run.unique())) if f is not None else "aucun"
        print(f"{nom:12s} mesures {len(o):5d} pts ({o.t.min():%d/%m} -> {o.t.max():%d/%m}) | runs : {runs}")
    print(OUTPUT)


if __name__ == "__main__":
    main()
