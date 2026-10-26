/** Types and fetchers for the API contract in docs/architecture.md. */

export interface Site {
  slug: string;
  name: string;
  lat: number;
  lon: number;
  altitude_m: number | null;
  /** "public" (observatory), "shared" (by a team with the community) or "hidden" (sent to the admin only). */
  visibility: "public" | "shared" | "hidden";
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

/** Global seeing map of a run (GET /api/map); each frame is fetched as ny * nx bytes. */
export interface MapGrid {
  ny: number;
  nx: number;
  lat0: number;
  lon0: number;
  dlat: number;
  dlon: number;
}
export interface MapMeta {
  run_time: string;
  grid: MapGrid;
  see_min: number;
  see_max: number;
  frames: { lead_hour: number; valid_time: string }[];
}

export type UserRole = "user" | "team" | "admin";

export interface User {
  id: number;
  email: string;
  display_name: string | null;
  role: UserRole;
}

export interface Me {
  /** Identity asserted by IAP, independent of the app account. */
  email: string | null;
  env: string;
  /** Logged-in app account, or null. */
  user: User | null;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: { Accept: "application/json", ...init.headers },
  });
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
  return (res.status === 204 ? undefined : await res.json()) as T;
}

const get = <T>(path: string) => request<T>(path);
/** JSON POST: the auth endpoints only accept application/json (CSRF guard). */
const post = <T>(path: string, body: unknown = {}) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });

export const api = {
  me: () => get<Me>("/api/me"),
  signup: (b: { email: string; password: string; display_name?: string }) => post<User>("/api/auth/signup", b),
  login: (b: { email: string; password: string }) => post<User>("/api/auth/login", b),
  logout: () => post<void>("/api/auth/logout"),
  sites: () => get<Site[]>("/api/sites"),
  latestRun: () => get<Run>("/api/runs/latest"),
  forecast: (slug: string, run = "latest") =>
    get<Forecast>(`/api/sites/${encodeURIComponent(slug)}/forecast?run=${encodeURIComponent(run)}`),
  cn2: (slug: string, run = "latest") =>
    get<Cn2>(`/api/sites/${encodeURIComponent(slug)}/cn2?run=${encodeURIComponent(run)}`),
  map: () => get<MapMeta>("/api/map"),
  /** Raw codes of one map frame (uint8, 255 = no value). */
  mapFrame: async (run: string, lead: number): Promise<Uint8Array> => {
    const res = await fetch(`/api/map/frame?run=${encodeURIComponent(run)}&lead=${lead}`, { credentials: "same-origin" });
    if (!res.ok) throw new ApiError(res.status, res.statusText);
    return new Uint8Array(await res.arrayBuffer());
  },
};

/** Query keys include the run time so a new run invalidates everything naturally. */
export const queryKeys = {
  me: ["me"] as const,
  sites: ["sites"] as const,
  latestRun: ["runs", "latest"] as const,
  forecast: (slug: string, run: string) => ["forecast", slug, run] as const,
  cn2: (slug: string, run: string) => ["cn2", slug, run] as const,
  map: (run: string) => ["map", run] as const,
};
