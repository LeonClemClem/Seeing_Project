import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { api, queryKeys, type Forecast } from "../api";
import { isNightDate } from "../lib/util";
import type { LieuData, LieuEpisode } from "../mock/engine";
import type { K3 } from "../store";
import type { Place } from "./places";

export type View = "run" | "week";

/** Forecast and Cn² of an API site (disabled for mock places): the latest run, or ("week") up to 7 days of
 * main runs stitched then the latest run. */
export function useRealForecast(place: Place, view: View = "run") {
  const slug = place.slug ?? "";
  const forecast = useQuery({
    queryKey: queryKeys.forecast(slug, "latest", view),
    queryFn: () => api.forecast(slug, "latest", view),
    enabled: place.real && !!slug,
  });
  const cn2 = useQuery({
    queryKey: queryKeys.cn2(slug, "latest", view),
    queryFn: () => api.cn2(slug, "latest", view),
    enabled: place.real && !!slug,
  });
  return { forecast, cn2 };
}

/** Raw measurements of a real site [ms, arcsec], sorted: those stored on the server (research uploads and the
 * daily collection of the online monitors) and the raw points of the research history. */
export function useRawMeasurements(place: Place): [number, number][] {
  const srv = useServerMeasurements(place);
  const h = useResearchHistory(place);
  return useMemo(() => {
    const m = new Map<number, number>();
    h?.episodes.forEach((e) =>
      e.brut.forEach(([t, v]) => {
        if (v != null) m.set(Date.parse(t.length <= 16 ? t + ":00Z" : t), v);
      }),
    );
    srv?.forEach(([t, v]) => m.set(t, v));
    return [...m.entries()].sort((a, b) => a[0] - b[0]);
  }, [srv, h]);
}

/** Measurements stored on the server [ms, arcsec], sorted (research uploads and the daily monitor collection). */
function useServerMeasurements(place: Place): [number, number][] | undefined {
  const slug = place.slug ?? "";
  const q = useQuery({
    queryKey: ["measurements", slug],
    queryFn: () => api.measurements(slug),
    enabled: place.real && !!slug,
    retry: false,
    staleTime: 10 * 60 * 1000,
  });
  return useMemo(
    () => q.data?.times.map((t, i): [number, number] => [Date.parse(t), q.data!.seeing_arcsec[i]!]).sort((a, b) => a[0] - b[0]),
    [q.data],
  );
}

/** Hourly medians of raw points [ms, arcsec], by round UTC hour [ms] (each hour +/- 30 min). */
export function hourlyMedians(raw: [number, number][]): Map<number, number> {
  const by = new Map<number, number[]>();
  raw.forEach(([t, v]) => {
    const k = Math.round(t / 3600000) * 3600000;
    (by.get(k) ?? by.set(k, []).get(k)!).push(v);
  });
  const out = new Map<number, number>();
  by.forEach((v, k) => {
    v.sort((a, b) => a - b);
    const n = v.length;
    out.set(k, n % 2 ? v[(n - 1) / 2]! : (v[n / 2 - 1]! + v[n / 2]!) / 2);
  });
  return out;
}

/** Measured hourly medians of a real site (research history), by UTC hour [ms]. */
export function useHourlyMedians(place: Place): Map<number, number> {
  const h = useResearchHistory(place);
  return useMemo(() => {
    const m = new Map<number, number>();
    h?.episodes.forEach((e) =>
      e.mediane.forEach(([t, v]) => {
        if (v != null) m.set(Date.parse(t.length <= 16 ? t + ":00Z" : t), v);
      }),
    );
    return m;
  }, [h]);
}

const HOUR = 3600000;
const isoMin = (ms: number) => new Date(ms).toISOString().slice(0, 16);
/** Gap that splits the measurements into periods, as research COUPURE_MESURES_H. */
const GAP = 3 * HOUR;
const MAX_RAW = 3000; // raw points kept per period, as research MAX_RAW_PER_PERIOD

/** History periods built on the server data, after the research history (`after`, ms): the past forecasts
 * stitched (main runs, shortest lead) and the stored measurements (uploads and daily monitor collection).
 * Same shape as the research export: periods with forecast, hourly medians and raw points; hourly pairs. */
