"""Recupere et trace le seeing des sites Miratlas publics OHP et Villeneuve (API Grafana anonyme).

Points bruts + mediane glissante (5 points, centree, min_periods=1) par segment continu (trou > 10 min = coupure).
Sauvegarde aussi les donnees en CSV (TU) dans seeing-miratlas/.
Usage : python releve_miratlas_ohp_sm5.py [jours]   (defaut : 30)
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import requests

ROOT = Path(__file__).parent
OUT = ROOT / "seeing-miratlas"
OUT.mkdir(exist_ok=True)
API = "https://dashboard.miratlas.net/api/ds/query?orgId=29"
GAP = pd.Timedelta(minutes=10)
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 30

SITES = {  # nom -> uid de la datasource InfluxDB
    "OHP": "dec92cumscphca",
    "Villeneuve": "d4ce5b0b-3a85-4e59-8931-c82a59f73f6e",
}
AFFICHE = {"Villeneuve": "Seeing monitor 5"}   # 13/10 : nom affiche (demande utilisateur) ; fichiers inchanges
SERIES = [  # colonne, measurement, field, libelle, couleur (couleurs du tableau de bord Miratlas)
    ("day_ssm_arcsec", "ism_stations", "day_see", "Jour SSM", "tab:green"),
    ("night_cdimm_arcsec", "ism_stations", "night_see", "Nuit CDIMM", "goldenrod"),
    ("day_shabar_arcsec", "shabar", "seeing", "Jour SHABAR", "tab:orange"),
]


def fetch(ds_uid):
    start = (datetime.now(timezone.utc) - timedelta(days=DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    queries = [{
        "refId": col,
        "datasource": {"type": "influxdb", "uid": ds_uid},
        "maxDataPoints": 200000,
        "query": (f'from(bucket: "miratlas")\n |> range(start: {start}, stop: v.timeRangeStop)\n'
                  f' |> filter(fn: (r) => r._measurement == "{m}" and r._field == "{f}")\n'
                  f' |> filter(fn: (r) => r._value > 0 and r._value <= 10)\n'
                  f' |> group(columns: ["_field"])'),
    } for col, m, f, _, _ in SERIES]
    r = requests.post(API, json={"queries": queries, "from": f"now-{DAYS}d", "to": "now"}, timeout=120)
    r.raise_for_status()
    out = {}
    for col, *_ in SERIES:
        frames = r.json()["results"][col].get("frames") or []
        s = pd.Series(dtype=float)
        if frames and frames[0]["data"]["values"]:
            t, v = frames[0]["data"]["values"][:2]
            s = pd.Series(v, index=pd.to_datetime(t, unit="ms")).sort_index()   # group() ne trie pas
        out[col] = s
    return out


fig, axes = plt.subplots(len(SITES), 1, figsize=(14, 4.5 * len(SITES)))
for ax, (site, uid) in zip(axes, SITES.items()):
    data = fetch(uid)
    pd.DataFrame(data).rename_axis("datetime_utc").to_csv(
        OUT / f"{site.lower()}_{datetime.now(timezone.utc):%Y-%m-%d}_UTC.csv", date_format="%Y-%m-%dT%H:%M:%SZ")
    t0 = None
    for col, _, _, label, color in SERIES:
        s = data[col]
        if s.empty:
            continue
        t0 = s.index.min() if t0 is None else min(t0, s.index.min())
        ax.plot(s.index, s.values, ".", ms=2, color=color, alpha=0.3, label=f"{label} ({len(s)} mesures)")
        segment = (s.index.to_series().diff() > GAP).cumsum()
        for i, (_, seg) in enumerate(s.groupby(segment.values)):
            med = seg.rolling(window=5, center=True, min_periods=1).median()
            ax.plot(med.index, med.values, "-", lw=1, color=color,
                    label=f"{label} - mediane glissante 5 pts" if i == 0 else None)
    if t0 is not None:
        ax.set_xlim(t0.floor("D"), pd.Timestamp.utcnow().tz_localize(None).ceil("D"))
    span = (ax.get_xlim()[1] - ax.get_xlim()[0])
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1 if span <= 10 else 2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    ax.set_ylim(0, 10)
    ax.set_ylabel("Seeing zenith 550 nm (arcsec)")
    ax.set_title(f"{AFFICHE.get(site, site)} - seeing mesure (Miratlas), TU")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=8, ncol=2)
axes[-1].set_xlabel("Date (TU)")
fig.tight_layout()

png = ROOT / "releves" / f"miratlas_ohp_villeneuve_{datetime.now(timezone.utc):%Y-%m-%d}.png"
fig.savefig(png, dpi=110)
print(png)
