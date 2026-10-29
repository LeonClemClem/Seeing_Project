/** Charts over real API data: forecast seeing, Cn² panel, Cn² profile and model variables (mockup's prevReal / lxCn2 / cn2Profile / prevVars). */
import type { Cn2, Forecast } from "../api";
import { tr } from "../i18n";
import {
  C_AR,
  C_DAY,
  C_LINE,
  C_OBS,
  C_OBSD,
  C_TXT,
  ddmm,
  dnText,
  HOUR,
  isNightDate,
  medCurve,
  pad2,
  pl,
  runLabel,
  turbo,
  yaxis,
} from "../lib/util";

const ms = (s: string) => Date.parse(s);

/** Forecast seeing of the latest run (night only, daytime drawn at half width). viewBox 0 0 900 220. */
/** Real seeing forecast; `obs` = measured hourly medians by UTC hour [ms] (squares), `raw` = raw measurements
 * [ms, arcsec] (dots), drawn as the mock-up following the measurement chips. */
export function prevRealSvg(
  fc: Forecast,
  kLabel: string,
  obs?: Map<number, number>,
  raw: [number, number][] = [],
  mesf = { brut: true, horaire: true, courbe: true },
) {
  const pts = fc.points.filter((p) => p.lead_hour > 0).sort((a, b) => a.lead_hour - b.lead_hour);
  if (!pts.length)
    return `<text x="450" y="110" text-anchor="middle" font-size="13" fill="${C_TXT}">${tr("Pas de prévision enregistrée pour ce lieu.")}</text>`;
  const t0 = ms(pts[0]!.valid_time),
    n = Math.round((ms(pts[pts.length - 1]!.valid_time) - t0) / HOUR) + 1;
  const W = 900,
    H = 220,
    L = 36,
    R = 10,
    T = 12,
    B = 30,
    pw = W - L - R,
    ph = H - T - B,
    tt = (i: number) => new Date(t0 + i * HOUR);
  const wt = (i: number) => (isNightDate(tt(i)) ? 1 : 0.5),
    cum = [0];
  for (let i = 0; i < n; i++) cum.push(cum[i]! + wt(i));
  const X = (x: number) => {
    const k = Math.max(0, Math.min(n - 1, Math.floor(x)));
    return L + ((x <= 0 ? 0 : x >= n ? cum[n]! : cum[k]! + (x - k) * wt(k)) / cum[n]!) * pw;
  };
  const sv: [number, number][] = [];
  pts.forEach((p) => {
    const i = Math.round((ms(p.valid_time) - t0) / HOUR);
    if (p.seeing_arcsec != null && p.seeing_arcsec > 0 && isNightDate(tt(i))) sv.push([i, p.seeing_arcsec]);
  });
  const ob: [number, number][] = [];
  obs?.forEach((v, t) => {
    const i = Math.round((t - t0) / HOUR);
    if (i >= 0 && i < n && isNightDate(tt(i))) ob.push([i, v]);
  });
  ob.sort((a, b) => a[0] - b[0]);
  const rw = raw
    .map(([t, v]): [number, number] => [(t - t0) / HOUR, v])
    .filter(([x, v]) => v > 0 && x >= -0.5 && x < n - 0.5 && isNightDate(new Date(t0 + x * HOUR)));
  const ymax = Math.max(3, Math.ceil(Math.max(...sv.map((p) => p[1]), ...ob.map((p) => p[1]), 0) * 1.15)),
    Y = (v: number) => T + ph - (Math.min(v, ymax) / ymax) * ph;
  let g = "",
    s0 = 0,
    cur: boolean | null = null;
  for (let i = 0; i <= n; i++) {
    const nn: boolean = i < n ? isNightDate(tt(i)) : !cur;
    if (i < n && !nn) g += `<rect x="${X(i)}" y="${T}" width="${X(i + 1) - X(i) + 0.5}" height="${ph}" fill="${C_DAY}"/>`;
    if (cur === null) {
      cur = nn;
      s0 = i;
    } else if (nn !== cur || i === n) {
      if (i - s0 >= 3) g += dnText((X(s0) + X(i)) / 2, T + 13, cur);
      cur = nn;
      s0 = i;
    }
  }
  g += yaxis(Y, L, W - R, ymax, ymax > 8 ? 2 : 1);
  for (let i = 0; i <= n; i++) {
    const d = tt(i),
      hh = d.getUTCHours();
    g += `<line x1="${X(i)}" x2="${X(i)}" y1="${T + ph}" y2="${T + ph + 4}" stroke="${C_LINE}"/>`;
    if (hh % (isNightDate(d) ? 2 : 4) === 0 && i < n)
      g += `<text x="${X(i)}" y="${T + ph + 16}" text-anchor="middle" font-size="11" fill="${hh === 0 ? "#e6ebf6" : C_TXT}" ${hh === 0 ? 'font-weight="500"' : ""}>${hh === 0 ? ddmm(d) : hh}</text>`;
  }
  let seg: number[][] = [],
    prev = -2;
  const fl = () => {
    if (seg.length > 1) g += pl(seg, `stroke="${C_AR}" stroke-width="2.2"`);
    else if (seg.length === 1) g += `<circle cx="${seg[0]![0]}" cy="${seg[0]![1]}" r="3" fill="${C_AR}"/>`; // isolated hour
    seg = [];
  };
  sv.forEach(([i, v]) => {
    if (i !== prev + 1) fl();
    seg.push([X(i + 0.5), Y(v)]);
    prev = i;
  });
  fl();
  if (mesf.brut) rw.forEach(([x, v]) => (g += `<circle cx="${X(x + 0.5)}" cy="${Y(v)}" r="1.7" fill="${C_OBS}"/>`));
  if (mesf.courbe) g += medCurve(ob.map(([i, v]): [number, number, number] => [X(i + 0.5), Y(v), i]));
  if (mesf.horaire)
    ob.forEach(([i, v]) => (g += `<rect x="${X(i + 0.5) - 5.5}" y="${Y(v) - 5.5}" width="11" height="11" fill="${C_OBSD}" stroke="#0a0f1d" stroke-width="1"/>`));
  if (sv.length) {
    const [li, lv] = sv.reduce((m, q) => (q[1] > m[1] ? q : m));
    g += `<text x="${X(li + 0.5)}" y="${Y(lv) - 9}" text-anchor="middle" font-size="13" font-weight="700" fill="${C_AR}" stroke="#0a0f1d" stroke-width="3.5" paint-order="stroke">Seeing AROME</text>`;
  }
  g += `<line x1="${X(0)}" x2="${X(0)}" y1="${T}" y2="${T + ph}" stroke="#f2c14e" stroke-width="1.6" stroke-dasharray="5 3"/><text x="${X(0) + 4}" y="${T + ph - 6}" font-size="11" fill="#f2c14e">run ${runLabel(ms(fc.run_time))} · ${tr(kLabel)}</text>`;
  return g;
}

