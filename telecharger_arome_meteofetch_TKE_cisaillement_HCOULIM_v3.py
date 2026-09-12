from pathlib import Path
import logging

from meteofetch import Arome0025


OUTPUT_DIR = Path("AROME_download")

# Paquets nécessaires au calcul complet sur toute la colonne :
#
# HP1 : T, U, V, P, Z sur niveaux hauteur AGL 20–3000 m
#       -> meilleure résolution verticale dans les premiers kilomètres.
#
# HP2 : TKE sur niveaux hauteur AGL 10–3000 m
#       -> modèle TKE dans les premiers kilomètres.
#
# IP1 : T, U, V, Z sur niveaux isobares 1000–100 hPa
#       -> variables thermodynamiques et vent au-dessus de 3000 m.
#
# IP4 : TKE sur les mêmes niveaux isobares
#       -> permet de prolonger le modèle TKE au-dessus de 3000 m
#          lorsque H_COULIM dépasse 3000 m.
#
# SP2 : H_COULIM / blh (surface)
#       -> hauteur de couche limite pour la séparation des modèles.
#
# L'altitude du relief n'est pas supposée provenir de SP2 : le code de calcul
# peut la déduire du géopotentiel Z des niveaux heightAboveGround si nécessaire.
PACKAGES = ("HP1", "HP2", "IP1", "IP4", "SP2")


def download_arome():

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    print()
    print("=" * 70)
    print("Téléchargement AROME 0.025° avec MeteoFetch")
    print("Variables : HP1 + HP2(TKE HAG) + IP1 + IP4(TKE isobare) + SP2(H_COULIM)")
    print("=" * 70)
    print(f"Dossier : {OUTPUT_DIR.resolve()}")
    print(f"Paquets : {', '.join(PACKAGES)}")
    print()

    for package in PACKAGES:

        print("-" * 70)
        print(f"Téléchargement du paquet {package}")
        print("-" * 70)

        paths = Arome0025.get_latest_forecast(
            paquet=package,
            path=str(OUTPUT_DIR),
            return_data=False,
            num_workers=1,
            num_retries=5,
        )

        print()
        print(f"Paquet {package} terminé.")

        if paths is None:
            print("Aucun fichier retourné.")
            continue

        if isinstance(paths, (str, Path)):
            paths = [paths]

        for path in paths:
            print(f"  {path}")

    print()
    print("=" * 70)
    print("Téléchargement terminé.")
    print("=" * 70)


if __name__ == "__main__":
    download_arome()