/** Types and fetchers for the API contract in docs/architecture.md. */

/** AROME orography of the grid cells around a site: centre of the site's cell, cell size [deg], altitudes
 * [m] in rows north to south (null where undefined). */
export interface Cells {
  lat0: number;
  lon0: number;
  step: number;
  alt: (number | null)[][];
}

export interface Site {
  slug: string;
  name: string;
  lat: number;
  lon: number;
  altitude_m: number | null;
  /** "public" (observatory), "shared" (by a team or a member with the community), "hidden" (sent to the
   * admin only) or "private" (the account's own place). */
  visibility: "public" | "shared" | "hidden" | "private";
  /** Personal place of the logged-in account. */
  owned?: boolean;
  /** (K_TKE, K_CIS, K_conv), sent to the owner, the administrator and the team for its own site only. */
  k?: number[] | null;
  /** AROME orography of the 5 x 5 cells around the site (written by the batch); none for another
   * member's shared place. */
  cells?: Cells | null;
}

/** Line-of-sight Cn2 integrals [m^1/3] per direction at the map K (GET /api/fisheye). */
export interface Fisheye {
  run_time: string;
  /** relief elevation [deg] every 2 degrees of azimuth from north (AROME orography); null without relief */
  horizon?: number[] | null;
  k: number[];
  elevations: number[];
  azimuths: number[];
  frames: {
    lead_hour: number;
    valid_time: string;
    j_low: (number | null)[][];
    j_high: (number | null)[][];
    /** cloud cover 0-1 seen in each direction; null for runs stored without clouds */
    cloud?: (number | null)[][] | null;
  }[];
}

export interface SiteHistory {
  nom: string;
  modele?: string;
  K?: number[];
  episodes: { a: string; b: string; prevu: [string, number | null][]; mediane: [string, number | null][]; brut: [string, number | null][] }[];
  paires: [string, number | null, number | null, boolean][];
  generated_at: string;
}

export interface Measurements {
  times: string[];
  seeing_arcsec: number[];
}
/** Precision of the AROME forecast with the age of the run (lead), night hours, at the site's current K. */
export interface SkillBin {
  age_from: number;
  age_to: number;
  n_hours: number;
  n_nights: number;
  r: number | null;
  bias: number | null;
  mae: number | null;
  /** standard deviation of |forecast - measured| */
  sd: number | null;
  rmse: number | null;
}

/** Night precision: median of a run's forecast hours of a night vs the measured median; age at 00h UTC. */
export interface SkillNight {
  age: number;
  n_nights: number;
  bias: number | null;
  mae: number | null;
  sd: number | null;
}

/** V2bd terms at K = 1 of each valid hour (latest run issued before it). */
export interface Terms {
  valid_times: string[];
  lead_hours: number[];
  i_tke: (number | null)[];
  i_conv: (number | null)[];
  i_cis: (number | null)[];
}

export interface PlaceIn {
  name: string;
  lat: number;
  lon: number;
  altitude_m?: number | null;
  shared?: boolean;
}
export interface PlacePatch {
  name?: string;
  shared?: boolean;
  k_tke?: number;
  k_cis?: number;
  k_conv?: number;
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
  /** Ground altitude of the AROME grid point [m]. */
  model_altitude_m?: number | null;
  /** Model variables {t2, dth, u10, u100, u500, shl, shj, tke}, absent for older forecasts. */
  variables?: Record<string, number | null> | null;
}

export interface Forecast {
  site: Site;
  run_time: string;
  points: ForecastPoint[];
}

/** One-off forecast at any point, read on the global maps (GET /api/point). */
export interface PointForecast {
  run_time: string;
  lat: number;
  lon: number;
  ground_m: number | null;
  k: number[];
  points: { lead_hour: number; valid_time: string; seeing_arcsec: number | null }[];
}

export interface Cn2 {
  site: Site;
  run_time: string;
  valid_times: string[];
  heights_m: number[];
  cn2: (number | null)[][];
  /** true where the convective closure filled the level (same shape as cn2); absent from older APIs */
  conv?: boolean[][];
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
  /** GET /api/map/relief serves the model orography of the grid. */
  relief?: boolean;
}

export type UserRole = "user" | "team" | "admin";

export interface User {
  id: number;
  email: string;
  display_name: string | null;
  role: UserRole;
}