export const CN2ALT: Record<string, [number, number]> = { bl: [0, 1000], "4": [0, 4000], jet: [8000, 16000], tout: [0, 16000] };

export interface Cn2Ctx {
  W: number;
  H: number;
  L: number;
  T: number;
  pw: number;
  ph: number;
  n: number;
  za: number;
  zb: number;
  lo: number;
  hi: number;
  times: number[];
  heights: number[];
  /** log10 Cn², [time][height], null when missing */
  lg: (number | null)[][];
  hc: (number | null)[];
  see: (number | null)[];
  /** Measured hourly median seeing at each time, null when none. */
  obs: (number | null)[];
  /** Raw measurements in the panel: [position in hours from the first time, arcsec]. */
  raw: [number, number][];
  /** Which measurements are drawn (chips "brutes / médianes horaires / courbe médiane horaire"). */
  mesf: { brut: boolean; horaire: boolean; courbe: boolean };
  /** Ground altitude of the AROME grid point [m] (the jet stream is at 8-16 km of real altitude). */
  sol: number;
}

/** Prepare the Cn² matrix once per (data, altitude range). The "jet" range is 8-16 km of real altitude,
 * i.e. above the ground of the grid point. */
export function cn2Ctx(
  cn: Cn2,
  fc: Forecast | undefined,
  alt: string,
  obs?: Map<number, number>,
  zoom = 1,
  raw: [number, number][] = [],
  mesf = { brut: true, horaire: true, courbe: true },
): Cn2Ctx {
  // zoom: the panel gets wider (same height), the page scrolls it horizontally, as in the mock-up
  const W = Math.round(900 * zoom);
  const sol = fc?.points.find((p) => p.model_altitude_m != null)?.model_altitude_m ?? 0;
  const [za0, zb1] = CN2ALT[alt] ?? CN2ALT["4"]!,
    za = alt === "jet" ? Math.max(0, za0 - sol) : za0,
    zb0 = alt === "jet" ? zb1 - sol : zb1;
  const heights = cn.heights_m,
    zb = Math.min(zb0, Math.max(...heights));
  // one column per hour from the first to the last profile: the panel is drawn by hour index, so the hours
  // missing in the stitched series (runs without profiles) must stay as empty columns, else everything after
  // a gap shifts to the left (the raw measurements, placed by time, then no longer line up)
  const t0 = cn.valid_times.length ? ms(cn.valid_times[0]!) : 0,
    nh = cn.valid_times.length ? Math.round((ms(cn.valid_times[cn.valid_times.length - 1]!) - t0) / HOUR) + 1 : 0,
    times = Array.from({ length: nh }, (_, i) => t0 + i * HOUR),
    rowAt = new Map(cn.valid_times.map((s, k) => [ms(s), k]));
  const lg = times.map((tm) => {
    const k = rowAt.get(tm);
    return k == null ? heights.map(() => null) : cn.cn2[k]!.map((v) => (v != null && v > 0 ? Math.log10(v) : null));
  });
  const a: number[] = [];
  lg.forEach((row) => row.forEach((v, k) => v != null && heights[k]! <= 4000 && a.push(v)));
  a.sort((x, y) => x - y);
  const lo = a.length ? a[Math.floor(a.length * 0.05)]! : -18,
    hi = a.length ? a[Math.floor(a.length * 0.995)]! : -13;
  const byT = new Map((fc?.points ?? []).map((p) => [ms(p.valid_time), p]));
  return {
    W,
    H: 400,
    L: 68,
    T: 46,
    pw: W - 68 - 32,
    ph: 400 - 46 - 56,
    n: times.length,
    za,
    zb,
    lo,
    hi: hi > lo ? hi : lo + 1,
    times,
    heights,
    lg,
    hc: times.map((t) => byT.get(t)?.h_coulim_m ?? null),
    see: times.map((t) => {
      const s = byT.get(t)?.seeing_arcsec;
      return s != null && s > 0 && isNightDate(new Date(t)) ? s : null;
    }),
    // night only (17h30-06h UTC): no daytime measurement anywhere on the site
    obs: times.map((t) => (isNightDate(new Date(t)) ? (obs?.get(t) ?? null) : null)),
    // night only, as everywhere on the site
    raw: raw
      .filter(([t, v]) => v > 0 && t >= (times[0] ?? 0) - HOUR / 2 && t < (times[times.length - 1] ?? 0) + HOUR / 2 && isNightDate(new Date(t)))
      .map(([t, v]): [number, number] => [(t - (times[0] ?? 0)) / HOUR, v]),
    mesf,
    sol,
  };
}

