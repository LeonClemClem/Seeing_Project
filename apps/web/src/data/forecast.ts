import { useIsFetching, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { api, queryKeys, type Forecast } from "../api";
import { isNightDate, pd } from "../lib/util";
import type { LieuData, LieuEpisode } from "../mock/engine";
import type { K3 } from "../store";
import type { Place } from "./places";

export type View = "run" | "week";

/** True while a query of this place (forecast, Cn², history, measurements) loads with no data yet: switching
 * to another place shows a spinner instead of "no data". Background refreshes do not count. */
export function usePlaceLoading(place: Place): boolean {
  const slug = place.slug ?? "";
  return (
    useIsFetching({
      predicate: (q) => !!slug && q.state.data === undefined && q.queryKey.some((k) => k === slug),
    }) > 0
  );
}

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

/** History forecast and pairs on the server data (`/verif`): one forecast per hour with its integrals at K = 1,
 * recomputed with the site's current K, and the measured hourly median (+/- 30 min), the same for every panel. The
 * hours without integrals cannot be compared: no forecast, no pair; the nights without any of them are not shown at
 * all, nor those without a night hour with both forecast and measurement (their measurements stay stored).
 * One period per night kept. */
function alignVerif(l: LieuData, v: { valid_times: string[]; seeing_arcsec: (number | null)[]; measured_arcsec: (number | null)[] }): LieuData {
  const f = new Map<string, number>(),
    m = new Map<string, number>();
  v.valid_times.forEach((t, i) => {
    const k = t.slice(0, 16),
      s = v.seeing_arcsec[i],
      o = v.measured_arcsec[i];
    if (s != null && s > 0) f.set(k, s);
    if (o != null) m.set(k, o);
  });
  // night of a time: date of the evening (12h UTC to 12h UTC)
  const nk = (t: string) => new Date(pd(t.slice(0, 16)).getTime() - 12 * 3600000).toISOString().slice(0, 10);
  const withF = new Set([...f.keys()].map(nk));
  const episodes: LieuEpisode[] = [];
  l.episodes.forEach((e) => {
    const by = new Map<string, LieuEpisode>();
    const of = (k: string) => by.get(k) ?? by.set(k, { a: e.a, b: e.b, prevu: [], mediane: [], brut: [] }).get(k)!;
    f.forEach((s, t) => t >= e.a && t <= e.b && of(nk(t)).prevu.push([t, +s.toFixed(2)]));
    e.mediane.forEach((p) => withF.has(nk(p[0])) && of(nk(p[0])).mediane.push(p));
    e.brut.forEach((p) => withF.has(nk(p[0])) && of(nk(p[0])).brut.push(p));
    [...by.entries()]
      .sort((x, y) => (x[0] < y[0] ? -1 : 1))
      .forEach(([, x]) => {
        // kept only with at least one night hour that has both the forecast and a measurement
        if (!x.prevu.some(([t]) => m.has(t) && isNightDate(new Date(t + ":00Z")))) return;
        const ts = [...x.prevu, ...x.mediane, ...x.brut].map((p) => p[0].slice(0, 16)).sort();
        episodes.push({ ...x, prevu: x.prevu.sort((p, q) => (p[0] < q[0] ? -1 : 1)), a: ts[0]! > e.a ? ts[0]! : e.a, b: ts[ts.length - 1]! < e.b ? ts[ts.length - 1]! : e.b });
      });
  });
  const paires: LieuData["paires"] = [];
  episodes.forEach((e) =>
    e.prevu.forEach(([t, s]) => {
      const o = m.get(t);
      if (o != null) paires.push([t, s, +o.toFixed(2), isNightDate(new Date(t + ":00Z"))]);
    }),
  );
  return { ...l, episodes, paires };
}

/** History of a real site: the research periods (research/envoi_site.py), then the periods built on the
 * server data (past forecasts and collected measurements); forecast and pairs from `/verif` (current K, hours with
 * integrals only). undefined while loading or when there is none. */
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
  const vq = useQuery({
    queryKey: ["verif", slug],
    queryFn: () => api.verif(slug),
    enabled: place.real && !!slug,
    retry: false,
    staleTime: 10 * 60 * 1000,
  });
  return useMemo(() => {
    if (vq.isLoading) return undefined;
    const after = Math.max(-Infinity, ...(res?.episodes ?? []).map((e) => Date.parse(e.b + ":00Z")));
    const live = fq.data && meas?.length ? liveHistory(fq.data, meas, after) : null;
    if (!res && !live?.episodes.length) return undefined;
    const base: LieuData = res ?? { nom: place.nom, modele: "V2bd", K: [...place.K], episodes: [], paires: [] };
    const all = live ? { ...base, episodes: [...base.episodes, ...live.episodes], paires: [...base.paires, ...live.paires] } : base;
    return vq.data ? alignVerif(all, vq.data) : all;
  }, [res, fq.data, meas, place.nom, place.K, vq.data, vq.isLoading]);
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
