/**
 * Mock K calibration (mockup's comp / seeC / calib / cstats): each night has fictitious turbulence
 * components; K_TKE and K_CIS are fitted independently on night hours (17h30–06h UTC), K_conv stays at 0.1.
 * Optional filters (mockup's calFiltre / calibReal): sparse hourly medians, short nights, and the hours
 * furthest above the model (removed after a first fit, then refit).
 */
import type { NightPt } from "../lib/csv";
import { corr, hash, med, rnd } from "../lib/util";
import type { K3 } from "../store";
import { KDEF } from "./engine";

export interface Comp {
  t: number;
  c: number;
}
/** Fictitious hourly components (TKE and shear) of a night, 12h → 12h UTC. */
export function comp(key: string): Comp[] {
  const s = hash(key),
    a: Comp[] = [];
  for (let i = 0; i <= 24; i++) a.push({ t: 0.03 + 0.07 * rnd(s + i) + 0.03 * Math.sin(i / 2 + s), c: 0.008 + 0.012 * rnd(s * 2 + i) });
  return a;
}
export const seeC = (K: K3, c: Comp) => Math.pow(K[0] * c.t + K[1] * c.c, 0.6) * 0.85;
/** Night hour on the 12h-based axis. */
export const isNx = (x: number) => {
  const hh = (12 + x) % 24;
  return hh >= 17.5 || hh < 6;
};

/** Hourly medians of a night; `n` = number of measurements behind each median. */
export function chourly(pts: NightPt[]) {
  const H: { h: number; m: number; n: number }[] = [];
  for (let h = 0; h <= 24; h++) {
    const w = pts.filter((p) => Math.abs(p.x - h) <= 0.5).map((p) => p.v);
    if (w.length) H.push({ h, m: med(w), n: w.length });
  }
  return H;
}

/** Longest run of consecutive hours. */
function longestRun(hours: number[]) {
  const h = [...hours].sort((a, b) => a - b);
  let best = h.length ? 1 : 0,
    cur = 1;
  for (let i = 1; i < h.length; i++) {
    cur = h[i]! - h[i - 1]! === 1 ? cur + 1 : 1;
    best = Math.max(best, cur);
  }
  return best;
}

/** Example night of 5-minute measurements as CSV text (UTC). */
export function exampleCsv(n: number): string {
  const d = new Date(Date.UTC(2026, 8, 28 + n)),
    key = d.toISOString().slice(0, 10),
    C = comp(key);
  let t = "date_TU;seeing_arcsec\n";
  for (let m = 17 * 60; m <= 31 * 60; m += 5) {
    const x = m / 60 - 12,
      i = Math.min(Math.floor(x), 23),
      f = x - i,
      a = C[i]!,
      b = C[i + 1]!;
    let v = seeC([14, 24, 0.1], { t: a.t * (1 - f) + b.t * f, c: a.c * (1 - f) + b.c * f }) * (0.8 + 0.4 * rnd(m + n * 999));
    if (rnd(m * 7 + n) > 0.985) v *= 2.5;
    t += new Date(d.getTime() + m * 60000).toISOString().slice(0, 16).replace("T", " ") + ";" + v.toFixed(2) + "\n";
  }
  return t;
}

export interface CalPair<C = Comp> {
  c: C;
  m: number;
  key: string; // night|hour, see hourKey
}

/** Model behind a calibration: the terms of each night hour and the seeing they give for some K. */
export interface CalModel<C> {
  comp: (night: string, h: number) => C | undefined;
  see: (K: K3, c: C) => number;
  /** K in service (dashed curve, start of the fit). */
  k0: K3;
}
export const MOCK_MODEL: CalModel<Comp> = { comp: (night, h) => comp(night)[h], see: seeC, k0: KDEF };
export const hourKey = (night: string, h: number) => `${night}|${h}`;

/** Calibration filters: sparse medians (< half the usual number of measurements of the night), nights
 * without 3 successive compared hours, and the `top` % of hours furthest above the model. */
