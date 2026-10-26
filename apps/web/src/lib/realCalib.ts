/**
 * Calibration of a real place: measured nights from the API, model seeing rebuilt from the V2bd terms
 * stored for every forecast hour (integral of Cn2 = K_TKE * i_tke + K_conv * i_conv + K_CIS * i_cis).
 */
import type { Terms as TermsOut } from "../api";
import type { CalModel } from "../mock/calibration";
import type { K3 } from "../store";
import type { NightPt } from "./csv";

export interface Terms {
  t: number;
  c: number;
  s: number;
}

const LAMBDA = 500e-9;

/** Seeing [arcsec] at 500 nm for K = (K_TKE, K_CIS, K_conv), same formula as seeing_core. */
export function seeTerms(K: K3, x: Terms): number {
  const J = K[0] * x.t + K[2] * x.c + K[1] * x.s;
  if (!(J > 0)) return NaN;
  return 0.98 * LAMBDA * Math.pow(0.423 * (2 * Math.PI / LAMBDA) ** 2 * J, 0.6) * 206265;
}

const H = 3600000;
const noon = (night: string) => Date.parse(night + "T12:00:00Z");
/** UTC hour "YYYY-MM-DDTHH" of hour index h (0 = 12h UTC) of a night. */
export const nightHourIso = (night: string, h: number) => new Date(noon(night) + h * H).toISOString().slice(0, 13);

/** Measurements grouped by night (key = date of the evening; x = hours since 12h UTC), as parseCsv. */
export function nightsFromTimes(times: string[], values: number[]): Map<string, NightPt[]> {
  const out = new Map<string, NightPt[]>();
  times.forEach((t, i) => {
    const ms = Date.parse(t),
      key = new Date(ms - 12 * H).toISOString().slice(0, 10);
    if (!out.has(key)) out.set(key, []);
    out.get(key)!.push({ x: (ms - noon(key)) / H, v: values[i]! });
  });
  return out;
}

/** Points of parsed nights as [ISO UTC time, seeing] for the upload (inverse of nightsFromTimes). */
export function nightPointsToIso(nights: Map<string, NightPt[]>): [string, number][] {
  const out: [string, number][] = [];
  nights.forEach((pts, key) => pts.forEach((p) => out.push([new Date(noon(key) + Math.round(p.x * 60) * 60000).toISOString(), p.v])));
  return out;
}

/** Calibration model of a real place from its terms. */
export function termsModel(t: TermsOut, k0: K3): CalModel<Terms> {
  const byHour = new Map<string, Terms>();
  t.valid_times.forEach((v, i) => {
    const a = t.i_tke[i],
      b = t.i_conv[i],
      c = t.i_cis[i];
    if (a != null && b != null && c != null) byHour.set(v.slice(0, 13), { t: a, c: b, s: c });
  });
  return { comp: (night, h) => byHour.get(nightHourIso(night, h)), see: seeTerms, k0 };
}
