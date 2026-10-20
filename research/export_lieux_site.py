#!/usr/bin/env python3
"""Export the monitored sites (seeing monitors) for the website mock-up.

For every site of ``historique_sites.SITES`` the script writes, in one JavaScript data file:

- the history: periods with both an AROME V2bd forecast and measurements (forecast, raw and hourly median
  seeing, arcsec, UTC);
- the hourly forecast / measurement pairs with a day / night flag (night = 17h30-06h UTC), and the
  correlations;
- the K = 1 integrals of Cn2 (I_tke, I_cis, I_conv, m^1/3) at those hours, so the page can recalibrate K;
- the Cn2 panel of the latest run with saved profiles (``calcul_run.py`` pickles), at the site's current K,
  plus the per-zone profiles at K = 1 so the panel can follow K changes.

Read-only: it reads the caches and the measurements through ``chemins.py`` and writes only the output file.
Usage: ``python export_lieux_site.py [--sortie FICHIER.js]``
"""

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))  # chemins.py is next to this script
from chemins import CACHE, RESEARCH  # noqa: E402

DEFAULT_OUTPUT = RESEARCH.parent / "apps" / "maquette" / "lieux_data.js"
DISPLAY_Z = np.arange(25.0, 4000.0 + 50, 50.0)  # display grid of the Cn2 panel (m above ground)
DELTA_V2BD = 100.0  # width of the V2bd smooth transition at H_COULIM (m)
MAX_RAW_PER_PERIOD = 400  # raw measurements kept per period (sub-sampled above)
LAMBDA = 500e-9  # wavelength for the seeing (m)
MAIN_RUNS = ("00Z", "06Z", "12Z", "18Z")  # only the main AROME runs are used (user rule)
# full-height grid for the week panel: the AROME height levels up to 3000 m, then every 250 m up to 16 km
WEEK_Z = np.concatenate([[10, 20, 35, 50, 75, 100, 150, 200, 250, 375, 500, 625, 750, 875, 1000, 1125, 1250,
                          1375, 1500, 1750, 2000, 2250, 2500, 2750, 3000], np.arange(3250.0, 16001.0, 250.0)]).astype(float)
WEEK_DAYS = 7  # at most one week of Cn2 panels (runs glued, most recent run wins)


