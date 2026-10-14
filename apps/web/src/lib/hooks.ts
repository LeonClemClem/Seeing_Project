import { useQueries, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { api, queryKeys, type Forecast, type Site } from "../api";
import { tonight, type NightSummary } from "./seeing";

/** Current time, refreshed every minute (for the "now" marker and "tonight"). */
export function useNow(intervalMs = 60_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

export function useLatestRunTime() {
  const run = useQuery({ queryKey: queryKeys.latestRun, queryFn: api.latestRun });
  return { runTime: run.data?.run_time, query: run };
}

export interface SiteSummary {
  site: Site;
  forecast?: Forecast;
  tonight: NightSummary | null;
  isLoading: boolean;
}

export function useSiteSummaries(sites: Site[] | undefined, runTime: string | undefined): SiteSummary[] {
  const now = useNow();
  const results = useQueries({
    queries: (sites ?? []).map((s) => ({
      queryKey: queryKeys.forecast(s.slug, runTime ?? "latest"),
      queryFn: () => api.forecast(s.slug, runTime ?? "latest"),
      enabled: !!runTime,
    })),
  });
  const datas = results.map((r) => r.data);
  const loading = results.map((r) => r.isLoading);
  // Recompute on data change or every ~10 minutes, not on every render.
  const tick = Math.floor(now / 600_000);
  return useMemo(
    () =>
      (sites ?? []).map((site, i) => {
        const forecast = datas[i];
        return {
          site,
          forecast,
          tonight: forecast ? tonight(forecast.points, site.lat, site.lon, tick * 600_000) : null,
          isLoading: loading[i] ?? false,
        };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sites, tick, ...datas, ...loading],
  );
}
