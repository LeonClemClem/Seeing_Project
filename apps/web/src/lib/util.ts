/** Small numeric and SVG-string helpers shared by the charts (ported from the mockup). */
import { tr } from "../i18n";

export const D2R = Math.PI / 180;
export const HOUR = 3_600_000;

/** Deterministic pseudo-random in [0, 1) from a seed. */
export function rnd(s: number): number {
  const x = Math.sin(s * 12.9898 + 4.1) * 43758.5453;
  return x - Math.floor(x);
}

export function hash(s: string): number {
  let h = 7;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 100003;
  return h;
}

/** Google "turbo" colour map, x in [0, 1] → [r, g, b]. */
export function turbo(x: number): [number, number, number] {
  x = Math.max(0, Math.min(1, x));
  const r = 34.61 + x * (1172.33 + x * (-10793.56 + x * (33300.12 + x * (-38394.49 + x * 14825.05))));
  const g = 23.31 + x * (557.33 + x * (1225.33 + x * (-3574.96 + x * (1073.77 + x * 707.56))));
  const b = 27.2 + x * (3211.1 + x * (-15327.97 + x * (27814 + x * (-22569.18 + x * 6838.66))));
  const c = (v: number) => Math.max(0, Math.min(255, Math.round(v)));
  return [c(r), c(g), c(b)];
}

export const turboGradient = () =>
  "linear-gradient(to right," + [0, 0.2, 0.4, 0.6, 0.8, 1].map((x) => "rgb(" + turbo(x).join(",") + ")").join(",") + ")";

export const fmt = (v: number) => (v < 1 ? v.toFixed(2) : v < 20 ? v.toFixed(1) : Math.round(v) + "");
export const fr2 = (v: number | null) => (v == null || isNaN(v) ? "–" : (v >= 0 ? "+" : "") + v.toFixed(2));
export const f2 = (v: number) => (isNaN(v) ? "–" : v.toFixed(2));

export function med(a: number[]): number {
  const s = [...a].sort((p, q) => p - q);
  const n = s.length;
  if (!n) return NaN;
  return n % 2 ? s[(n - 1) / 2]! : (s[n / 2 - 1]! + s[n / 2]!) / 2;
}

export function corr(a: number[], b: number[]): number {
  const n = a.length;
  if (n < 3) return NaN;
  const ma = a.reduce((s, v) => s + v, 0) / n;
  const mb = b.reduce((s, v) => s + v, 0) / n;
  let c = 0,
    va = 0,
    vb = 0;
  for (let i = 0; i < n; i++) {
    c += (a[i]! - ma) * (b[i]! - mb);
    va += (a[i]! - ma) ** 2;
    vb += (b[i]! - mb) ** 2;
  }
  return c / Math.sqrt(va * vb);
}

/** Escape text that comes from data (site names) before it goes into an SVG/HTML string. */
export const esc = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

/* ---------- dates (UTC) ---------- */
export const pad2 = (n: number) => String(n).padStart(2, "0");
export const ddmm = (d: Date) => pad2(d.getUTCDate()) + "/" + pad2(d.getUTCMonth() + 1);
/** "12/10 12Z" */
export const runLabel = (ms: number) => {
  const d = new Date(ms);
  return `${ddmm(d)} ${pad2(d.getUTCHours())}Z`;
};
/** Night for the measurement fit: 17h30–06h UTC. */
export const isNightDate = (d: Date) => {
  const m = d.getUTCHours() * 60 + d.getUTCMinutes();
  return m >= 17 * 60 + 30 || m < 6 * 60;
};
/** "2026-10-12T20:00" → Date (the mockup's minute-precision UTC strings). */
export const pd = (s: string) => new Date(s + ":00Z");
export const isoMin = (ms: number) => new Date(ms).toISOString().slice(0, 16);

/* ---------- SVG strings ---------- */
export const C_TXT = "#97a2bd",
  C_LINE = "#26324f",
  C_DAY = "#253c6b",
  C_NIGHT = "#253c6b",
  C_AR = "#4f9be8",
  C_OBS = "#f2a23a",
  C_OBSD = "#c97a12";

export const pl = (pts: number[][], st: string) =>
  `<polyline fill="none" ${st} points="${pts.map((p) => p.join(",")).join(" ")}"/>`;

export function yaxis(Y: (v: number) => number, L: number, R: number, ymax: number, st: number, ymin = 0) {
  let g = "";
  for (let v = Math.ceil(ymin / st - 1e-9) * st; v <= ymax + 1e-9; v = +(v + st).toFixed(6))
    g += `<line x1="${L}" x2="${R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${C_LINE}" stroke-width="0.6"/><text x="${L - 5}" y="${Y(v) + 4}" text-anchor="end" font-size="11" fill="${C_TXT}">${v}"</text>`;
  return g;
}

export const dnText = (x: number, y: number, night: boolean) =>
  `<text x="${x}" y="${y}" text-anchor="middle" font-size="11" font-weight="500" fill="${night ? "#9cc7ff" : "#f2c14e"}" stroke="#0a0f1d" stroke-width="3" paint-order="stroke">${tr(night ? "Nuit" : "Jour")}</text>`;

/** Hourly median curve: polyline broken where consecutive hours are more than one hour apart. q = [x, y, hour]. */
export function medCurve(q: [number, number, number][], st = `stroke="${C_OBSD}" stroke-width="1.4"`) {
  let s: number[][] = [],
    o = "",
    pv: number | null = null;
  q.forEach(([x, y, h]) => {
    if (pv != null && h - pv > 1.01) {
      if (s.length > 1) o += pl(s, st);
      s = [];
    }
    s.push([x, y]);
    pv = h;
  });
  if (s.length > 1) o += pl(s, st);
  return o;
}

/** Physical seeing (arcsec) from the integrated Cn² (m^1/3), as in the V2 code. */
export const seeJ = (J: number) => (J > 0 ? 0.98 * 5e-7 * Math.pow(0.423 * Math.pow((2 * Math.PI) / 5e-7, 2) * J, 0.6) * 206265 : NaN);
