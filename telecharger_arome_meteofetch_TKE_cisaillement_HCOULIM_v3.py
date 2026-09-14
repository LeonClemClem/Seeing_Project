import argparse
import logging
from pathlib import Path

from meteofetch import Arome0025


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


def download_arome(output_dir):

    output_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    print()
    print("=" * 70)
    print("Téléchargement AROME 0.025° avec MeteoFetch")
    print("Variables : HP1 + HP2(TKE HAG) + IP1 + IP4(TKE isobare) + SP2(H_COULIM)")
    print("=" * 70)
    print(f"Dossier : {output_dir.resolve()}")
    print(f"Paquets : {', '.join(PACKAGES)}")
    print()

    for package in PACKAGES:

        print("-" * 70)
        print(f"Téléchargement du paquet {package}")
        print("-" * 70)

        paths = Arome0025.get_latest_forecast(
            paquet=package,
            path=str(output_dir),
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


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download AROME 0.025° GRIB2 forecast files via MeteoFetch."
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Folder to save downloaded GRIB2 files into (default: current directory).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    download_arome(parse_args().output_dir)