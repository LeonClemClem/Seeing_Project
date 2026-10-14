/** Types and fetchers for the API contract in docs/architecture.md. */

export interface Site {
  slug: string;
  name: string;
  lat: number;
  lon: number;
  altitude_m: number | null;
}

export interface Run {
  run_time: string;
  finished_at: string | null;
  status: string;
}

export interface ForecastPoint {
  lead_hour: number;
  valid_time: string;
  seeing_arcsec: number | null;
  r0_m: number | null;
  integral_cn2: number | null;
  h_coulim_m: number | null;
}

export interface Forecast {
  site: Site;
  run_time: string;
  points: ForecastPoint[];
}

export interface Cn2 {
  site: Site;
  run_time: string;
  valid_times: string[];
  heights_m: number[];
  cn2: (number | null)[][];
}

export interface Me {
  email: string | null;
  env: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  me: () => get<Me>("/api/me"),
  sites: () => get<Site[]>("/api/sites"),
  latestRun: () => get<Run>("/api/runs/latest"),
  forecast: (slug: string, run = "latest") =>
    get<Forecast>(`/api/sites/${encodeURIComponent(slug)}/forecast?run=${encodeURIComponent(run)}`),
  cn2: (slug: string, run = "latest") =>
    get<Cn2>(`/api/sites/${encodeURIComponent(slug)}/cn2?run=${encodeURIComponent(run)}`),
};

/** Query keys include the run time so a new run invalidates everything naturally. */
export const queryKeys = {
  me: ["me"] as const,
  sites: ["sites"] as const,
  latestRun: ["runs", "latest"] as const,
  forecast: (slug: string, run: string) => ["forecast", slug, run] as const,
  cn2: (slug: string, run: string) => ["cn2", slug, run] as const,
};