/** Jet stream of a profile (log10 Cn² by height): a clear local Cn² peak between 8 and 16 km of real
 * altitude, at least 0.3 decade above the minimum of the 4 km - peak range and of the 3 km above it
 * (same rule as the mock-up). Returns its height above ground and log10 Cn², or null. */
export function jetStream(c: Cn2Ctx, i: number): { z: number; v: number } | null {
  const row = c.lg[i];
  if (!row) return null;
  const P = c.heights.map((z, k) => [z, row[k]] as const).filter((q): q is readonly [number, number] => q[1] != null);
  const J = P.filter(([z]) => z >= 8000 - c.sol && z <= 16000 - c.sol);
  if (J.length <= 2) return null;
  const [zj, vj] = J.reduce((m, q) => (q[1] > m[1] ? q : m));
  const ki = P.findIndex((q) => q[0] === zj),
    low = P.filter(([z]) => z >= 4000 - c.sol && z < zj).map((q) => q[1]),
    up = P.filter(([z]) => z > zj && z <= zj + 3000).map((q) => q[1]);
  const local = ki > 0 && ki < P.length - 1 && vj >= P[ki - 1]![1] && vj >= P[ki + 1]![1];
  if (!local || !low.length || !up.length || vj - Math.min(...low) < 0.3 || vj - Math.min(...up) < 0.3) return null;
  return { z: zj, v: vj };
}

/** Cn² panel: turbo heatmap (log10, interpolated vertically, and in time between two neighbouring hours for the
 * picture only), boundary layer, night seeing on the right axis. */
