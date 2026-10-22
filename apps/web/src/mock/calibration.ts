/**
 * Mock K calibration (mockup's comp / seeC / calib / cstats): each night has fictitious turbulence
 * components; K_TKE and K_CIS are fitted independently on night hours (17h30–06h UTC), K_conv stays at 0.1.
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

export function chourly(pts: NightPt[]) {
  const H: { h: number; m: number }[] = [];
  for (let h = 0; h <= 24; h++) {
    const w = pts.filter((p) => Math.abs(p.x - h) <= 0.5).map((p) => p.v);
    if (w.length) H.push({ h, m: med(w) });
  }
  return H;
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

export interface CalPair {
  c: Comp;
  m: number;
}

export function calib(nights: Map<string, NightPt[]>): { P: CalPair[]; K: K3; mode: string } {
  const P: CalPair[] = [];
  nights.forEach((pts, key) => {
    const C = comp(key);
    chourly(pts).forEach((p) => {
      if (isNx(p.h)) P.push({ c: C[p.h]!, m: p.m });
    });
  });
  if (!P.length) return { P, K: [...KDEF], mode: "aucune mesure" };
  const err = (K: K3) => P.reduce((s, p) => s + Math.abs(Math.log(seeC(K, p.c) / p.m)), 0) / P.length;
  let best = 1e9,
    K: K3 = [...KDEF];
  for (let i = 0; i <= 48; i++)
    for (let j = 0; j <= 48; j++) {
      const k: K3 = [0.01 * Math.pow(15000, i / 48), 0.01 * Math.pow(15000, j / 48), 0.1],
        e = err(k);
      if (e < best) {
        best = e;
        K = k;
      }
    }
  return { P, K, mode: "K_TKE et K_CIS indépendants" };
}

export function cstats(P: CalPair[], K: K3) {
  if (!P.length) return { r: NaN, b: NaN, q: NaN };
  const o = P.map((p) => p.m),
    pr = P.map((p) => seeC(K, p.c));
  return {
    r: corr(o, pr),
    b: pr.reduce((s, v, i) => s + v - o[i]!, 0) / o.length,
    q: Math.sqrt(pr.reduce((s, v, i) => s + (v - o[i]!) ** 2, 0) / o.length),
  };
}
