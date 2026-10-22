import { useQuery } from "@tanstack/react-query";

import { api, queryKeys } from "../api";
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