export interface CalFilters {
  pics: boolean;
  courtes: boolean;
  top: number;
  /** nights (date of the evening) left out of the fit by hand */
  out: string[];
}
export const NO_FILTER: CalFilters = { pics: false, courtes: false, top: 0, out: [] };
export interface CalRemoved {
  pics: number;
  courtes: number;
  top: number;
  /** nights left out by hand that had compared hours */
  out: number;
  rm: Set<string>; // hourKey of every night hour left out of the fit
  /** hourKey of the hours left out by the "above the model" filter (drawn with their threshold line) */
  topRm: Set<string>;
}

export function calib<C = Comp>(
  nights: Map<string, NightPt[]>,
  f: CalFilters = NO_FILTER,
  model: CalModel<C> = MOCK_MODEL as unknown as CalModel<C>,
): { P: CalPair<C>[]; K: K3; mode: string; F: CalRemoved; R: CalPair<C>[] } {
  const all: CalPair<C>[] = [];
  const F: CalRemoved = { pics: 0, courtes: 0, top: 0, out: 0, rm: new Set(), topRm: new Set() };
  const outs = new Set(f.out ?? []);
  const R: CalPair<C>[] = []; // pairs left out of the fit (filters, nights left out)
  const seeC = model.see;
  nights.forEach((pts, key) => {
    // only the hours with model terms are compared
    const H = chourly(pts).filter((p) => isNx(p.h) && model.comp(key, p.h) !== undefined);
    const usual = med(H.map((p) => p.n));
    let kept = H;
    if (outs.has(key) && H.length) {
      F.out++;
      kept = [];
    }
    if (f.pics) {
      kept = kept.filter((p) => p.n >= 0.5 * usual);
      F.pics += H.length - kept.length;
    }
    if (f.courtes && kept.length && longestRun(kept.map((p) => p.h)) < 3) {
      F.courtes++;
      kept = [];
    }
    const keptH = new Set(kept.map((p) => p.h));
    H.forEach((p) => {
      const pair = { c: model.comp(key, p.h)!, m: p.m, key: hourKey(key, p.h) };
      if (keptH.has(p.h)) all.push(pair);
      else {
        F.rm.add(pair.key);
        R.push(pair);
      }
    });
  });
  let { P, K, mode } = fit(all, model);
  if (f.top > 0 && P.length > 1) {
    const nd = Math.min(P.length - 1, Math.max(1, Math.round((P.length * f.top) / 100)));
    const drop = new Set(
      [...P]
        .sort((a, b) => b.m - seeC(K, b.c) - (a.m - seeC(K, a.c)))
        .slice(0, nd)
        .map((p) => p.key),
    );
    F.top = drop.size;
    drop.forEach((k) => {
      F.rm.add(k);
      F.topRm.add(k);
    });
    R.push(...P.filter((p) => drop.has(p.key)));
    ({ P, K, mode } = fit(P.filter((p) => !drop.has(p.key)), model));
  }
  return { P, K, mode, F, R };
}

function fit<C>(P: CalPair<C>[], model: CalModel<C>): { P: CalPair<C>[]; K: K3; mode: string } {
  if (!P.length) return { P, K: [...model.k0], mode: "aucune mesure" };
  const err = (K: K3) => P.reduce((s, p) => s + Math.abs(Math.log(model.see(K, p.c) / p.m)), 0) / P.length;
  let best = 1e9,
    K: K3 = [...model.k0];
  for (let i = 0; i <= 48; i++)
    for (let j = 0; j <= 48; j++) {
      const k: K3 = [0.01 * Math.pow(15000, i / 48), 0.01 * Math.pow(15000, j / 48), model.k0[2]],
        e = err(k);
      if (e < best) {
        best = e;
        K = k;
      }
    }
  return { P, K, mode: "K_TKE et K_CIS indépendants" };
}

export function cstats<C = Comp>(P: CalPair<C>[], K: K3, see: (K: K3, c: C) => number = seeC as unknown as (K: K3, c: C) => number) {
  if (!P.length) return { r: NaN, b: NaN, q: NaN };
  const o = P.map((p) => p.m),
    pr = P.map((p) => see(K, p.c));
  return {
    r: corr(o, pr),
    b: pr.reduce((s, v, i) => s + v - o[i]!, 0) / o.length,
    q: Math.sqrt(pr.reduce((s, v, i) => s + (v - o[i]!) ** 2, 0) / o.length),
  };
}