def load_module(name, filename):
    """Load a research script as a module without running its __main__ part."""
    spec = importlib.util.spec_from_file_location(name, RESEARCH / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seeing_arcsec(integral):
    """Seeing (arcsec) from the Cn2 integral (m^1/3), same formula as the main script."""
    if not integral > 0:
        return np.nan
    return 0.98 * LAMBDA * (0.423 * (2 * np.pi / LAMBDA) ** 2 * integral) ** 0.6 * 206265


def r2(x, n=2):
    """Round for JSON, None for missing values."""
    return None if x is None or not np.isfinite(x) else round(float(x), n)


def ts(t):
    return pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M")


def log10_or_none(v):
    return None if not np.isfinite(v) or v <= 0 else round(float(np.log10(v)), 2)


class Exporter:
    def __init__(self):
        self.h = load_module("historique_sites", "historique_sites.py")
        self.mb = load_module("mb", "SeeingAromeV2b_cisaillement_V1.py")
        self.mb.K_CIS = 1.0
        self.panels = CACHE / "panneaux"

    # ---------- Cn2 profiles (same physics as figure_cn2_sites.profil_v2bd) ----------
    def zones_k1(self, p, i, hour, k0):
        """V2bd Cn2 at K = 1 for each zone, already weighted by the smooth transition:
        Cn2(K) = K_TKE * tke + K_conv * conv + K_CIS * shear. Returns sorted z and the three zones."""
        cv, r = p["conv"][i], p["r"][hour]
        z = np.asarray(cv["z"], float)
        h_coulim = float(cv.get("h_coulim", r["H_COULIM"]))
        tke = np.nan_to_num(cv["cn2_tke"], nan=0.0) / k0[0]
        conv = (np.where(cv["conv"], np.nan_to_num(cv["cn2_bl"], nan=0.0), 0.0) / k0[2]) if k0[2] else np.zeros_like(z)
        full = {q: np.asarray(r[q], float) for q in ("z", "T", "U", "V", "P")}
        shear = np.interp(z, full["z"], np.nan_to_num(self.mb.cisaillement_v2b(full, h_coulim), nan=0.0))
        w = 0.5 * (1 - np.tanh((z - h_coulim) / DELTA_V2BD))
        order = np.argsort(z)
        return z[order], (w * tke)[order], (w * conv)[order], ((1 - w) * shear)[order]

    def panel(self, name, mesh, run):
        """Cn2 panel of one saved run at the site's current K, plus zones at K = 1 on the display grid."""
        path = self.panels / f"pan_{name}_{mesh}_{run}.pkl"
        if not path.exists():
            return None
        with open(path, "rb") as fh:
            p = pickle.load(fh)
        k0, k_site = tuple(p["K"]), self.h.SITES[name]["K_new"]
        hours = sorted(p["r"])
        times = [p["ref"] + pd.Timedelta(hours=int(x)) for x in hours]
        n, nz = len(hours), DISPLAY_Z.size
        cn2, conv_mask = np.full((n, nz), np.nan), np.zeros((n, nz), bool)
        seeing, h_coulim = np.full(n, np.nan), np.full(n, np.nan)
        zones, integrals = np.zeros((n, 3, nz)), np.zeros((n, 3))
        for i, hour in enumerate(hours):
            k = tuple(self.h.K_heure(k_site, times[i]))
            z, tke, conv, shear = self.zones_k1(p, i, hour, k0)
            for j, part in enumerate((tke, conv, shear)):
                zones[i, j] = np.interp(DISPLAY_Z, z, part, left=np.nan, right=np.nan)
                integrals[i, j] = np.trapezoid(part, z)
            c = k[0] * tke + k[2] * conv + k[1] * shear
            ok = c > 0
            if ok.sum() >= 2:
                cn2[i] = 10 ** np.interp(DISPLAY_Z, z[ok], np.log10(c[ok]), left=np.nan, right=np.nan)
            cv = p["conv"][i]
            zc = np.asarray(cv["z"])
            oc = np.argsort(zc)
            conv_mask[i] = np.asarray(cv["conv"])[oc][np.clip(np.searchsorted(zc[oc], DISPLAY_Z), 0, len(zc) - 1)]
            if np.isfinite(p["df"].seeing_arcsec.iloc[i]):  # no TKE (H+0) or incomplete hour -> empty column
                seeing[i] = seeing_arcsec(np.trapezoid(c, z))
            h_coulim[i] = p["r"][hour]["H_COULIM"]
        empty = ~np.isfinite(seeing)
        cn2[empty], conv_mask[empty] = np.nan, False
        return pd.DatetimeIndex(times), cn2, conv_mask, seeing, h_coulim, zones, integrals

    def week_hours(self, name, mesh, run):
        """Per hour of one saved run: zones at K = 1 on WEEK_Z, convective mask, integrals, H_COULIM."""
        path = self.panels / f"pan_{name}_{mesh}_{run}.pkl"
        if not path.exists():
            return {}
        with open(path, "rb") as fh:
            p = pickle.load(fh)
        k0, out = tuple(p["K"]), {}
        for i, hour in enumerate(sorted(p["r"])):
            t = p["ref"] + pd.Timedelta(hours=int(hour))
            z, tke, conv, shear = self.zones_k1(p, i, hour, k0)
            ok = np.isfinite(p["df"].seeing_arcsec.iloc[i])  # H+0 (no TKE) or incomplete hour -> empty
            cv = p["conv"][i]
            zc = np.asarray(cv["z"])
            oc = np.argsort(zc)
            mask = np.asarray(cv["conv"])[oc][np.clip(np.searchsorted(zc[oc], WEEK_Z), 0, len(zc) - 1)] & (WEEK_Z <= zc.max())
            out[t] = {"ok": bool(ok), "run": run, "hc": float(p["r"][hour]["H_COULIM"]),
                      "zones": [np.interp(WEEK_Z, z, part, left=np.nan, right=np.nan) for part in (tke, conv, shear)],
                      "J": [float(np.trapezoid(part, z)) for part in (tke, conv, shear)], "conv": mask}
        return out

    def week_panel(self, name, obs_median, obs):
        """Up to WEEK_DAYS of main runs glued hour by hour (most recent run wins, except its hours without TKE)."""
        meshes = ("ancienne", "nouvelle") if name == "Copernic" else ("site",)
        runs = sorted({f.stem.rsplit("_", 2)[-2] + "_" + f.stem.rsplit("_", 1)[-1]
                       for f in self.panels.glob(f"pan_{name}_{meshes[-1]}_*.pkl")})
        runs = [r for r in runs if r[-3:] in MAIN_RUNS]
        if not runs:
            return None
        run_time = lambda r: pd.Timestamp(r[:10]) + pd.Timedelta(hours=int(r[11:13]))  # noqa: E731
        last = run_time(runs[-1])
        runs = [r for r in runs if run_time(r) >= last - pd.Timedelta(days=WEEK_DAYS)]
        hours = {}
        for run in runs:  # chronological: later runs overwrite
            per_mesh = [self.week_hours(name, m, run) for m in meshes]
            for t in set.intersection(*(set(d) for d in per_mesh)):
                rec = per_mesh[0][t]
                if len(per_mesh) == 2:  # Copernic: mean of the two meshes
                    b = per_mesh[1][t]
                    rec = {"ok": rec["ok"] and b["ok"], "run": run, "hc": (rec["hc"] + b["hc"]) / 2,
                           "zones": [(x + y) / 2 for x, y in zip(rec["zones"], b["zones"])],
                           "J": [(x + y) / 2 for x, y in zip(rec["J"], b["J"])], "conv": rec["conv"] | b["conv"]}
                if rec["ok"] or t not in hours:
                    hours[t] = rec
        times = sorted(hours)
        t0, t1 = times[0], times[-1]
        n = int((t1 - t0) / pd.Timedelta(hours=1)) + 1
        rows = []
        for i in range(n):
            rec = hours.get(t0 + pd.Timedelta(hours=i))
            if rec is None or not rec["ok"]:
                rows.append(None)
                continue
            rows.append({"r": runs.index(rec["run"]), "hc": r2(rec["hc"], 0),
                         "J": [float(f"{v:.4g}") for v in rec["J"]],
                         "c": "".join("1" if v else "0" for v in rec["conv"]),
                         "z": [[log10_or_none(v) for v in part] for part in rec["zones"]]})
        raw = obs[(obs.t >= t0) & (obs.t <= t1 + pd.Timedelta(hours=1))]
        if len(raw) > 3000:
            raw = raw.iloc[:: int(np.ceil(len(raw) / 3000))]
        return {"runs": runs, "run_t": [ts(run_time(r)) for r in runs], "t0": ts(t0), "n": n, "z": WEEK_Z.tolist(),
                "h": rows,
                "mesures": [[ts(x), r2(v)] for x, v in obs_median.items() if t0 <= x <= t1],
                "brut": [[ts(x), r2(v)] for x, v in zip(raw.t, raw.seeing)]}

    def latest_run(self, name, mesh):
        """Latest MAIN run (00/06/12/18Z) with saved profiles for this site."""
        runs = sorted(f.stem.rsplit("_", 2)[-2] + "_" + f.stem.rsplit("_", 1)[-1]
                      for f in self.panels.glob(f"pan_{name}_{mesh}_*.pkl"))
        runs = [r for r in runs if r[-3:] in MAIN_RUNS]
        return runs[-1] if runs else None

    def site_panel(self, name):
        """Latest panel; Copernic = median (mean for the zones) of its two AROME meshes."""
        if name != "Copernic":
            run = self.latest_run(name, "site")
            return run, (self.panel(name, "site", run) if run else None)
        run = self.latest_run(name, "nouvelle")
        a, b = (self.panel(name, m, run) if run else None for m in ("ancienne", "nouvelle"))
        if a is None or b is None:
            return run, None
        with np.errstate(all="ignore"):
            return run, (a[0], np.nanmedian(np.stack([a[1], b[1]]), 0), a[2] | b[2],
                         np.nanmedian(np.vstack([a[3], b[3]]), 0), (a[4] + b[4]) / 2,
                         (a[5] + b[5]) / 2, (a[6] + b[6]) / 2)

    # ---------- one site ----------
    def site(self, name, cfg):
        h = self.h
        k = tuple(cfg["K_new"])
        lat, lon = h.COORDS[name]
        obs = h.observations(name)
        fc = h.forecasts_site(name)  # Pic du Midi included (cached forecasts exist even if the site is off the daily chain)
        item = {"nom": name, "lat": lat, "lon": lon, "K": [r2(x, 3) for x in k], "modele": h.nom_v2(),
                "mesures_n": int(len(obs)), "mesures_de": ts(obs.t.min()) if len(obs) else None,
                "mesures_a": ts(obs.t.max()) if len(obs) else None, "episodes": [], "paires": [], "cn2": None}
        periods = h.episodes(fc, obs) if fc is not None else []
        th, mh, _ = h.hourly_median(obs, stats=True)
        median = pd.Series(mh, index=th)
        if periods:
            t_f, s_f, _ = h.arome(fc, k)
            forecast = pd.Series(np.asarray(s_f, float), index=pd.DatetimeIndex(t_f))
            for a, b in periods:
                raw = obs[(obs.t >= a) & (obs.t <= b)]
                if len(raw) > MAX_RAW_PER_PERIOD:
                    raw = raw.iloc[:: int(np.ceil(len(raw) / MAX_RAW_PER_PERIOD))]
                sel = lambda s: s[(s.index >= a) & (s.index <= b)]  # noqa: E731
                item["episodes"].append({"a": ts(a), "b": ts(b),
                                         "prevu": [[ts(t), r2(v)] for t, v in sel(forecast).items()],
                                         "mediane": [[ts(t), r2(v)] for t, v in sel(median).items()],
                                         "brut": [[ts(t), r2(v)] for t, v in zip(raw.t, raw.seeing)]})
            with_tke = fc[np.asarray(fc.has_tke, bool)]
            inside = np.zeros(len(with_tke), bool)
            for a, b in periods:
                inside |= ((with_tke.t >= a) & (with_tke.t <= b)).to_numpy()
            with_tke = with_tke[inside]
            item["integ"] = [[ts(t), float(f"{a:.4g}"), float(f"{c:.4g}"), float(f"{v:.4g}")]
                             for t, a, c, v in zip(with_tke.t, with_tke.I_tke, with_tke.I_cis, with_tke.I_conv)]
            pairs = h.paires_horaires(fc, obs, k, periods)
            night = h.est_nuit(pairs.index)
            item["paires"] = [[ts(t), r2(a), r2(b), bool(nt)]
                              for t, a, b, nt in zip(pairs.index, pairs.prevu, pairs.mesure, night)]
            for key, mask in (("nuit", night), ("jour", ~night), ("tout", np.ones(len(pairs), bool))):
                q = pairs[mask]
                item["r_" + key] = r2(h.wcorr(q.prevu, q.mesure, np.ones(len(q))) if len(q) >= 3 else np.nan)
                item["n_" + key] = int(len(q))
                item["biais_" + key] = r2((q.prevu - q.mesure).mean()) if len(q) else None
        item["cn2w"] = self.week_panel(name, median, obs)
        run, panel = self.site_panel(name)
        if panel is not None:
            times, cn2, conv_mask, seeing, h_coulim, zones, integrals = panel
            item["cn2"] = {
                "run": run, "t0": ts(times[0]), "z": DISPLAY_Z.tolist(),
                "log": [[log10_or_none(v) for v in row] for row in cn2],
                "conv": [[int(v) for v in row] for row in conv_mask],
                "seeing": [r2(v) for v in seeing], "hc": [r2(v, 0) for v in h_coulim],
                "mesures": [[ts(x), r2(v)] for x, v in median.items() if times[0] <= x <= times[-1]],
                "parties": [None if not np.isfinite(seeing[i]) else [[log10_or_none(v) for v in zones[i, j]]
                                                                    for j in range(3)] for i in range(len(seeing))],
                "J": [None if not np.isfinite(seeing[i]) else [float(f"{v:.4g}") for v in integrals[i]]
                      for i in range(len(seeing))],
            }
        return item

    def run(self):
        sites = []
        for name, cfg in self.h.SITES.items():
            item = self.site(name, cfg)
            sites.append(item)
            print(f"{name:18s} mesures {item['mesures_n']:6d}  periodes {len(item['episodes']):2d}  "
                  f"paires {len(item['paires']):4d}  r nuit {item.get('r_nuit')}  r jour {item.get('r_jour')}  "
                  f"cn2 {item['cn2']['run'] if item['cn2'] else 'non'}")
        return {"genere": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"), "lieux": sites}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Export the monitored sites for the website mock-up.")
    parser.add_argument("--sortie", type=Path, default=DEFAULT_OUTPUT,
                        help=f"output JavaScript data file (default: {DEFAULT_OUTPUT})")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    data = Exporter().run()
    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    args.sortie.write_text("window.LIEUX_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";",
                           encoding="utf-8")
    print(args.sortie, round(args.sortie.stat().st_size / 1024), "Ko")


if __name__ == "__main__":
    main()
