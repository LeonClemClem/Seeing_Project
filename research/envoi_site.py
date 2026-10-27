#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Envoi des donnees des seeing monitors sur le site web (a lancer a la demande, apres un releve).

Pour chaque site de historique_sites.SITES, envoie au site :
  1. les mesures (toutes, en TU) -> calage et histogrammes ;
  2. les previsions V2bd calculees par la recherche, run par run, avec les integrales a K = 1
     (caches cache_validation, comme les figures) -> historique et calage. Les heures deja
     calculees par le serveur ne sont jamais remplacees ;
  3. l'historique tel qu'affiche par la maquette (export_lieux_site.py : periodes, paires horaires).

Il faut un compte ADMINISTRATEUR du site : e-mail et mot de passe sont demandes au lancement
(le mot de passe n'est ni affiche ni enregistre).
Tant que le site est derriere IAP (connexion Google), le script demande a gcloud un jeton d'identite
du compte de service seeing-uploader (autorise a passer IAP, rien d'autre), au nom de ton compte gcloud,
et l'envoie dans l'en-tete Authorization (le site, lui, utilise un cookie).

Usage : python envoi_site.py [--url URL] [--sites "OHP,Drôme"] [--sans mesures,previsions,historique] [--essai]
        --essai : lit et compte tout, sans rien envoyer (pas de connexion).
"""
from pathlib import Path
import sys as _sys; _sys.path.insert(0, str(Path(__file__).resolve().parent))  # chemins.py est a cote
from chemins import CACHE
import argparse, getpass, importlib.util, json, math, os, shutil, subprocess

import pandas as pd

URL_PROD = "https://seeing-web-prod-62naw3atjq-uc.a.run.app"
# Passage d'IAP : compte de service autorise et identifiant OAuth d'IAP du site de production (pas des secrets).
COMPTE_IAP = "seeing-uploader@project-astrarome.iam.gserviceaccount.com"
CLIENT_IAP = "5123733464-g1cleua3a3djp1s5ajrvmlj0916dnle8.apps.googleusercontent.com"
# nom dans historique_sites -> site du serveur
SLUGS = {"Drôme": "verclause", "Copernic": "copernic-gap", "Saint-Veran": "saint-veran", "OHP": "ohp",
         "Seeing monitor 5": "seeing-monitor-5", "Pic du Midi": "pic-du-midi", "Cosmodrome": "cosmodrome"}
PAQUET_MESURES = 20000     # points par envoi (limite du serveur)
PAQUET_RUNS = 40           # runs par envoi
RESEARCH = Path(__file__).resolve().parent


def charge(nom, fichier):
    spec = importlib.util.spec_from_file_location(nom, RESEARCH / fichier)
    m = importlib.util.module_from_spec(spec)
    _sys.modules[nom] = m
    spec.loader.exec_module(m)
    return m


def propre(x):
    """NaN / inf -> None (JSON strict), recursivement."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: propre(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [propre(v) for v in x]
    return x


def runs_recherche(h, tag):
    """Runs du site : fichier V2bd (cache v2bd_100) s'il existe, sinon V2, comme historique_sites.forecasts()."""
    out = []
    for f in sorted(CACHE.glob(f"*__{tag}__*.csv")):
        dossier, suf = h.VARIANTES_V2.get(h.MODELE_V2, (None, None))
        if dossier:
            fb = CACHE / dossier / f"{f.name.split('__')[0]}__{tag}__{suf}.csv"
            if fb.exists():
                f = fb
        d = pd.read_csv(f, parse_dates=["t"])
        if not len(d):
            continue
        run = d.t.iloc[0] - pd.Timedelta(hours=int(d.h.iloc[0]))
        heures = [[int(r.h), None if pd.isna(r.H_COULIM) else float(r.H_COULIM),
                   float(r.I_tke), float(r.I_conv), float(r.I_cis)]
                  for r in d.itertuples() if pd.notna(r.I_tke) and pd.notna(r.I_conv) and pd.notna(r.I_cis)]
        if heures:
            out.append({"run_time": run.strftime("%Y-%m-%dT%H:%M:00Z"), "hours": heures})
    return out


def gcloud():
    """Chemin de gcloud (installation Windows par defaut si absent du PATH)."""
    g = shutil.which("gcloud")
    if g:
        return g
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Cloud SDK/google-cloud-sdk"
    py = base / "platform/bundledpython/python.exe"
    if py.exists():
        os.environ.setdefault("CLOUDSDK_PYTHON", str(py))
    g = base / "bin/gcloud.cmd"
    return str(g) if g.exists() else None


def jeton_iap():
    """Jeton d'identite Google du compte gcloud (pour passer IAP), ou None."""
    g = gcloud()
    if not g:
        return None
    r = subprocess.run([g, "auth", "print-identity-token", f"--impersonate-service-account={COMPTE_IAP}",
                        f"--audiences={CLIENT_IAP}", "--include-email"], capture_output=True, text=True)
    if not r.stdout.strip():
        print("Pas de jeton IAP :", r.stderr.strip()[-300:])
    return r.stdout.strip() or None


class Site:
    def __init__(self, url, iap=True):
        import requests
        self.url, self.s = url.rstrip("/"), requests.Session()
        if iap:
            jeton = jeton_iap()
            if jeton:
                self.s.headers["Authorization"] = "Bearer " + jeton
            else:
                print("gcloud introuvable ou non connecte : pas de jeton IAP (lance 'gcloud auth login').")

    def connexion(self):
        email = input("E-mail du compte administrateur : ").strip()
        mdp = getpass.getpass("Mot de passe (non affiche) : ")
        r = self.s.post(self.url + "/api/auth/login", json={"email": email, "password": mdp})
        del mdp
        if r.status_code != 200:
            if "IAP" in r.text:
                raise SystemExit("Refuse par IAP (protection Google du site) : le compte gcloud n'est pas autorise "
                                 "ou le jeton n'est pas accepte. " + r.text[:200])
            raise SystemExit(f"Connexion refusee ({r.status_code}) : {r.text[:200]}")
        if r.json().get("role") != "admin":
            raise SystemExit("Ce compte n'est pas administrateur.")

    def envoie(self, methode, chemin, corps):
        r = self.s.request(methode, self.url + chemin, json=corps, timeout=300)
        if r.status_code >= 400:
            raise SystemExit(f"{methode} {chemin} : erreur {r.status_code} {r.text[:300]}")
        return r.json()


def main(argv=None):
    p = argparse.ArgumentParser(description="Envoi des donnees des seeing monitors sur le site web.")
    p.add_argument("--url", default=URL_PROD)
    p.add_argument("--sites", default="", help="noms separes par des virgules (defaut : tous)")
    p.add_argument("--sans", default="", help="parmi mesures,previsions,historique")
    p.add_argument("--essai", action="store_true", help="lire et compter sans rien envoyer")
    p.add_argument("--sans-iap", action="store_true", help="ne pas demander de jeton IAP (site public)")
    a = p.parse_args(argv)
    sans = {x.strip() for x in a.sans.split(",") if x.strip()}

    h = charge("historique_sites", "historique_sites.py")
    ex = charge("export_lieux_site", "export_lieux_site.py").Exporter() if "historique" not in sans else None
    noms = [n for n in h.SITES if not a.sites or n in {x.strip() for x in a.sites.split(",")}]
    site = None
    if not a.essai:
        site = Site(a.url, iap=not a.sans_iap)
        site.connexion()

    for nom in noms:
        slug = SLUGS.get(nom)
        if slug is None:
            print(f"{nom}: pas de site correspondant sur le serveur, ignore")
            continue
        ligne = [f"{nom:17s} -> {slug:17s}"]
        if "mesures" not in sans:
            o = h.observations(nom)
            pts = [[t.strftime("%Y-%m-%dT%H:%M:%SZ"), float(v)] for t, v in zip(o.t, o.seeing) if pd.notna(v)]
            stock = rej = 0
            for i in range(0, len(pts), PAQUET_MESURES):
                if site:
                    r = site.envoie("POST", f"/api/sites/{slug}/measurements", {"points": pts[i:i + PAQUET_MESURES]})
                    stock, rej = stock + r["stored"], rej + r["rejected"]
            ligne.append(f"mesures {len(pts)}" + (f" (enregistrees {stock}, rejetees {rej})" if site else ""))
        if "previsions" not in sans:
            runs = runs_recherche(h, h.SITES[nom]["cache_tag"])
            res = {"new_runs": 0, "rows": 0, "kept_existing": 0, "too_recent_runs": 0}
            for i in range(0, len(runs), PAQUET_RUNS):
                if site:
                    r = site.envoie("POST", f"/api/admin/sites/{slug}/forecasts", {"runs": runs[i:i + PAQUET_RUNS]})
                    res = {k: res[k] + r[k] for k in res}
            ligne.append(f"runs {len(runs)}" + (f" (heures ajoutees {res['rows']}, deja sur le serveur {res['kept_existing']}, "
                                                f"runs plus recents que le serveur {res['too_recent_runs']})" if site else ""))
        if ex is not None:
            item = propre(ex.site(nom, h.SITES[nom]))
            taille = len(json.dumps(item)) // 1024
            if site:
                site.envoie("PUT", f"/api/admin/sites/{slug}/history", item)
            ligne.append(f"historique {len(item['episodes'])} periodes, {len(item['paires'])} paires, {taille} Ko")
        print("  ".join(ligne))
    print("Termine." if site else "Essai termine : rien n'a ete envoye.")


if __name__ == "__main__":
    main()
