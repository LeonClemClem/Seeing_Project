import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { api, queryKeys } from "../api";
import type { LieuData } from "../mock/engine";
import type { K3 } from "../store";
import type { Place } from "./places";

/** Latest-run forecast and Cn² of an API site (disabled for mock places). */
export function useRealForecast(place: Place) {
  const slug = place.slug ?? "";
  const forecast = useQuery({
    queryKey: queryKeys.forecast(slug, "latest"),
    queryFn: () => api.forecast(slug),
    enabled: place.real && !!slug,
  });
  const cn2 = useQuery({
    queryKey: queryKeys.cn2(slug, "latest"),
    queryFn: () => api.cn2(slug),
    enabled: place.real && !!slug,
  });
  return { forecast, cn2 };
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
