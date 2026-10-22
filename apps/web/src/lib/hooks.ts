import { useQuery } from "@tanstack/react-query";

import { api, queryKeys } from "../api";

export function useLatestRunTime() {
  const run = useQuery({ queryKey: queryKeys.latestRun, queryFn: api.latestRun });
  return { runTime: run.data?.run_time, query: run };
}
