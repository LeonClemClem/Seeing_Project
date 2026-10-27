import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { api, queryKeys } from "../api";
import type { LieuData } from "../mock/engine";
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
  const slug = place.slug ?? "";
  const q = useQuery({
    queryKey: ["measurements", slug],
    queryFn: () => api.measurements(slug),
    enabled: place.real && !!slug,
    retry: false,
    staleTime: 10 * 60 * 1000,
  });
  const h = useSiteHistory(place);
  return useMemo(() => {
    const m = new Map<number, number>();
    h?.episodes.forEach((e) =>
      e.brut.forEach(([t, v]) => {
        if (v != null) m.set(Date.parse(t.length <= 16 ? t + ":00Z" : t), v);
      }),
    );
    q.data?.times.forEach((t, i) => m.set(Date.parse(t), q.data!.seeing_arcsec[i]!));
    return [...m.entries()].sort((a, b) => a[0] - b[0]);
  }, [q.data, h]);
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
  const h = useSiteHistory(place);
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

/** History of a real site (research periods with forecast and measurements), as the charts expect it.
 * undefined while loading or when the site has none. */
export function useSiteHistory(place: Place): LieuData | undefined {
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