export function cn2RealSvg(c: Cn2Ctx, runMs: number) {
  const { W, L, T, pw, ph, n, za, zb, lo, hi, times, heights: Zh } = c;
  if (!n) return `<text x="450" y="190" text-anchor="middle" font-size="13" fill="${C_TXT}">${tr("Pas de panneau Cn² enregistré pour ce lieu.")}</text>`;
  const X = (i: number) => L + (i / n) * pw,
    Yz = (z: number) => T + ph - ((Math.min(Math.max(z, za), zb) - za) / (zb - za)) * ph;
  let g = `<rect x="${L}" y="${T}" width="${pw}" height="${ph}" fill="#262c3b"/>`;
  {
    // S image columns per hour: between the centres of two neighbouring hours the log10 Cn² is blended linearly
    // (display only: hover, profile and values keep the hourly data). Next to a missing hour, the existing hour
    // fills its own column only, as before: gaps are never filled.
    const NR = Math.max(120, Math.round(ph * 1.5)),
      S = Math.max(1, Math.min(8, Math.floor(4000 / n))),
      NW = n * S,
      cv = document.createElement("canvas");
    cv.width = NW;
    cv.height = NR;
    const cx = cv.getContext("2d");
    if (cx) {
      const im = cx.createImageData(NW, NR),
        D = im.data;
      const at = (i: number, k: number, z: number) => {
        const row = c.lg[i];
        const a = row?.[k],
          b = row?.[k + 1];
        return a == null || b == null ? null : a + ((b - a) * (z - Zh[k]!)) / (Zh[k + 1]! - Zh[k]!);
      };
      let k = 0;
      for (let r = NR - 1; r >= 0; r--) {
        const z = za + ((zb - za) * (NR - 1 - r + 0.5)) / NR;
        if (z < Zh[0]! || z > Zh[Zh.length - 1]!) continue;
        while (k < Zh.length - 2 && Zh[k + 1]! < z) k++;
        for (let x = 0; x < NW; x++) {
          const t = (x + 0.5) / S - 0.5,
            i0 = Math.floor(t),
            f = t - i0,
            a = i0 >= 0 ? at(i0, k, z) : null,
            b = i0 + 1 < n ? at(i0 + 1, k, z) : null;
          const v = a != null && b != null ? a + (b - a) * f : f < 0.5 ? a : b;
          if (v == null) continue;
          const q = turbo((v - lo) / (hi - lo)),
            p = (r * NW + x) * 4;
          D[p] = q[0];
          D[p + 1] = q[1];
          D[p + 2] = q[2];
          D[p + 3] = 255;
        }
      }
      cx.putImageData(im, 0, 0);
      g += `<image href="${cv.toDataURL()}" x="${L}" y="${T}" width="${pw}" height="${ph}" preserveAspectRatio="none" style="image-rendering:pixelated"/>`;
    }
  }
  const hcs: number[][][] = [];
  let sg: number[][] = [];
  for (let i = 0; i < n; i++) {
    const h = c.hc[i];
    if (h != null) sg.push([X(i + 0.5), Yz(h)]);
    else {
      if (sg.length > 1) hcs.push(sg);
      sg = [];
    }
  }
  if (sg.length > 1) hcs.push(sg);
  hcs.forEach((s) => (g += pl(s, 'stroke="#000" stroke-width="5"') + pl(s, 'stroke="#ff2bd6" stroke-width="2.8"')));
  {
    const lab = hcs.flat().find((p) => p[1]! > T + 14 && p[1]! < T + ph - 6 && p[0]! > L + 40 && p[0]! < L + pw - 140);
    if (lab)
      g += `<text x="${lab[0]! + 4}" y="${lab[1]! - 6}" font-size="12" font-weight="500" fill="#ff2bd6" stroke="#000" stroke-width="3" paint-order="stroke">boundary layer</text>`;
  }
  const step = zb - za > 8000 ? 2000 : zb - za > 2000 ? 500 : 100;
  for (let z = Math.ceil(za / step) * step; z <= zb; z += step)
    g += `<line x1="${L - 4}" x2="${L}" y1="${Yz(z)}" y2="${Yz(z)}" stroke="${C_TXT}"/><text x="${L - 7}" y="${Yz(z) + 5}" text-anchor="end" font-size="13" fill="${C_TXT}">${z >= 1000 ? z / 1000 : z}<tspan font-weight="700"> ${z >= 1000 ? "km" : "m"}</tspan></text>`;
  g += `<text x="13" y="${T + ph / 2}" text-anchor="middle" font-size="13" fill="${C_TXT}" transform="rotate(-90 13 ${T + ph / 2})" font-weight="700">${tr("Altitude au-dessus du sol")}</text>`;
  const tstep = n > 96 ? 3 : 1,
    lstep = n > 96 ? 12 : n > 36 ? 3 : 2;
  for (let i = 0; i <= n; i++) {
    const d = new Date((times[0] ?? 0) + i * HOUR),
      hh = d.getUTCHours();
    if (hh % tstep) continue;
    g += `<line x1="${X(i)}" x2="${X(i)}" y1="${T + ph}" y2="${T + ph + (hh % lstep ? 3 : 5)}" stroke="${C_TXT}"/>`;
    if (hh % lstep === 0 && i < n)
      g += `<text x="${X(i)}" y="${T + ph + 20}" text-anchor="middle" font-size="13" fill="${hh === 0 ? "#e6ebf6" : C_TXT}" ${hh === 0 ? 'font-weight="500"' : ""}>${hh === 0 ? ddmm(d) : hh + "h"}</text>`;
    if ((hh === 0 || hh === 12) && i < n)
      g += `<text x="${X(i)}" y="${T + ph + 37}" text-anchor="middle" font-size="12" font-weight="600" fill="${hh === 12 ? "#f2c14e" : "#9cc7ff"}">${tr(hh === 12 ? "Jour" : "Nuit")}</text>`;
  }
  const SEE = c.see.map((s, i) => [i, s] as const).filter((q): q is readonly [number, number] => q[1] != null);
  const OBS = c.obs.map((s, i) => [i, s] as const).filter((q): q is readonly [number, number] => q[1] != null);
  const smax = Math.max(2, Math.max(...SEE.map((p) => p[1]), ...OBS.map((p) => p[1]), 0) * 1.2),
    YS = (v: number) => T + ph - (Math.min(v, smax) / smax) * ph;
  let seg: number[][] = [],
    prev: number | null = null;
  const fl = () => {
    if (seg.length > 1) g += pl(seg, 'stroke="#fff" stroke-width="5.6"') + pl(seg, 'stroke="#1f6bff" stroke-width="3"');
    else if (seg.length === 1) g += `<circle cx="${seg[0]![0]}" cy="${seg[0]![1]}" r="3.4" fill="#1f6bff" stroke="#fff" stroke-width="1.3"/>`; // isolated hour
    seg = [];
  };
  SEE.forEach(([i, s]) => {
    if (prev != null && i !== prev + 1) fl();
    seg.push([X(i + 0.5), YS(s)]);
    prev = i;
  });
  fl();
  // measurements on the same right axis, white with a black outline (legend): raw points, hourly median curve,
  // hourly medians
  if (c.mesf.brut)
    c.raw.forEach(([x, s]) => (g += `<circle cx="${X(x + 0.5)}" cy="${YS(s)}" r="1.7" fill="#fff" stroke="#000" stroke-width="0.5"/>`));
  if (c.mesf.courbe) {
    const q = OBS.map(([i, s]): [number, number, number] => [X(i + 0.5), YS(s), i]);
    g += medCurve(q, 'stroke="#000" stroke-width="4"') + medCurve(q, 'stroke="#fff" stroke-width="2"');
  }
  if (c.mesf.horaire)
    OBS.forEach(([i, s]) => (g += `<circle cx="${X(i + 0.5)}" cy="${YS(s)}" r="3.4" fill="#fff" stroke="#000" stroke-width="1"/>`));
  {
    const cand = SEE.map(([i, s]) => [X(i + 0.5), YS(s)] as const).filter(([x, y]) => x > L + 20 && x < L + pw - 120 && y > T + 22),
      p = cand.length ? cand.reduce((m, q) => (q[1] < m[1] ? q : m)) : null;
    if (p)
      g += `<text x="${p[0] + 6}" y="${p[1] - 10}" font-size="13" font-weight="700" fill="#1f6bff" stroke="#fff" stroke-width="3.5" paint-order="stroke">Seeing AROME</text>`;
  }
  const sst = smax > 8 ? 2 : smax > 3 ? 1 : 0.5;
  for (let v = 0; v <= smax; v += sst)
    g += `<text x="${L + pw + 3}" y="${YS(v) + 5}" font-size="13" fill="${C_TXT}">${+v.toFixed(1)}<tspan font-weight="700">″</tspan></text>`;
  g += `<text x="${W - 1}" y="${T - 7}" text-anchor="end" font-size="13" font-weight="700" fill="${C_TXT}">Seeing (″)</text>`;
  const xl = X((runMs - (times[0] ?? 0)) / HOUR);
  if (xl >= L && xl <= L + pw)
    g += `<line x1="${xl}" x2="${xl}" y1="${T}" y2="${T + ph}" stroke="#f2c14e" stroke-width="1.6" stroke-dasharray="5 3"/><text x="${xl + 5}" y="${T + 15}" font-size="12" fill="#f2c14e" stroke="#000" stroke-width="3" paint-order="stroke">${tr("dernier run")} ${runLabel(runMs)}</text>`;
  const bw = Math.min(300, pw * 0.45),
    bx = L + pw - bw - 80,
    by = 4,
    bh = 9;
  for (let k = 0; k < 60; k++)
    g += `<rect x="${bx + (k * bw) / 60}" y="${by}" width="${bw / 60 + 0.6}" height="${bh}" fill="rgb(${turbo((k + 0.5) / 60)})"/>`;
  for (let q = Math.ceil(lo); q <= Math.floor(hi); q++) {
    const x = bx + ((q - lo) / (hi - lo)) * bw;
    g += `<line x1="${x}" x2="${x}" y1="${by + bh}" y2="${by + bh + 3}" stroke="${C_TXT}"/><text x="${x}" y="${by + bh + 14}" text-anchor="middle" font-size="11" fill="${C_TXT}">1e${q}</text>`;
  }
  g += `<text x="${bx - 8}" y="${by + bh}" text-anchor="end" font-size="12" fill="${C_TXT}">Cn² (m⁻²ᐟ³)</text>`;
  return g;
}

