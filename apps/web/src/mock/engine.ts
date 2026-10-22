/**
 * Fictitious seeing model used by the views that have no backend yet (ported from the mockup).
 * Time is an hour index `i` from REF (UTC midnight of today); the mock run is at i = 12 (12Z) and "now" at i = 20.
 * Replace with real endpoints as they appear (see the project-status skill roadmap).
 */
import type { K3 } from "../store";
import { HOUR, isoMin, isNightDate, med, rnd } from "../lib/util";

export const REF = (() => {
  const d = new Date();
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
})();
export const I0 = 12,
  I1 = 54,
  NOW = 20;
export const KDEF: K3 = [9.6, 17.2, 0.1];

export const hhOf = (i: number) => ((i % 24) + 24) % 24;
/** Night for the charts: 17h30–06h UTC. */
export const isN = (i: number) => {
  const h = hhOf(i);
  return h >= 17.5 || h < 6;
};
export const tOfI = (i: number) => REF + i * HOUR;

/** Log-spaced heights 10 m → 10 km. */
export const Z = [...Array(40)].map((_, k) => 10 * Math.pow(10, (3 * k) / 39));
export const hbl = (i: number) => {
  const h = hhOf(i),
    s = Math.sin(((h - 8) / 10) * Math.PI);
  return isN(i) ? 35 + 90 * rnd(i) : Math.max(60, 200 + 1200 * Math.max(0, s));
};
export const conv = (i: number) => !isN(i) && Math.sin(((hhOf(i) - 8) / 10) * Math.PI) > 0.15;

interface Lev {
  bl: number;
  fa: number;
}
const BASE = new Map<number, Lev[]>();
function base(i: number): Lev[] {
  const c = BASE.get(i);
  if (c) return c;
  const H = hbl(i),
    A = isN(i) ? 4e-15 + 6e-15 * rnd(i * 3) : 1e-15 + 1e-15 * rnd(i * 5);
  const v = Z.map((z) => ({
    bl: z <= H ? A * Math.exp(-z / H) : 0,
    fa:
      (z > H ? A * Math.exp(-z / H) : 0) +
      1e-17 * (1 + 0.6 * rnd(i + z)) * (z > H ? 1 : 0.2) +
      (z > H ? 6e-17 * Math.exp(-(((z - 9500) / 1600) ** 2)) * (1 + Math.sin(i / 5)) : 0),
  }));
  BASE.set(i, v);
  return v;
}
export function prof(i: number, K: K3, KCAL: K3) {
  const a = conv(i) ? 1 : K[0] / KCAL[0],
    b = K[1] / KCAL[1];
  return base(i).map((p) => ({ v: p.bl * a + p.fa * b, bl: p.bl * a }));
}
function J(p: { v: number }[]) {
  let s = 0;
  for (let n = 1; n < Z.length; n++) s += ((p[n]!.v + p[n - 1]!.v) / 2) * (Z[n]! - Z[n - 1]!);
  return s;
}
/** Seeing (arcsec) at hour i with K, relative to the place's fitted K. */
export const see = (i: number, K: K3, KCAL: K3) => 0.315 * Math.pow(J(prof(i, K, KCAL)) / 1e-13, 0.6);

export interface Pt {
  t: number;
  v: number;
}
export interface HPt {
  t: number;
  m: number;
}
/** Fake 5-minute measurements between hours i0 and i1, scaled by f. */
export function meas(i0: number, i1: number, f: number): Pt[] {
  const P: Pt[] = [];
  const s0 = (i: number) => see(i, KDEF, KDEF);
  for (let m = Math.round(i0 * 60); m <= i1 * 60; m += 5) {
    const t = m / 60,
      a = Math.floor(t),
      fr = t - a,
      v = (s0(a) * (1 - fr) + s0(a + 1) * fr) * f * (0.75 + 0.5 * rnd(m * 1.7));
    P.push({ t, v: rnd(m * 3.1) > 0.985 ? v * 2.4 : v });
  }
  return P;
}
export function hourly(P: Pt[], i0: number, i1: number): HPt[] {
  const H: HPt[] = [];
  for (let h = Math.ceil(i0); h <= i1; h++) {
    const w = P.filter((p) => Math.abs(p.t - h) <= 0.5).map((p) => p.v);
    if (w.length) H.push({ t: h, m: med(w) });
  }
  return H;
}

export interface Episode {
  a: number;
  b: number;
  P: Pt[];
  H: HPt[];
}
const EP: [number, number][] = [
  [-17 * 24 + 18, -17 * 24 + 27],
  [-6 * 24 + 16, -6 * 24 + 22],
  [-3 * 24 + 18, -3 * 24 + 30],
  [12, NOW],
];
const EPD_CACHE = new Map<number, Episode[]>();
/** Measurement episodes of a mock place; `f` is the place's measurement factor. */
export function episodes(f = 1.0): Episode[] {
  const c = EPD_CACHE.get(f);
  if (c) return c;
  const v = EP.map(([a, b], n) => {
    const P = meas(a, b, f * (n === 3 ? 1.08 : 1.05 + 0.08 * n));
    return { a, b, P, H: hourly(P, a, b) };
  });
  EPD_CACHE.set(f, v);
  return v;
}
/** The current episode (run → now). */
export const currentEpisode = (f = 1.0) => episodes(f)[3]!;

export function nightSegs(idx: number[]): number[][] {
  const out: number[][] = [];
  let s: number[] = [];
  idx.forEach((i) => {
    if (isN(i)) s.push(i);
    else {
      if (s.length > 1) out.push(s);
      s = [];
    }
  });
  if (s.length > 1) out.push(s);
  return out;
}

/* ---------- the "real place" data shape the history/correlation charts consume ---------- */
export type TV = [string, number | null];
export interface LieuEpisode {
  a: string;
  b: string;
  prevu: TV[];
  mediane: TV[];
  brut: TV[];
}
export interface LieuData {
  nom: string;
  modele: string;
  K: K3;
  episodes: LieuEpisode[];
  /** [time, forecast, measured hourly median, is night] */
  paires: [string, number | null, number | null, boolean][];
}

/** Build history/correlation data for a mock place from the fictitious episodes, forecasts with K. */
export function lieuData(nom: string, f: number, K: K3, KCAL: K3): LieuData {
  const iso = (i: number) => isoMin(tOfI(i));
  const eps = episodes(f).map((e) => {
    const prevu: TV[] = [];
    for (let i = e.a; i <= e.b; i++) prevu.push([iso(i), see(i, K, KCAL)]);
    return {
      a: iso(e.a),
      b: iso(e.b),
      prevu,
      mediane: e.H.map((h): TV => [iso(h.t), h.m]),
      brut: e.P.map((p): TV => [isoMin(tOfI(p.t)), p.v]),
    };
  });
  const paires: LieuData["paires"] = [];
  episodes(f).forEach((e) =>
    e.H.forEach((h) => paires.push([iso(h.t), see(h.t, K, KCAL), h.m, isNightDate(new Date(tOfI(h.t)))])),
  );
  return { nom, modele: "V2bd", K, episodes: eps, paires };
}