/** Sign-up waiting for the e-mail confirmation (no session yet). */
export interface Pending {
  email: string;
  pending: true;
  /** false: the e-mail could not be sent (offer to send it again). */
  sent: boolean;
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
const send = <T>(method: string, path: string, body: unknown = {}) =>
  request<T>(path, { method, body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });
const post = <T>(path: string, body: unknown = {}) => send<T>("POST", path, body);

export const api = {
  me: () => get<Me>("/api/me"),
  signup: (b: { email: string; password: string; display_name?: string }) => post<User | Pending>("/api/auth/signup", b),
  verifyEmail: (token: string) => post<User>("/api/auth/verify", { token }),
  resendVerification: (email: string) => post<void>("/api/auth/resend", { email }),
  login: (b: { email: string; password: string }) => post<User>("/api/auth/login", b),
  logout: () => post<void>("/api/auth/logout"),
  sites: () => get<Site[]>("/api/sites"),
  createPlace: (b: PlaceIn) => post<Site>("/api/places", b),
  updatePlace: (slug: string, b: PlacePatch) => send<Site>("PATCH", `/api/places/${encodeURIComponent(slug)}`, b),
  deletePlace: (slug: string) => send<void>("DELETE", `/api/places/${encodeURIComponent(slug)}`),
  measurements: (slug: string) => get<Measurements>(`/api/sites/${encodeURIComponent(slug)}/measurements`),
  addMeasurements: (slug: string, points: [string, number][]) =>
    post<{ stored: number; rejected: number }>(`/api/sites/${encodeURIComponent(slug)}/measurements`, { points }),
  /** Calibration settings saved with the place: filters and nights left out. */
  calib: (slug: string) => get<{ pics: boolean; courtes: boolean; top: number; out: string[] }>(`/api/sites/${encodeURIComponent(slug)}/calib`),
  /** Save the K of a site (owner, administrator, team for its site): used from the next run. */
  saveK: (slug: string, b: { k_tke: number; k_cis: number; k_conv: number }) =>
    send<void>("PUT", `/api/sites/${encodeURIComponent(slug)}/k`, b),
  saveCalib: (slug: string, b: { pics: boolean; courtes: boolean; top: number; out: string[] }) =>
    send<void>("PUT", `/api/sites/${encodeURIComponent(slug)}/calib`, b),
  deleteMeasurements: (slug: string, night?: string) =>
    send<void>("DELETE", `/api/sites/${encodeURIComponent(slug)}/measurements${night ? `?night=${night}` : ""}`),
  point: (lat: number, lon: number) => get<PointForecast>(`/api/point?lat=${lat.toFixed(4)}&lon=${lon.toFixed(4)}`),
  fisheye: (lat: number, lon: number, alt?: number | null) =>
    get<Fisheye>(`/api/fisheye?lat=${lat.toFixed(4)}&lon=${lon.toFixed(4)}${alt != null ? `&alt=${Math.round(alt)}` : ""}`),
  /** Research history of a monitored site (periods, hourly pairs); K and integrals only for calibrators. */
  history: (slug: string) => get<SiteHistory>(`/api/sites/${encodeURIComponent(slug)}/history`),
  skill: (slug: string) => get<{ bins: SkillBin[]; nights: SkillNight[] }>(`/api/sites/${encodeURIComponent(slug)}/skill`),
  terms: (slug: string, from: string, to: string) =>
    get<Terms>(`/api/sites/${encodeURIComponent(slug)}/terms?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`),
  latestRun: () => get<Run>("/api/runs/latest"),
  /** view "week": up to 7 days of main runs stitched, then the run. */
  forecast: (slug: string, run = "latest", view: "run" | "week" | "all" = "run") =>
    get<Forecast>(`/api/sites/${encodeURIComponent(slug)}/forecast?run=${encodeURIComponent(run)}&view=${view}`),
  cn2: (slug: string, run = "latest", view: "run" | "week" = "run") =>
    get<Cn2>(`/api/sites/${encodeURIComponent(slug)}/cn2?run=${encodeURIComponent(run)}&view=${view}`),
  map: () => get<MapMeta>("/api/map"),
  /** Model orography of the map grid [m], NaN where undefined. */
  mapRelief: async (run: string): Promise<Float32Array> => {
    const res = await fetch(`/api/map/relief?run=${encodeURIComponent(run)}`, { credentials: "same-origin" });
    if (!res.ok) throw new ApiError(res.status, res.statusText);
    const q = new Uint16Array(await res.arrayBuffer()),
      out = new Float32Array(q.length);
    for (let i = 0; i < q.length; i++) out[i] = q[i] === 65535 ? NaN : q[i]! - 500;
    return out;
  },
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
  forecast: (slug: string, run: string, view = "run") => ["forecast", slug, run, view] as const,
  cn2: (slug: string, run: string, view = "run") => ["cn2", slug, run, view] as const,
  map: (run: string) => ["map", run] as const,
};