/** Cn² profile at hour index i (side panel of the Prévision Cn² chart). */
export function cn2ProfileSvg(c: Cn2Ctx, i: number, pfW: number) {
  const H = 400,
    W = pfW,
    L = 6,
    R = 6,
    T = 46,
    B = 56,
    pw = W - L - R,
    ph = H - T - B;
  const t = c.times[i];
  const d = new Date(t ?? 0),
    Yz = (z: number) => T + ph - ((Math.min(Math.max(z, c.za), c.zb) - c.za) / (c.zb - c.za)) * ph,
    x0 = c.lo - 1,
    x1 = c.hi + 0.5,
    X = (v: number) => L + ((Math.min(Math.max(v, x0), x1) - x0) / (x1 - x0)) * pw;
  let g = `<rect x="${L}" y="${T}" width="${pw}" height="${ph}" fill="#262c3b"/>`;
  g += `<text x="${L}" y="12" font-size="10" fill="#e6ebf6" font-weight="500">${ddmm(d)} ${pad2(d.getUTCHours())}h ${tr("TU")}</text>`;
  const row = c.lg[i];
  if (!row || row.every((v) => v == null))
    return g + `<text x="${L + pw / 2}" y="${T + ph / 2}" text-anchor="middle" font-size="11" fill="${C_TXT}">${tr("pas de Cn² (H+0 ou trou)")}</text>`;
  for (let q = Math.ceil(x0); q <= Math.floor(x1); q++)
    g += `<line x1="${X(q)}" x2="${X(q)}" y1="${T}" y2="${T + ph}" stroke="#3a4258"/>${(q - Math.ceil(x0)) % 2 ? "" : `<text x="${X(q)}" y="${T + ph + 14}" text-anchor="middle" font-size="8" fill="${C_TXT}">1e${q}</text>`}`;
  const pts: number[][] = [];
  c.heights.forEach((z, k) => {
    if (z < c.za || z > c.zb) return;
    const v = row[k];
    if (v != null) pts.push([X(v), Yz(z)]);
  });
  if (pts.length > 1) g += pl(pts, 'stroke="#5eead4" stroke-width="2"');
  pts.forEach(([x, y]) => (g += `<circle cx="${x}" cy="${y}" r="2" fill="#5eead4"/>`));
  const jet = jetStream(c, i);
  if (jet && jet.z >= c.za && jet.z <= c.zb) {
    const y = Yz(jet.z);
    g += `<line x1="${L}" x2="${L + pw}" y1="${y}" y2="${y}" stroke="#f2c14e" stroke-width="1" stroke-dasharray="3 2"/><circle cx="${X(jet.v)}" cy="${y}" r="3.2" fill="#f2c14e" stroke="#000" stroke-width="0.8"/><text x="${L + 3}" y="${y - 4}" font-size="11" font-weight="600" fill="#f2c14e" stroke="#000" stroke-width="3" paint-order="stroke">Jet stream</text><text x="${L + pw - 2}" y="${y + 12}" text-anchor="end" font-size="9" fill="#f2c14e" stroke="#000" stroke-width="2.5" paint-order="stroke">${((jet.z + c.sol) / 1000).toFixed(1)} km ${tr("d'altitude")}</text>`;
  }
  const hc = c.hc[i];
  if (hc != null && hc >= c.za && hc <= c.zb)
    g += `<line x1="${L}" x2="${L + pw}" y1="${Yz(hc)}" y2="${Yz(hc)}" stroke="#000" stroke-width="4.2"/><line x1="${L}" x2="${L + pw}" y1="${Yz(hc)}" y2="${Yz(hc)}" stroke="#ff2bd6" stroke-width="2.4"/><text x="${L + 4}" y="${Yz(hc) - 4}" font-size="12" font-weight="500" fill="#ff2bd6" stroke="#000" stroke-width="3" paint-order="stroke">BL</text><text x="${L + pw - 2}" y="${Yz(hc) - 3}" text-anchor="end" font-size="9" fill="#ff2bd6">${Math.round(hc)} m</text>`;
  const step = c.zb - c.za > 8000 ? 2000 : c.zb - c.za > 2000 ? 500 : 100;
  for (let z = Math.ceil(c.za / step) * step; z <= c.zb; z += step)
    g += `<line x1="${L}" x2="${L + pw}" y1="${Yz(z)}" y2="${Yz(z)}" stroke="#3a4258" stroke-width="0.6"/>`;
  const s = c.see[i];
  g += `<text x="${L + pw / 2}" y="${H - 6}" text-anchor="middle" font-size="9" fill="${C_TXT}">Cn²</text><text x="${L}" y="${T - 7}" font-size="9" fill="${C_TXT}">seeing ${s != null ? s.toFixed(2) + '"' : "–"}${isNightDate(d) ? "" : tr(" (jour)")}</text>`;
  return g;
}