export function liveHistory(fc: Forecast, meas: [number, number][], after: number): Pick<LieuData, "episodes" | "paires"> {
  const f = new Map<number, number>();
  fc.points.forEach((p) => {
    if (p.seeing_arcsec != null && p.seeing_arcsec > 0) f.set(Date.parse(p.valid_time), p.seeing_arcsec);
  });
  const raw = meas.filter(([t]) => t > after);
  const runs: [number, number][][] = [];
  raw.forEach((q, k) => {
    if (k && q[0] - raw[k - 1]![0] <= GAP) runs[runs.length - 1]!.push(q);
    else runs.push([q]);
  });
  const episodes: LieuEpisode[] = [],
    paires: LieuData["paires"] = [];
  for (const r of runs) {
    const a = r[0]![0] - HOUR / 2,
      b = r[r.length - 1]![0] + HOUR / 2;
    const hours: number[] = [];
    for (let h = Math.ceil(a / HOUR) * HOUR; h <= b; h += HOUR) if (f.has(h)) hours.push(h);
    if (!hours.length) continue; // measurements without any forecast: not a history period
    const by = new Map<number, number[]>();
    r.forEach(([t, v]) => {
      const k = Math.round(t / HOUR) * HOUR;
      (by.get(k) ?? by.set(k, []).get(k)!).push(v);
    });
    const med = [...by.entries()]
      .sort((x, y) => x[0] - y[0])
      .map(([k, v]): [number, number] => {
        v.sort((x, y) => x - y);
        const n = v.length;
        return [k, n % 2 ? v[(n - 1) / 2]! : (v[n / 2 - 1]! + v[n / 2]!) / 2];
      });
    const step = Math.ceil(r.length / MAX_RAW);
    episodes.push({
      a: isoMin(Math.max(a, hours[0]! - HOUR / 2)),
      b: isoMin(Math.min(b, hours[hours.length - 1]! + HOUR / 2)),
      prevu: hours.map((h) => [isoMin(h), +f.get(h)!.toFixed(2)]),
      mediane: med.map(([k, v]) => [isoMin(k), +v.toFixed(2)]),
      brut: r.filter((_, k) => k % step === 0).map(([t, v]) => [isoMin(t), v]),
    });
    med.forEach(([k, v]) => f.has(k) && paires.push([isoMin(k), +f.get(k)!.toFixed(2), +v.toFixed(2), isNightDate(new Date(k))]));
  }
  return { episodes, paires };
}

/** History of a real site: the research periods (research/envoi_site.py), then the periods built on the
 * server data (past forecasts and collected measurements). undefined while loading or when there is none. */
export function useSiteHistory(place: Place): LieuData | undefined {
  const res = useResearchHistory(place);
  const slug = place.slug ?? "";
  const fq = useQuery({
    queryKey: queryKeys.forecast(slug, "latest", "all"),
    queryFn: () => api.forecast(slug, "latest", "all"),
    enabled: place.real && !!slug,
    retry: false,
    staleTime: 10 * 60 * 1000,
  });
  const meas = useServerMeasurements(place);
  return useMemo(() => {
    const after = Math.max(-Infinity, ...(res?.episodes ?? []).map((e) => Date.parse(e.b + ":00Z")));
    const live = fq.data && meas?.length ? liveHistory(fq.data, meas, after) : null;
    if (!res && !live?.episodes.length) return undefined;
    const base: LieuData = res ?? { nom: place.nom, modele: "V2bd", K: [...place.K], episodes: [], paires: [] };
    if (!live) return base;
    return { ...base, episodes: [...base.episodes, ...live.episodes], paires: [...base.paires, ...live.paires] };
  }, [res, fq.data, meas, place.nom, place.K]);
}

/** Research history of a real site (sent by research/envoi_site.py), as the charts expect it.
 * undefined while loading or when the site has none. */
function useResearchHistory(place: Place): LieuData | undefined {
  const slug = place.slug ?? "";
  const q = useQuery({
    queryKey: ["history", slug],
    queryFn: () => api.history(slug),
    enabled: place.real && !!slug,
    retry: false,
    staleTime: 10 * 60 * 1000,
  });
  const d = q.data;
  return useMemo(() => {
    if (!d) return undefined;
    const k = d.K;
    const K: K3 = k && k.length === 3 ? [k[0]!, k[1]!, k[2]!] : [...place.K];
    return { nom: place.nom, modele: d.modele ?? "V2bd", K, episodes: d.episodes, paires: d.paires };
  }, [d, place.nom, place.K]);
}
