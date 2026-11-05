import { useQuery, useIsFetching } from "@tanstack/react-query";
import { useEffect, useState } from "react";

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

/** Share of a part of the turbulence (boundary layer, or an altitude band above sea level) of every frame of the
 * map (loaded only when asked: the map's turbulence options), by lead hour; a frame without it is absent. */
export function useMapShares(
  meta: MapMeta | undefined,
  enabled: boolean,
  part: "bl" | "z0" | "z1" | "z2" = "bl",
): Map<number, Uint8Array> | undefined {
  const q = useQuery({
    queryKey: ["map-share", meta?.run_time ?? "", part],
    queryFn: async () => {
      const m = meta!;
      const got = await Promise.all(m.frames.map((f) => api.mapShare(m.run_time, f.lead_hour, part).catch(() => null)));
      return new Map(m.frames.flatMap((f, i) => (got[i] ? [[f.lead_hour, got[i]!] as const] : [])));
    },
    enabled: enabled && !!meta,
    staleTime: 30 * 60 * 1000,
    retry: false,
  });
  return q.data;
}

/** True while the global map (or the latest run it depends on) is being loaded and none is shown yet. */
export function useGlobalMapLoading(): boolean {
  const n = useIsFetching({ predicate: (q) => q.queryKey[0] === "map" || (q.queryKey[0] === "runs" && q.queryKey[1] === "latest") });
  return n > 0;
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

/** Usual publication delay of each main AROME cycle by Météo-France [h] (00/06/12/18 UTC), as the batch schedule. */
const PUB_DELAY_H: Record<number, number> = { 0: 2.83, 6: 5.25, 12: 3.92, 18: 5.42 };
/** Computation of a run by the batch, from its hourly firing at h+45 [min]. */
const RUN_COMPUTE_MIN = 40;

/** When the latest run was put on the site, and the estimate of the next update: the next main cycle (6 h later) is
 * published by Météo-France after its usual delay, taken by the first hourly batch firing (h+45) after that, then
 * computed in ~40 min. `next` is null once that time is past (Météo-France late): the next update then comes as
 * soon as the run is published. */
export function useRunUpdates() {
  const { query } = useLatestRunTime();
  // re-evaluated every minute, so that the "up to date" colour goes once the next update is due
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 60000);
    return () => clearInterval(id);
  }, []);
  const fin = query.data?.finished_at;
  const run = query.data?.run_time;
  const updated = fin ? Date.parse(fin) : null;
  let next: number | null = null;
  if (run) {
    const cycle = Date.parse(run) + 6 * 3600000,
      pub = cycle + (PUB_DELAY_H[new Date(cycle).getUTCHours()] ?? 5) * 3600000,
      hour = Math.floor(pub / 3600000) * 3600000,
      firing = hour + 45 * 60000 >= pub ? hour + 45 * 60000 : hour + 105 * 60000;
    next = firing + RUN_COMPUTE_MIN * 60000;
  }
  // fresh: the map is the latest one expected (the next update is not due yet); false once that time has passed
  const due = next != null && next > Date.now() ? next : null;
  return { updated, next: due, fresh: updated != null && due != null };
}