/* ---------- model variables ---------- */
export const PVDEF: [id: string, label: string, unit: string, color: string, real: boolean][] = [
  ["see", "Seeing", '"', "#8fd0ff", true],
  ["dth", "Stabilité (dθ/dz, 10–100 m)", " K/100 m", "#ff9f6b", true],
  ["hc", "BL", " m", "#ff3cf0", true],
  ["u10", "Vent à 10 m", " km/h", "#9be89b", true],
  ["u100", "Vent à 100 m", " km/h", "#4fc06a", true],
  ["u500", "Vent à 500 m", " km/h", "#1f8f45", true],
  ["shl", "Cisaillement (10 m – 500 m)", " m/s/km", "#f2c14e", true],
  ["shj", "Cisaillement jetstream", " m/s/km", "#e8743b", true],
  ["tke", "TKE", " m²/s²", "#c79bff", true],
  ["t2", "Température", " °C", "#ff6b6b", true],
];
export const PVGRP = [
  ["see", "dth", "hc", "tke", "t2"],
  ["u10", "u100", "u500", "shl", "shj"],
];

/** Value of variable `id` at time t from the forecast; null where it has none (forecasts computed before
 * the variables were stored): never a fictitious value. */
function pvValue(t: number, id: string, byT: Map<number, Forecast["points"][number]>) {
  const p = byT.get(t);
  if (id === "see") return p?.seeing_arcsec ?? null;
  if (id === "hc") return p?.h_coulim_m ?? null;
  return p?.variables?.[id] ?? null;
}

