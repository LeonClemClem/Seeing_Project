import { useQuery } from "@tanstack/react-query";

import { api, queryKeys, type MapMeta } from "../api";

export function useLatestRunTime() {
  const run = useQuery({ queryKey: queryKeys.latestRun, queryFn: api.latestRun });
  return { runTime: run.data?.run_time, query: run };
}

export interface GlobalMap {
  meta: MapMeta;
  /** Seeing [arcsec] of every frame by lead hour, row-major ny * nx, NaN where undefined. */
  frames: Map<number, Float32Array>;
  /** Model orography of the grid [m] (contour lines), when the run has it. */
  relief?: Float32Array;
}

/** Decode the uint8 log-scale codes of a frame (seeing_core.grid.encode_seeing). */
export function decodeFrame(codes: Uint8Array, meta: MapMeta): Float32Array {
  const a = Math.log(meta.see_min),
    b = Math.log(meta.see_max) - a,
    lut = new Float32Array(256);
  for (let c = 0; c < 255; c++) lut[c] = Math.exp(a + (c / 254) * b);
  lut[255] = NaN;
  const out = new Float32Array(codes.length);
  for (let i = 0; i < codes.length; i++) out[i] = lut[codes[i]!]!;
  return out;
}

/** Share of the boundary-layer turbulence of every frame of the map (loaded only when asked: the map's
 * "Couche limite" / "Au-dessus" options), by lead hour; a frame without it is absent. */
export function useMapShares(meta: MapMeta | undefined, enabled: boolean): Map<number, Uint8Array> | undefined {
  const q = useQuery({
    queryKey: ["map-share", meta?.run_time ?? ""],
    queryFn: async () => {
      const m = meta!;
      const got = await Promise.all(m.frames.map((f) => api.mapShare(m.run_time, f.lead_hour).catch(() => null)));
      return new Map(m.frames.flatMap((f, i) => (got[i] ? [[f.lead_hour, got[i]!] as const] : [])));
    },
    enabled: enabled && !!meta,
    staleTime: 30 * 60 * 1000,
    retry: false,
  });
  return q.data;
}

/** Latest global seeing map with all its frames, or undefined while loading / when there is none. */
export function useGlobalMap(): GlobalMap | undefined {
  const { runTime } = useLatestRunTime();
  const q = useQuery({
    queryKey: queryKeys.map(runTime ?? ""),
    queryFn: async (): Promise<GlobalMap> => {
      const meta = await api.map();
      const [codes, relief] = await Promise.all([
        Promise.all(meta.frames.map((f) => api.mapFrame(meta.run_time, f.lead_hour))),
        meta.relief ? api.mapRelief(meta.run_time).catch(() => undefined) : Promise.resolve(undefined),
      ]);
      return { meta, frames: new Map(meta.frames.map((f, i) => [f.lead_hour, decodeFrame(codes[i]!, meta)])), relief };
    },
    staleTime: 30 * 60 * 1000,
    retry: false,
  });
  return q.data;
}
