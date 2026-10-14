import { describe, expect, it } from "vitest";

import type { Cn2, ForecastPoint } from "../api";
import { SEEING_BANDS } from "../config";
import { cn2Cells } from "./cn2";
import { bestWindow, median, nightIntervals, seeingBand, seeingColor, tonight } from "./seeing";
import { tzOffsetMs } from "./time";

const HOUR = 3_600_000;
const T0 = Date.UTC(2026, 9, 13, 12); // 13 Oct 2026 12:00 UTC

function pts(values: (number | null)[], start = T0): ForecastPoint[] {
  return values.map((v, i) => ({
    lead_hour: i,
    valid_time: new Date(start + i * HOUR).toISOString(),
    seeing_arcsec: v,
    r0_m: 0.1,
    integral_cn2: null,
    h_coulim_m: 300,
  }));
}

describe("seeing thresholds", () => {
  it("classifies on half-open intervals", () => {
    expect(seeingBand(0.6)?.cls).toBe("excellent");
    expect(seeingBand(1.0)?.cls).toBe("good");
    expect(seeingBand(1.49)?.cls).toBe("good");
    expect(seeingBand(1.5)?.cls).toBe("average");
    expect(seeingBand(2.5)?.cls).toBe("poor");
    expect(seeingBand(9)?.cls).toBe("poor");
  });
  it("handles missing values", () => {
    expect(seeingBand(null)).toBeNull();
    expect(seeingBand(Number.NaN)).toBeNull();
    expect(seeingColor(null)).not.toBe(SEEING_BANDS[0]!.color);
    expect(seeingColor(0.5)).toBe(SEEING_BANDS[0]!.color);
  });
});

describe("median", () => {
  it("works for odd, even and empty", () => {
    expect(median([3, 1, 2])).toBe(2);
    expect(median([4, 1, 2, 3])).toBe(2.5);
    expect(median([])).toBeNull();
  });
});

describe("bestWindow", () => {
  it("finds the lowest 3-hour mean", () => {
    const w = bestWindow(pts([2, 2, 1, 0.8, 0.9, 2, 3]));
    expect(w?.start).toBe(T0 + 2 * HOUR);
    expect(w?.end).toBe(T0 + 5 * HOUR);
    expect(w?.mean).toBeCloseTo(0.9);
  });
  it("skips windows containing nulls", () => {
    const w = bestWindow(pts([0.5, null, 0.5, 1, 1, 1]));
    expect(w?.start).toBe(T0 + 2 * HOUR);
    expect(w?.mean).toBeCloseTo(2.5 / 3);
  });
  it("respects the night interval", () => {
    const w = bestWindow(pts([0.5, 0.5, 0.5, 2, 2, 2, 1.5, 1.5]), { start: T0 + 3 * HOUR, end: T0 + 8 * HOUR });
    expect(w?.start).toBe(T0 + 5 * HOUR);
  });
  it("returns null without enough data", () => {
    expect(bestWindow(pts([1, 1]))).toBeNull();
  });
});

describe("night", () => {
  it("finds astronomical night at Saint-Véran in October", () => {
    const nights = nightIntervals(44.7, 6.9, T0, T0 + 24 * HOUR);
    expect(nights).toHaveLength(1);
    const n = nights[0]!;
    // Astronomical dusk ~18:15 UTC, dawn ~04:15 UTC in mid-October.
    expect(new Date(n.start).getUTCHours()).toBeGreaterThanOrEqual(17);
    expect(new Date(n.start).getUTCHours()).toBeLessThanOrEqual(19);
    expect(new Date(n.end).getUTCHours()).toBeGreaterThanOrEqual(3);
    expect(new Date(n.end).getUTCHours()).toBeLessThanOrEqual(5);
  });
  it("tonight summarises the coming night", () => {
    const values = Array.from({ length: 30 }, (_, i) => (i >= 9 && i <= 14 ? 0.7 : 2));
    const s = tonight(pts(values), 44.7, 6.9, T0);
    expect(s).not.toBeNull();
    expect(s!.best).toBe(0.7);
    expect(s!.window?.mean).toBeCloseTo(0.7);
  });
});

describe("timezones", () => {
  it("knows the Paris offset across DST", () => {
    expect(tzOffsetMs(Date.UTC(2026, 6, 1), "Europe/Paris")).toBe(2 * HOUR);
    expect(tzOffsetMs(Date.UTC(2026, 11, 1), "Europe/Paris")).toBe(HOUR);
    expect(tzOffsetMs(Date.UTC(2026, 11, 1), "UTC")).toBe(0);
  });
});

describe("cn2Cells", () => {
  it("log-scales, clamps, skips nulls and cuts heights", () => {
    const data: Cn2 = {
      site: { slug: "x", name: "x", lat: 0, lon: 0, altitude_m: null },
      run_time: "2026-10-13T00:00:00Z",
      valid_times: ["2026-10-13T00:00:00Z"],
      heights_m: [0, 100, 5000],
      cn2: [[1e-15, null, 1e-20]],
    };
    expect(cn2Cells(data, 4000)).toEqual({ times: [Date.UTC(2026, 9, 13)], heights: [0, 100], cells: [[0, 0, -15]] });
    expect(cn2Cells(data).cells).toEqual([
      [0, 0, -15],
      [0, 2, -18],
    ]);
  });
});