export interface PvPanel {
  svg: string;
  W: number;
  H: number;
  ranges: Record<string, [number, number]>;
}

/** One sub-panel of model variables (night hours only, nights glued with a gap). */
/** Model-variable panel; in the week view the hours before the latest run (stitched main runs) are solid,
 * the latest run dashed. */
export function pvPanel(fc: Forecast, _name: string, sel: Set<string>, zoom = 1): PvPanel {
  const runT = ms(fc.run_time);
  const byT = new Map(fc.points.map((p) => [ms(p.valid_time), p]));
  const tl = [...byT.keys()].sort((a, b) => a - b).filter((t) => isNightDate(new Date(t)));
  const D: Record<string, { a: (number | null)[]; lo: number; hi: number }> = {};
  PVDEF.forEach(([id]) => {
    const a = tl.map((t) => {
      const v = pvValue(t, id, byT);
      return v != null && isFinite(v) ? v : null;
    });
    const ok = a.filter((v): v is number => v != null);
    D[id] = { a, lo: ok.length ? Math.min(...ok) : 0, hi: ok.length ? Math.max(...ok) : 1 };
  });
  const GAP = 1.5,
    PX: number[] = [];
  let pos = 0;
  tl.forEach((t, j) => {
    if (j && t - tl[j - 1]! > HOUR) pos += GAP;
    PX.push(pos);
    pos++;
  });
  const NP = Math.max(1, pos);
  const chosen = PVDEF.filter((q) => sel.has(q[0])),
    units = [...new Set(chosen.map((q) => q[2]))],
    common = units.length === 1,
    W = Math.round(640 * zoom),
    H = 200,
    L = common ? 44 : 12,
    R = 8,
    T = 10,
    B = 22,
    pw = W - L - R,
    ph = H - T - B,
    X = (j: number) => L + (PX[j]! / NP) * pw,
    cwn = pw / NP;
  let g = "";
  tl.forEach((t, j) => {
    if (!j || t - tl[j - 1]! > HOUR) {
      if (j)
        g += `<line x1="${X(j) - (cwn * GAP) / 2}" x2="${X(j) - (cwn * GAP) / 2}" y1="${T}" y2="${T + ph}" stroke="${C_TXT}" stroke-width="0.6" stroke-dasharray="2 3"/>`;
      const b0 = new Date(t - 12 * HOUR),
        e = new Date(b0.getTime() + 24 * HOUR);
      g += `<text x="${X(j) + 2}" y="${T + ph + 15}" font-size="10" fill="${C_TXT}">${ddmm(b0)}→${ddmm(e)}</text>`;
    }
  });
  let lo = 0,
    hi = 1;
  if (common && chosen.length) {
    lo = Math.min(0, ...chosen.map((q) => D[q[0]]!.lo));
    hi = Math.max(...chosen.map((q) => D[q[0]]!.hi)) * 1.08 || 1;
  }
  const Yc = (v: number) => T + ph - ((v - lo) / (hi - lo)) * ph;
  if (common && chosen.length) {
    const st = (hi - lo) / 4,
      dg = hi - lo >= 20 ? 0 : hi - lo >= 2 ? 1 : 2;
    for (let k2 = 0; k2 <= 4; k2++) {
      const v = lo + st * k2;
      g += `<line x1="${L}" x2="${W - R}" y1="${Yc(v)}" y2="${Yc(v)}" stroke="${C_LINE}" stroke-width="0.6"/><text x="${L - 4}" y="${Yc(v) + 3.5}" text-anchor="end" font-size="10" fill="${C_TXT}">${v.toFixed(dg)}<tspan font-weight="700">${k2 === 4 ? units[0]!.trim() : ""}</tspan></text>`;
    }
  } else {
    for (let k2 = 0; k2 <= 4; k2++)
      g += `<line x1="${L}" x2="${W - R}" y1="${T + (ph * k2) / 4}" y2="${T + (ph * k2) / 4}" stroke="${C_LINE}" stroke-width="0.6"/>`;
    if (chosen.length)
      g += `<text x="${L + 4}" y="${T + 11}" font-size="10" fill="${C_TXT}">${tr("échelle propre à chaque courbe (valeurs à droite)")}</text>`;
  }
  chosen.forEach(([id, , , col]) => {
    const S2 = D[id]!,
      Y = common ? Yc : (v: number) => T + ph - ((v - S2.lo) / (S2.hi - S2.lo || 1)) * ph * 0.92 - ph * 0.04;
    let seg: number[][] = [],
      pv: number | null = null,
      past = false;
    const fl = () => {
      if (seg.length > 1) g += pl(seg, `stroke="${col}" stroke-width="1.8"${past ? "" : ' stroke-dasharray="5 3"'}`);
      seg = [];
    };
    S2.a.forEach((v, j) => {
      if (v == null) {
        fl();
        pv = null;
        return;
      }
      const isPast = tl[j]! < runT;
      if (pv != null && (tl[j]! - tl[pv]! > HOUR || isPast !== past)) {
        const last = seg[seg.length - 1];
        fl();
        if (last && isPast !== past && tl[j]! - tl[pv]! <= HOUR) seg.push(last); // continuous at the run
      }
      past = isPast;
      seg.push([X(j) + cwn / 2, Y(v)]);
      pv = j;
    });
    fl();
  });
  if (!chosen.length)
    g += `<text x="${W / 2}" y="${H / 2}" text-anchor="middle" font-size="12" fill="${C_TXT}">${tr("Coche une ou plusieurs variables à droite.")}</text>`;
  const ranges: Record<string, [number, number]> = {};
  PVDEF.forEach(([id]) => (ranges[id] = [D[id]!.lo, D[id]!.hi]));
  return { svg: g, W, H, ranges };
}
