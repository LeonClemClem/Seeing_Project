"""Trace le seeing de Saint-Veran pour une journee (TU) a partir du dernier releve.

Points bruts + mediane glissante (5 points, centree, min_periods=1) par instrument.
Usage : python plot_saint_veran_jour.py [AAAA-MM-JJ]   (defaut : aujourd'hui TU)
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).parent
CSV = ROOT / "seeing-saint-veran" / "seeing_saint_veran.csv"
GAP = pd.Timedelta(minutes=10)   # au-dela, la courbe est interrompue

SERIES = [  # colonne, libelle, couleur (memes couleurs que le tableau de bord Miratlas)
    ("day_ssm_arcsec", "Jour SSM", "tab:green"),
    ("night_cdimm_arcsec", "Nuit CDIMM", "goldenrod"),
    ("day_shabar_arcsec", "Jour SHABAR", "tab:orange"),
]

jour = pd.Timestamp(sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y-%m-%d"))
df = pd.read_csv(CSV, parse_dates=["datetime_utc"])
df["datetime_utc"] = df["datetime_utc"].dt.tz_localize(None)
df = df[(df["datetime_utc"] >= jour) & (df["datetime_utc"] < jour + pd.Timedelta(days=1))].sort_values("datetime_utc")

fig, ax = plt.subplots(figsize=(12, 5))
for col, label, color in SERIES:
    s = df.set_index("datetime_utc")[col].dropna()
    if s.empty:
        continue
    ax.plot(s.index, s.values, ".", ms=3, color=color, alpha=0.35, label=f"{label} ({len(s)} mesures)")
    # mediane glissante calculee par segment continu : pas de melange ni de trait a travers les trous
    segment = (s.index.to_series().diff() > GAP).cumsum()
    for i, (_, seg) in enumerate(s.groupby(segment.values)):
        med = seg.rolling(window=5, center=True, min_periods=1).median()
        ax.plot(med.index, med.values, "-", lw=1.4, color=color,
                label=f"{label} - mediane glissante 5 pts" if i == 0 else None)

ax.set_xlim(jour, jour + pd.Timedelta(days=1))
ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax.set_ylim(bottom=0)
ax.set_xlabel("Heure (TU)")
ax.set_ylabel("Seeing au zenith a 550 nm (arcsec)")
ax.set_title(f"Saint-Veran - seeing du {jour:%d/%m/%Y} (TU)")
ax.grid(alpha=0.3)
ax.legend(loc="upper left", fontsize=8)
fig.tight_layout()

out = ROOT / "releves" / f"saint_veran_{jour:%Y-%m-%d}.png"
fig.savefig(out, dpi=120)
print(out)
