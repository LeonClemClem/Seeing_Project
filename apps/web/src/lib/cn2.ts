import type { Cn2 } from "../api";
import { CN2_LOG_MAX, CN2_LOG_MIN } from "../config";

export interface Cn2Cells {
  times: number[];
  heights: number[];
  /** [timeIndex, heightIndex, log10(cn2) clamped to the colour range] — null/<=0 values are skipped. */
  cells: [number, number, number][];
}

/** Turn the API matrix into heatmap cells, keeping heights <= maxHeight. */
export function cn2Cells(cn2: Cn2, maxHeight = Infinity): Cn2Cells {
  const keep = cn2.heights_m.map((h, i) => [h, i] as const).filter(([h]) => h <= maxHeight);
  const cells: [number, number, number][] = [];
  cn2.cn2.forEach((row, ti) => {
    keep.forEach(([, hi], yi) => {
      const v = row[hi];
      if (v == null || !(v > 0)) return;
      cells.push([ti, yi, Math.min(CN2_LOG_MAX, Math.max(CN2_LOG_MIN, Math.log10(v)))]);
    });
  });
  return { times: cn2.valid_times.map((t) => Date.parse(t)), heights: keep.map(([h]) => h), cells };
}
