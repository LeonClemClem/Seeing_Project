import SunCalc from "suncalc";

import type { ForecastPoint } from "../api";
import {
  BEST_WINDOW_HOURS,
  NIGHT_SUN_ALTITUDE,
  NIGHT_SUN_ALTITUDE_FALLBACK,
  NO_DATA_COLOR,
  SEEING_BANDS,
  type SeeingBand,
} from "../config";

const HOUR = 3_600_000;

export function seeingBand(seeing: number | null | undefined): SeeingBand | null {
  if (seeing == null || !Number.isFinite(seeing)) return null;
  return SEEING_BANDS.find((b) => seeing < b.max) ?? SEEING_BANDS[SEEING_BANDS.length - 1]!;
}

export function seeingColor(seeing: number | null | undefined): string {
  return seeingBand(seeing)?.color ?? NO_DATA_COLOR;
}

export function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid]! : (s[mid - 1]! + s[mid]!) / 2;
}

export interface Interval {
  start: number; // epoch ms
  end: number;
}

/**
 * Night periods (sun below `altitude`) between `from` and `to`, sampled every 5 minutes.
 * Falls back to nautical night if there is no astronomical night at all in the range.
 */
export function nightIntervals(
  lat: number,
  lon: number,
  from: number,
  to: number,
  altitude = NIGHT_SUN_ALTITUDE,
): Interval[] {
  const step = 5 * 60_000;
  const limit = (altitude * Math.PI) / 180;
  const out: Interval[] = [];
  let start: number | null = null;
  for (let t = from - 12 * HOUR; t <= to + 12 * HOUR; t += step) {
    const dark = SunCalc.getPosition(new Date(t), lat, lon).altitude < limit;
    if (dark && start === null) start = t;
    if (!dark && start !== null) {
      out.push({ start, end: t });
      start = null;
    }
  }
  if (start !== null) out.push({ start, end: to + 12 * HOUR });
  const clipped = out.filter((i) => i.end > from && i.start < to);
  if (clipped.length === 0 && altitude === NIGHT_SUN_ALTITUDE) {
    return nightIntervals(lat, lon, from, to, NIGHT_SUN_ALTITUDE_FALLBACK);
  }
  return clipped;
}

export interface BestWindow {
  start: number; // epoch ms of first point
  end: number; // epoch ms of end of last hour
  mean: number;
  points: ForecastPoint[];
}

/** Best (lowest mean seeing) run of `hours` consecutive hourly points with data, all inside `within`. */
export function bestWindow(
  points: ForecastPoint[],
  within?: Interval,
  hours = BEST_WINDOW_HOURS,
): BestWindow | null {
  const usable = points
    .map((p) => ({ p, t: Date.parse(p.valid_time) }))
    .filter(({ t }) => !within || (t >= within.start - 30 * 60_000 && t + HOUR <= within.end + 30 * 60_000))
    .sort((a, b) => a.t - b.t);
  let best: BestWindow | null = null;
  for (let i = 0; i + hours <= usable.length; i++) {
    const slice = usable.slice(i, i + hours);
    const contiguous = slice.every((s, k) => k === 0 || s.t - slice[k - 1]!.t === HOUR);
    const values = slice.map((s) => s.p.seeing_arcsec);
    if (!contiguous || values.some((v) => v == null || !Number.isFinite(v))) continue;
    const mean = (values as number[]).reduce((a, b) => a + b, 0) / hours;
    if (!best || mean < best.mean) {
      best = { start: slice[0]!.t, end: slice[hours - 1]!.t + HOUR, mean, points: slice.map((s) => s.p) };
    }
  }
  return best;
}

export interface NightSummary {
  night: Interval;
  points: ForecastPoint[];
  best: number | null;
  median: number | null;
  window: BestWindow | null;
}

/** "Tonight": the night in progress, otherwise the next one covered by the forecast. */
export function tonight(
  points: ForecastPoint[],
  lat: number,
  lon: number,
  now: number = Date.now(),
): NightSummary | null {
  if (points.length === 0) return null;
  const times = points.map((p) => Date.parse(p.valid_time));
  const from = Math.min(...times);
  const to = Math.max(...times) + HOUR;
  const nights = nightIntervals(lat, lon, from, to);
  // Skip a night that is (almost) over: at least one best window must still fit in it.
  const nowHour = Math.floor(now / HOUR) * HOUR;
  const found = nights.find((n) => n.end - Math.max(n.start, nowHour) >= BEST_WINDOW_HOURS * HOUR && n.start < to);
  if (!found) return null;
  const night = { start: Math.max(found.start, nowHour), end: found.end };
  const inNight = points.filter((p) => {
    const t = Date.parse(p.valid_time);
    return t >= night.start - 30 * 60_000 && t < night.end;
  });
  const values = inNight.map((p) => p.seeing_arcsec).filter((v): v is number => v != null && Number.isFinite(v));
  return {
    night: found,
    points: inNight,
    best: values.length ? Math.min(...values) : null,
    median: median(values),
    window: bestWindow(points, night),
  };
}

/** Fried parameter r0 in cm for display. */
export function r0cm(r0_m: number | null | undefined): number | null {
  return r0_m == null || !Number.isFinite(r0_m) ? null : r0_m * 100;
}
