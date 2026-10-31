/** Per-place charts (mockup's lxHist / lxCorr / histSvg / lxMaille) over LieuData. */
import { tr } from "../i18n";
import type { Cells, SkillBin, SkillNight } from "../api";
import type { LieuData, LieuEpisode, TV } from "../mock/engine";
import type { UiState } from "../store";
import {
  C_AR,
  C_DAY,
  C_LINE,
  C_OBS,
  C_OBSD,
  C_TXT,
  corr,
  D2R,
  ddmm,
  esc,
  f2,
  fr2,
  isNightDate,
  med,
  medCurve,
  pd,
  pl,
  turbo,
  yaxis,
} from "../lib/util";

/** Signed error of the forecast with the age of the run (square panel under the correlation): mean forecast - measured
 * for each hour of age (orange) and by night, medians of the night (white, dashed, age at 00h UTC), each with a band of
 * one standard deviation. Above 0, AROME forecasts a worse seeing than measured. The ages with few compared hours (or
 * nights) are see-through. */
export function skillSvg(bins: SkillBin[], nights: SkillNight[] = []) {
  const W = 200,
    H = 200,
    L = 30,
    R = 8,
    T = 8,
    B = 30,
    pw = W - L - R,
    ph = H - T - B,
    amax = Math.max(48, ...bins.map((b) => b.age_to)),
    hp = bins.filter((b) => b.bias != null),
    nn = nights.filter((n) => n.bias != null),
    emax = Math.max(
      0.5,
      Math.ceil(Math.max(...hp.map((b) => Math.abs(b.bias!) + (b.sd ?? 0)), ...nn.map((n) => Math.abs(n.bias!) + (n.sd ?? 0))) * 1.05 * 2) / 2,
    ),
    X = (a: number) => L + (a / amax) * pw,
    Y = (v: number) => T + ph / 2 - (Math.max(-emax, Math.min(v, emax)) / emax) * (ph / 2),
    sg = (v: number) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(v === 0 ? 0 : 1);
  let g = "";
  [-emax, -emax / 2, 0, emax / 2, emax].forEach(
    (v) =>
      (g += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${v === 0 ? C_TXT : C_LINE}" stroke-width="${v === 0 ? 0.9 : 0.5}"/><text x="${L - 3}" y="${Y(v) + 3}" text-anchor="end" font-size="9" fill="${C_TXT}">${sg(v)}"</text>`),
  );
  for (let a = 0; a <= amax; a += 12)
    g += `<line x1="${X(a)}" x2="${X(a)}" y1="${T}" y2="${T + ph}" stroke="${C_LINE}" stroke-width="0.5"/><text x="${X(a)}" y="${T + ph + 12}" text-anchor="middle" font-size="9" fill="${C_TXT}">${a}</text>`;
  g += `<text x="${W - R - 2}" y="${T + 9}" text-anchor="end" font-size="7.5" fill="${C_TXT}">${tr("AROME trop pessimiste")}</text>`;
  g += `<text x="${W - R - 2}" y="${T + ph - 3}" text-anchor="end" font-size="7.5" fill="${C_TXT}">${tr("AROME trop optimiste")}</text>`;
  g += `<text x="${L + pw / 2}" y="${H - 4}" text-anchor="middle" font-size="9.5" fill="${C_TXT}">${tr("âge du run (h)")}</text>`;
  // band of one standard deviation around a curve, broken where an age is missing
  const band = (q: { x: number; v: number; sd: number | null }[], color: string, op: number) => {
    const w = q.filter((p) => p.sd != null);
    if (w.length < 2) return;
    const up = w.map((p) => `${X(p.x)},${Y(p.v + p.sd!)}`),
      dn = w.map((p) => `${X(p.x)},${Y(p.v - p.sd!)}`).reverse();
    g += `<polygon points="${[...up, ...dn].join(" ")}" fill="${color}" fill-opacity="${op}"/>`;
  };
  const runs = <U,>(a: U[], next: (p: U, q: U) => boolean) => {
    const out: U[][] = [];
    a.forEach((p, i) => (i && next(a[i - 1]!, p) ? out[out.length - 1]!.push(p) : out.push([p])));
    return out;
  };
  const hr = runs(hp, (p, q) => q.age_from === p.age_from + 1).map((r) => r.map((b) => ({ x: b.age_from + 0.5, v: b.bias!, sd: b.sd })));
  const nr = nn.map((n) => ({ x: n.age, v: n.bias!, sd: n.sd }));
  hr.forEach((r) => band(r, C_AR, 0.2));
  band(nr, "#f1efe8", 0.13);
  hr.forEach((r) => (g += pl(r.map((p) => [X(p.x), Y(p.v)] as [number, number]), `stroke="${C_AR}" stroke-width="1.8"`)));
  hp.forEach((b) => {
    const op = b.n_hours < 10 ? ' opacity=".35"' : "";
    g += `<circle cx="${X(b.age_from + 0.5)}" cy="${Y(b.bias!)}" r="2.4" fill="${C_AR}"${op}><title>${b.age_from} h : ${sg(b.bias!)}'' ± ${(b.sd ?? 0).toFixed(2)} (${b.n_hours} h)</title></circle>`;
  });
  g += pl(nr.map((p) => [X(p.x), Y(p.v)] as [number, number]), `stroke="#f1efe8" stroke-width="1.4" stroke-dasharray="4 3"`);
  nn.forEach((n) => {
    const op = n.n_nights < 3 ? ' opacity=".35"' : "";
    g += `<rect x="${X(n.age) - 3}" y="${Y(n.bias!) - 3}" width="6" height="6" fill="#f1efe8" stroke="#0a0f1d" stroke-width="0.8"${op}><title>${tr("nuit")} ${n.age} h : ${sg(n.bias!)}'' ± ${(n.sd ?? 0).toFixed(2)} (${n.n_nights} ${tr("nuits")})</title></rect>`;
  });
  return g;
}

/** Night only (the mockup removed daytime seeing): keep the night part of each episode on a compressed axis. */
function nightParts(eps: LieuEpisode[]): LieuEpisode[] {
  const out: LieuEpisode[] = [];
  const ms = (s: string) => pd(s).getTime(),
    iso = (t: number) => new Date(t).toISOString().slice(0, 16);
  eps.forEach((e) => {
    const a = ms(e.a),
      b = ms(e.b);
    let s: number | null = null,
      t = a;
    const step = (t0: number) => {
      const d = new Date(t0),
        m = d.getUTCMinutes();
      return t0 + ((m < 30 ? 30 : 60) - m) * 60000 - d.getUTCSeconds() * 1000;
    };
    const push = (x: number, y: number) => {
      if (y - x < 15 * 60000) return;
      const sl = (arr: TV[]) =>
        arr.filter((p) => {
          const v = ms(p[0]);
          return v >= x && v <= y;
        });
      out.push({ a: iso(x), b: iso(y), prevu: sl(e.prevu), mediane: sl(e.mediane), brut: sl(e.brut) });
    };
    while (t < b) {
      const n = Math.min(step(t), b),
        k = isNightDate(new Date(t));
      if (k && s == null) s = t;
      if (!k && s != null) {
        push(s, t);
        s = null;
      }
      t = n;
    }
    if (s != null) push(s, b);
  });
  return out;
}

export interface HistOpts {
  OB: boolean;
  mesf: UiState["mesf"];
  zoom: number;
  /** Visible x window in viewBox units when zoomed and auto-stretched, else null. */
  win: [number, number] | null;
  /** Highlighted night (date of the evening, UTC), or null. */
  sel?: string | null;
  /** Hours left out of the calibration (filters and nights left out), as hourKey "night|h": in red. */
  rm?: ReadonlySet<string>;
}

/** x range (viewBox units) of each night part of the history, for the clicks. */
export type HistHit = { x0: number; x1: number; night: string };

/** History of forecasts and measurements on a compressed time axis. viewBox 0 0 (1100·zoom) 240. */
export function histChart(l: LieuData, o: HistOpts): { svg: string; note: string; hits: HistHit[] } {
  const W = 1100 * o.zoom,
    H = 240,
    L = 36,
    R = 10,
    T = 12,
    B = 34,
    pw = W - L - R,
    ph = H - T - B,
    gap = 14,
    E = nightParts(l.episodes);
  const keep = (s: string) => isNightDate(pd(s));
  if (!E.length)
    return {
      svg: `<text x="${W / 2}" y="${H / 2}" text-anchor="middle" font-size="14" fill="${C_TXT}">${tr("Pas de période avec prévision et mesures pour ce lieu.")}</text>`,
      note: "",
      hits: [],
    };
  const span = (e: LieuEpisode) => (pd(e.b).getTime() - pd(e.a).getTime()) / 3600000,
    tot = E.reduce((s, e) => s + span(e), 0),
    u = (pw - gap * (E.length - 1)) / tot;
  const str = !!o.win;
  const [xa, xb] = o.win ?? [-1e9, 1e9];
  let ys: number[] = [];
  {
    let off = L;
    E.forEach((e) => {
      const a = pd(e.a).getTime(),
        Xp = (d: number) => off + ((d - a) / 3600000) * u,
        add = (p: TV) => {
          if (p[1] != null && keep(p[0])) {
            const x = Xp(pd(p[0]).getTime());
            if (x >= xa && x <= xb) ys.push(p[1]);
          }
        };
      e.prevu.forEach(add);
      e.mediane.forEach(add);
      off += span(e) * u + gap;
    });
  }
  if (!ys.length) ys = [2];
  const lo = Math.min(...ys),
    hi = Math.max(...ys),
    pad = str ? Math.max((hi - lo) * 0.04, 0.05) : 0,
    ymin = str ? Math.max(0, lo - pad) : 0,
    ymax = str ? Math.max(hi + pad, ymin + 0.2) : Math.max(2, Math.ceil(hi * 1.15)),
    rg = ymax - ymin,
    Y = (v: number) => T + ph - ((Math.min(Math.max(v, ymin), ymax) - ymin) / rg) * ph,
    yst = rg > 8 ? 2 : rg > 3 ? 1 : rg > 1.5 ? 0.5 : rg > 0.6 ? 0.2 : 0.1;
  let g = yaxis(Y, L, W - R, ymax, yst, ymin),
    off = L,
    lastDay = "";
  const hits: HistHit[] = [];
  if (str)
    for (let v = Math.ceil(ymin / yst - 1e-9) * yst; v <= ymax + 1e-9; v = +(v + yst).toFixed(6))
      g += `<text x="${xa + 6}" y="${Y(v) - 3}" font-size="10" fill="#e6ebf6" stroke="#0a0f1d" stroke-width="3" paint-order="stroke">${+v.toFixed(1)}"</text>`;
  E.forEach((e, n) => {
    const a = pd(e.a),
      oo = off,
      X = (d: Date) => oo + ((d.getTime() - a.getTime()) / 3600000) * u,
      w = span(e) * u;
    for (let t = new Date(a); t < pd(e.b); t = new Date(t.getTime() + 1800000))
      if (!isNightDate(t)) g += `<rect x="${X(t)}" y="${T}" width="${u / 2 + 0.4}" height="${ph}" fill="${C_DAY}"/>`;
    const nk = nightKey(e.a);
    hits.push({ x0: oo - gap / 2, x1: oo + w + gap / 2, night: nk });
    if (o.sel === nk)
      g += `<rect x="${oo - 3}" y="${T}" width="${w + 6}" height="${ph}" fill="rgba(242,193,78,.16)" stroke="#f2c14e" stroke-width="1.5"/>`;
    const d0 = ddmm(a);
    if (d0 !== lastDay && w > 18) {
      g += `<text x="${oo + 2}" y="${T + ph + 14}" font-size="10" fill="#e6ebf6" font-weight="500">${d0}</text>`;
      lastDay = d0;
    }
    if (w > 36)
      g += `<text x="${oo + w - 2}" y="${T + ph + 26}" font-size="9" text-anchor="end" fill="${C_TXT}">${String(a.getUTCHours()).padStart(2, "0")}h–${String(pd(e.b).getUTCHours()).padStart(2, "0")}h</text>`;
    if (o.OB && o.mesf.brut)
      e.brut.forEach(
        (p) =>
          p[1] != null &&
          keep(p[0]) &&
          (g += `<circle cx="${X(pd(p[0]))}" cy="${Y(p[1])}" r="1.4" fill="${C_OBS}" opacity=".7"/>`),
      );
    let seg: number[][] = [];
    const fl = () => {
      if (seg.length > 1) g += pl(seg, `stroke="${C_AR}" stroke-width="1.8"`);
      // a single forecast hour (e.g. a night piece cut at 17h30) is still shown, as a dot
      else if (seg.length === 1) g += `<circle cx="${seg[0]![0]}" cy="${seg[0]![1]}" r="2.6" fill="${C_AR}"/>`;
      seg = [];
    };
    e.prevu.forEach((p) => {
      if (p[1] == null || !keep(p[0])) {
        fl();
        return;
      }
      seg.push([X(pd(p[0])), Y(p[1])]);
    });
    fl();
    if (o.OB && o.mesf.courbe)
      g += medCurve(
        e.mediane
          .filter((p) => p[1] != null && keep(p[0]))
          .map((p): [number, number, number] => [X(pd(p[0])), Y(p[1]!), pd(p[0]).getTime() / 3600000]),
      );
    if (o.OB && o.mesf.horaire)
      e.mediane.forEach(
        (p) =>
          p[1] != null &&
          keep(p[0]) &&
          (g += `<rect x="${X(pd(p[0])) - 2.5}" y="${Y(p[1]) - 2.5}" width="5" height="5" fill="${o.rm?.has(hourKeyOf(p[0])) ? C_RM : C_OBSD}"/>`),
      );
    // hours left out of the calibration: red veil over the full height and red mark at the bottom
    if (o.rm?.size)
      e.mediane.forEach(
        (p) =>
          p[1] != null &&
          keep(p[0]) &&
          o.rm!.has(hourKeyOf(p[0])) &&
          (g += `<rect x="${X(pd(p[0])) - u / 2}" y="${T}" width="${u}" height="${ph}" fill="rgba(255,77,77,.16)"/><rect x="${X(pd(p[0])) - u / 2}" y="${T + ph - 4}" width="${u}" height="4" fill="${C_RM}"/>`),
      );
    off += w + gap;
    if (n < E.length - 1)
      g += `<text x="${off - gap / 2}" y="${T + ph / 2}" text-anchor="middle" font-size="11" fill="${C_TXT}">||</text>`;
  });
  return {
    svg: g,
    note: tr(
      `${E.length} période(s) avec prévision et mesures, du ${ddmm(pd(E[0]!.a))} au ${ddmm(pd(E[E.length - 1]!.b))} ; axe compressé (seules ces périodes sont montrées).`,
    ),
    hits,
  };
}

/** Night of a time: date of the evening (UTC), as the calibration nights. */
export const nightKey = (s: string) => new Date(pd(s).getTime() - 12 * 3600000).toISOString().slice(0, 10);
/** Calibration hour key "night|h" of a time (h = hours since 12h UTC of the evening), as mock/calibration hourKey. */
export const hourKeyOf = (s: string) => {
  const n = nightKey(s);
  return `${n}|${Math.round((pd(s).getTime() - Date.parse(n + "T12:00:00Z")) / 3600000)}`;
};
/** Colour of the hours left out of the calibration (as Calibrer). */
const C_RM = "#ff4d4d";

/** Forecast vs measured for a place: hourly medians, nightly medians (moons) and raw points. viewBox 0 0 340 320. */
export function corrChart(l: LieuData, corrf: UiState["corrf"], sel: string | null = null, rmHours?: ReadonlySet<string>) {
  const prevAt = (() => {
    const m = new Map<string, number>();
    l.episodes.forEach((e) => e.prevu.forEach((p) => p[1] != null && m.set(p[0], p[1])));
    return (s: string) => m.get(s);
  })();
  const P = l.paires.filter((p) => p[3] && p[1] != null && p[2] != null) as [string, number, number, boolean][];
  const PH = new Set(P.map((p) => p[0])),
    hs = (d: Date) => d.toISOString().slice(0, 16),
    RAW: [number, number][] = [];
  if (corrf.brut)
    l.episodes.forEach((e) =>
      e.brut.forEach((p) => {
        if (p[1] == null) return;
        const d = pd(p[0]),
          r = new Date(d.getTime() + 1800000);
        r.setUTCMinutes(0, 0, 0);
        if (!PH.has(hs(r))) return;
        const a = new Date(d);
        a.setUTCMinutes(0, 0, 0);
        const va = prevAt(hs(a)),
          vb = prevAt(hs(new Date(a.getTime() + 3600000)));
        let v: number | null = null;
        if (d.getTime() === a.getTime()) v = va ?? null;
        else if (va != null && vb != null) v = va + ((vb - va) * (d.getTime() - a.getTime())) / 3600000;
        if (v != null && isFinite(v)) RAW.push([p[1], v]);
      }),
    );
  const empty = { rn: "–", nn: "", rj: "–", nj: "" };
  if (!P.length && !RAW.length)
    return {
      svg: `<text x="170" y="160" text-anchor="middle" font-size="13" fill="${C_TXT}">${tr("Pas d'heure de nuit comparée.")}</text>`,
      ct: "–",
      tiles: empty,
    };
  const G: Record<string, typeof P> = {};
  P.forEach((p) => {
    const k = nightKey(p[0]);
    (G[k] = G[k] || []).push(p);
  });
  const MOON = Object.values(G)
    .filter((a) => a.length >= 2)
    .map((a): [number, number] => [med(a.map((p) => p[2])), med(a.map((p) => p[1]))]);
  const all: [number, number][] = [
    ...(corrf.horaire ? P.map((p): [number, number] => [p[2], p[1]]) : []),
    ...(corrf.nuit ? MOON : []),
    ...RAW,
  ];
  const W = 340,
    H = 320,
    L = 34,
    T = 8,
    B = 32,
    R = 10,
    pw = W - L - R,
    ph = H - T - B,
    m = Math.max(
      2,
      Math.ceil(Math.max(...(all.length ? all : P.map((p) => [p[2], p[1]])).map((q) => Math.max(q[0]!, q[1]!))) * 1.08),
    ),
    X = (v: number) => L + (Math.min(v, m) / m) * pw,
    Y = (v: number) => T + ph - (Math.min(v, m) / m) * ph,
    st = m > 8 ? 2 : 1;
  let g = "";
  for (let v = 0; v <= m; v += st)
    g += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${C_LINE}" stroke-width="0.6"/><line y1="${T}" y2="${T + ph}" x1="${X(v)}" x2="${X(v)}" stroke="${C_LINE}" stroke-width="0.6"/><text x="${L - 5}" y="${Y(v) + 4}" text-anchor="end" font-size="11" fill="${C_TXT}">${v}"</text><text x="${X(v)}" y="${T + ph + 14}" text-anchor="middle" font-size="11" fill="${C_TXT}">${v}"</text>`;
  g += `<line x1="${X(0)}" y1="${Y(0)}" x2="${X(m)}" y2="${Y(m)}" stroke="${C_TXT}" stroke-dasharray="4 3"/>`;
  RAW.forEach((q) => (g += `<circle cx="${X(q[1])}" cy="${Y(q[0])}" r="1.6" fill="#2a78d6" opacity=".35"/>`));
  if (corrf.horaire)
    P.forEach((p) => (g += `<circle cx="${X(p[1])}" cy="${Y(p[2])}" r="3.6" fill="#2a78d6" stroke="#fff" stroke-width="0.6"/>`));
  if (corrf.nuit)
    MOON.forEach(([y, x]) => {
      const cx = X(x),
        cy = Y(y);
      g += `<path d="M${cx + 2},${cy - 9} A9,9 0 1,0 ${cx + 2},${cy + 9} A12,12 0 0,1 ${cx + 2},${cy - 9} Z" fill="#f1efe8" stroke="#0a0f1d" stroke-width="1"/>`;
    });
  // hours left out of the calibration (filters, nights left out) in red, the highlighted night on top in yellow
  if (rmHours?.size)
    P.filter((p) => rmHours.has(hourKeyOf(p[0]))).forEach(
      (p) => (g += `<circle cx="${X(p[1])}" cy="${Y(p[2])}" r="3.6" fill="${C_RM}" stroke="#fff" stroke-width="0.6"/>`),
    );
  if (sel && G[sel]) {
    G[sel].forEach((p) => (g += `<circle cx="${X(p[1])}" cy="${Y(p[2])}" r="5" fill="#f2c14e" stroke="#000" stroke-width="1"/>`));
    if (G[sel].length >= 2) {
      const cx = X(med(G[sel].map((p) => p[1]))),
        cy = Y(med(G[sel].map((p) => p[2])));
      g += `<circle cx="${cx}" cy="${cy}" r="11" fill="none" stroke="#f2c14e" stroke-width="2.2"/>`;
    }
  }
  g += `<text x="${L + pw / 2}" y="${H - 2}" text-anchor="middle" font-size="11" fill="${C_TXT}">${tr("prévu ")}${esc(l.modele)}</text><text x="10" y="${T + ph / 2}" text-anchor="middle" font-size="11" fill="${C_TXT}" transform="rotate(-90 10 ${T + ph / 2})">${tr("mesuré")}</text>`;
  const rr = corr(
      P.map((p) => p[2]),
      P.map((p) => p[1]),
    ),
    bb = P.length ? P.reduce((s, p) => s + p[1] - p[2], 0) / P.length : NaN,
    rm =
      MOON.length > 2
        ? corr(
            MOON.map((q) => q[0]),
            MOON.map((q) => q[1]),
          )
        : NaN,
    qh = P.length ? Math.sqrt(P.reduce((s, p) => s + (p[1] - p[2]) ** 2, 0) / P.length) : NaN,
    rb = RAW.length
      ? corr(
          RAW.map((q) => q[0]),
          RAW.map((q) => q[1]),
        )
      : NaN;
  const LG: [string, string][] = [
    [tr("R nuit"), f2(rm)],
    [tr("R horaire"), f2(rr)],
    ...(RAW.length ? [[tr("R brut"), f2(rb)] as [string, string]] : []),
    [tr("précision horaire"), isNaN(qh) ? "–" : "± " + qh.toFixed(2) + '"'],
  ];
  g +=
    `<rect x="${L + 4}" y="${T + 4}" width="150" height="${LG.length * 15 + 6}" rx="5" fill="#0a0f1d" opacity=".82"/>` +
    LG.map(
      ([a, v], i) =>
        `<text x="${L + 10}" y="${T + 18 + i * 15}" font-size="10.5" fill="${C_TXT}">${a}</text><text x="${L + 148}" y="${T + 18 + i * 15}" text-anchor="end" font-size="10.5" font-weight="600" fill="#e8ecf6">${v}</text>`,
    ).join("");
  return {
    svg: g,
    ct: tr(
      `nuit : r = ${f2(rr)} · n = ${P.length} h · biais ${fr2(bb)}" · précision horaire ± ${f2(qh)}" · ${MOON.length} nuits (r des médianes nocturnes ${f2(rm)})${RAW.length ? ` · R brut ${f2(rb)} (${RAW.length} mesures)` : ""}`,
    ),
    tiles: {
      rn: f2(rr),
      nn: tr(`${P.length} h de nuit`),
      rj: isNaN(bb) ? "–" : fr2(bb) + '"',
      nj: tr(`${MOON.length} nuits`),
    },
  };
}

export const seeHist = (l: LieuData) => {
  const v: number[] = [];
  l.episodes.forEach((e) =>
    e.brut.forEach((p) => {
      if (p[1] != null && isNightDate(pd(p[0]))) v.push(p[1]);
    }),
  );
  return v;
};

/** Histogram of measured night seeing with a log-normal fit, median and P5/P95. */
export function histSvg(v: number[], W: number, H: number, small: boolean) {
  // axis from 0 to the largest value, 0.25" classes
  const bw = 0.25,
    x0 = 0,
    nb = Math.ceil(Math.max(1, ...v) / bw + 1e-9),
    x1 = nb * bw,
    c = new Array<number>(nb).fill(0);
  v.forEach((x) => c[Math.min(nb - 1, Math.floor(x / bw))]!++);
  const mx = Math.max(...c, 1),
    L = small ? 4 : 34,
    R = small ? 4 : 8,
    T = small ? 14 : 10,
    B = small ? 12 : 30,
    pw = W - L - R,
    ph = H - T - B,
    cw = pw / nb;
  const s = [...v].sort((a, b) => a - b),
    q = (p: number) => (s.length ? s[Math.min(s.length - 1, Math.floor(p * (s.length - 1)))]! : NaN),
    md = q(0.5);
  let g = "";
  c.forEach((n, k) => {
    const h = (n / mx) * ph;
    g += `<rect x="${L + k * cw + 0.5}" y="${T + ph - h}" width="${cw - 1}" height="${h}" fill="#2a78d6"/>`;
  });
  const lv = v.filter((x) => x > 0).map(Math.log),
    mu = lv.length ? lv.reduce((a, b) => a + b, 0) / lv.length : NaN,
    sg = lv.length > 1 ? Math.sqrt(lv.reduce((a, b) => a + (b - mu) ** 2, 0) / (lv.length - 1)) : NaN;
  if (isFinite(mu) && sg > 0) {
    const pdf = (x: number) => Math.exp(-((Math.log(x) - mu) ** 2) / (2 * sg * sg)) / (x * sg * Math.sqrt(2 * Math.PI)),
      pts: number[][] = [];
    for (let k = 0; k <= nb * 4; k++) {
      const x = x0 + (k * bw) / 4,
        y = x > 0 ? pdf(x) * v.length * bw : 0;
      pts.push([L + ((x - x0) / bw) * cw, T + ph - Math.min(y / mx, 1.05) * ph]);
    }
    g += pl(pts, `stroke="#000" stroke-width="${small ? 2.6 : 3.4}"`) + pl(pts, `stroke="#ff9f6b" stroke-width="${small ? 1.4 : 2}"`);
  }
  if (isFinite(md)) {
    const x = L + Math.max(0, Math.min((md - x0) / bw, nb)) * cw;
    g += `<line x1="${x}" x2="${x}" y1="${T - 2}" y2="${T + ph}" stroke="#f2c14e" stroke-width="1.4"/>`;
    if (!small) {
      g += `<text x="${x + 8}" y="${T + 26}" font-size="24" font-weight="700" fill="#f2c14e" stroke="#0a0f1d" stroke-width="4" paint-order="stroke">${md.toFixed(2)}″</text><text x="${x + 9}" y="${T + 40}" font-size="11" fill="#f2c14e" stroke="#0a0f1d" stroke-width="3" paint-order="stroke">${tr("médiane")}</text>`;
      const mn = q(0.05),
        mxv = q(0.95),
        xp = (v2: number) => L + Math.max(0, Math.min((v2 - x0) / bw, nb)) * cw;
      g +=
        `<line x1="${xp(mn)}" x2="${xp(mn)}" y1="${T}" y2="${T + ph}" stroke="#9cc7ff" stroke-width="1.2" stroke-dasharray="4 3"/><line x1="${xp(mxv)}" x2="${xp(mxv)}" y1="${T}" y2="${T + ph}" stroke="#ff8a8a" stroke-width="1.2" stroke-dasharray="4 3"/>` +
        `<text x="${W - R}" y="${T + 16}" text-anchor="end" font-size="17" font-weight="700" fill="#9cc7ff" stroke="#0a0f1d" stroke-width="4" paint-order="stroke">min ${mn.toFixed(2)}″ <tspan font-size="11" font-weight="500">(P5)</tspan></text><text x="${W - R}" y="${T + 36}" text-anchor="end" font-size="17" font-weight="700" fill="#ff8a8a" stroke="#0a0f1d" stroke-width="4" paint-order="stroke">max ${mxv.toFixed(2)}″ <tspan font-size="11" font-weight="500">(P95)</tspan></text>`;
    }
  }
  if (small)
    g += `<text x="${L}" y="10" font-size="10" fill="#e6ebf6" font-weight="600">${tr("Seeing mesuré")}</text><text x="${W - R}" y="10" text-anchor="end" font-size="10" fill="#f2c14e">${tr("méd.")} ${isFinite(md) ? md.toFixed(2) : "–"}″</text><text x="${L}" y="${H - 2}" font-size="9" fill="${C_TXT}">${+x0.toFixed(2)}″</text><text x="${W - R}" y="${H - 2}" text-anchor="end" font-size="9" fill="${C_TXT}">${+x1.toFixed(2)}″</text>`;
  else {
    const xs = x1 - x0 > 12 ? 2 : x1 - x0 > 3 ? 1 : 0.5;
    for (let x = Math.ceil(x0 / xs) * xs; x <= x1 + 1e-9; x += xs)
      g += `<text x="${L + ((x - x0) / bw) * cw}" y="${T + ph + 14}" text-anchor="middle" font-size="11" fill="${C_TXT}">${+x.toFixed(2)}<tspan font-weight="700">″</tspan></text>`;
    g += `<text x="${L - 4}" y="${T + 8}" text-anchor="end" font-size="10" fill="${C_TXT}">${mx}</text><text x="${L - 4}" y="${T + ph}" text-anchor="end" font-size="10" fill="${C_TXT}">0</text><text x="${L + pw / 2}" y="${H - 2}" text-anchor="middle" font-size="11" fill="${C_TXT}">${tr("seeing mesuré (nuit), classes de 0,25″")}</text>`;
  }
  return { svg: g, md, q1: q(0.25), q3: q(0.75), n: v.length, mu, sg };
}

const relCol = (f: number): number[] => {
  const S: [number, number[]][] = [
    [0, [38, 115, 77]],
    [0.3, [120, 170, 90]],
    [0.55, [222, 205, 120]],
    [0.8, [170, 120, 80]],
    [1, [245, 245, 245]],
  ];
  f = Math.max(0, Math.min(1, f));
  for (let k = 1; k < S.length; k++)
    if (f <= S[k]![0]) {
      const [a, ca] = S[k - 1]!,
        [b, cb] = S[k]!,
        u = (f - a) / (b - a);
      return ca.map((v, j) => Math.round(v + (cb[j]! - v) * u));
    }
  return S[S.length - 1]![1];
};

/** 5 × 5 AROME cells (0.025°) around the place, coloured by (fictitious) terrain height. viewBox 0 0 520 420. */
/** The 5 x 5 AROME grid cells around a place with their real orography (`cells`, written by the batch);
 * a message until the batch has computed them. viewBox 0 0 520 420. */
export function mailleSvg(nom: string, lat: number, lon: number, alt: number | null, cells: Cells | null | undefined) {
  if (!cells)
    return {
      svg: `<text x="260" y="210" text-anchor="middle" font-size="13" fill="${C_TXT}">${tr("Altitudes des mailles disponibles après le prochain run AROME.")}</text>`,
      caption: tr("grille AROME 0,025° · 5 × 5 mailles"),
    };
  const NG = cells.alt.length,
    C = cells.step,
    h = (NG - 1) / 2,
    cla = cells.lat0,
    clo = cells.lon0,
    kx = 111.32 * Math.cos(cla * D2R) * C,
    ky = 111.2 * C,
    W = 520,
    H = 420,
    M = 30,
    CB = 54,
    sc = Math.min((W - 2 * M - CB) / (NG * kx), (H - 2 * M - 26) / (NG * ky)),
    gw = NG * kx * sc,
    gh = NG * ky * sc,
    x0 = (W - CB - gw) / 2,
    y0 = M;
  const XL = (lo: number) => x0 + ((lo - (clo - (h + 0.5) * C)) / C) * kx * sc,
    YL = (la: number) => y0 + ((cla + (h + 0.5) * C - la) / C) * ky * sc,
    A: [number, number, number | null][] = [];
  // rows north to south, columns west to east
  cells.alt.forEach((row, i) => row.forEach((v, j) => A.push([h - i, j - h, v == null ? null : Math.round(v)])));
  const vals = A.map((q) => q[2]).filter((v): v is number => v != null),
    lo0 = vals.length ? Math.min(...vals) : 0,
    hi0 = vals.length ? Math.max(...vals) : 0,
    span = Math.max(50, hi0 - lo0);
  let g = "";
  A.forEach(([a, b, al]) => {
    const x = XL(clo + b * C - C / 2),
      y = YL(cla + a * C + C / 2),
      cen = !a && !b,
      c = al == null ? [70, 76, 92] : relCol((al - lo0) / span),
      dark = c[0]! * 0.3 + c[1]! * 0.59 + c[2]! * 0.11 > 150;
    g +=
      `<rect x="${x}" y="${y}" width="${kx * sc}" height="${ky * sc}" fill="rgb(${c})" stroke="${cen ? "#f2c14e" : "rgba(10,15,29,.7)"}" stroke-width="${cen ? 3 : 0.8}"/>` +
      `<text x="${x + (kx * sc) / 2}" y="${y + ky * sc - 5}" text-anchor="middle" font-size="10.5" fill="${dark ? "#111" : "#f4f6fb"}" font-weight="${cen ? 700 : 500}">${al == null ? "–" : `${al} m`}</text>`;
  });
  g += `<text x="${x0 + gw / 2}" y="${y0 - 9}" text-anchor="middle" font-size="11" fill="#f2c14e">${tr(`maille du site (cadre jaune) · centre ${cla.toFixed(3)} N · ${clo.toFixed(3)} E`)}</text>`;
  {
    const x = XL(lon),
      y = YL(lat),
      yt = YL(cla + C / 2),
      ty = y - yt > 26 ? y - 8 : y + 20;
    g += `<circle cx="${x}" cy="${y}" r="6" fill="#f2a23a" stroke="#000" stroke-width="1.5"/><text x="${x + 9}" y="${ty}" font-size="12" font-weight="700" fill="#fff" stroke="#000" stroke-width="3" paint-order="stroke">${esc(nom)}${alt != null ? `<tspan fill="#ff4d4d" font-size="14" dx="5">${Math.round(alt)} m</tspan>` : ""}</text>`;
  }
  const km = kx < 1.5 ? 2 : 5,
    sx = x0,
    sy = y0 + gh + 18;
  g += `<line x1="${sx}" x2="${sx + km * sc}" y1="${sy}" y2="${sy}" stroke="#fff" stroke-width="2"/><line x1="${sx}" x2="${sx}" y1="${sy - 4}" y2="${sy + 4}" stroke="#fff"/><line x1="${sx + km * sc}" x2="${sx + km * sc}" y1="${sy - 4}" y2="${sy + 4}" stroke="#fff"/><text x="${sx + (km * sc) / 2}" y="${sy + 15}" text-anchor="middle" font-size="11" fill="#fff">${km} km</text>`;
  g += `<text x="${x0 + gw}" y="${sy + 4}" text-anchor="end" font-size="11" fill="${C_TXT}">${tr("maille")} ${kx.toFixed(1)} × ${ky.toFixed(1)} km</text><text x="${x0 + gw - 10}" y="${y0 + 16}" font-size="12" font-weight="700" fill="#fff" stroke="#000" stroke-width="3" paint-order="stroke" text-anchor="middle">N</text><path d="M${x0 + gw - 10},${y0 + 20} l-4,10 l4,-3 l4,3 z" fill="#fff" stroke="#000" stroke-width="0.6"/>`;
  {
    const bx = x0 + gw + 18,
      bw = 12;
    for (let k = 0; k < 40; k++)
      g += `<rect x="${bx}" y="${y0 + gh - ((k + 1) * gh) / 40}" width="${bw}" height="${gh / 40 + 0.6}" fill="rgb(${relCol((k + 0.5) / 40)})"/>`;
    g += `<rect x="${bx}" y="${y0}" width="${bw}" height="${gh}" fill="none" stroke="#0a0f1d"/><text x="${bx + bw + 4}" y="${y0 + 9}" font-size="10" fill="${C_TXT}">${lo0 + span} m</text><text x="${bx + bw + 4}" y="${y0 + gh}" font-size="10" fill="${C_TXT}">${lo0} m</text><text x="${bx + bw / 2}" y="${y0 - 9}" text-anchor="middle" font-size="10" fill="${C_TXT}">${tr("altitude")}</text>`;
  }
  return {
    svg: g,
    caption: tr(`grille AROME 0,025° · ${NG} × ${NG} mailles · altitudes du relief AROME`),
  };
}

/* ---------- wind roses (Mes lieux) ---------- */

export const ROSE_SECT = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];

/** One hour of a wind rose: direction the wind comes from [deg], speed [km/h], colour value. */
export type RosePt = { dir: number; speed: number; val: number };

/** Sector (8 points of the compass) of a direction. */
export const roseSector = (dir: number) => ROSE_SECT[Math.floor((((dir + 22.5) % 360) + 360) % 360 / 45)]!;

/** Best sector: lowest median colour value over the sectors with at least `minH` hours. */
export function roseBest(pts: RosePt[], minH = 5): { sect: string; med: number; n: number } | null {
  const by = new Map<string, number[]>();
  pts.forEach((p) => (by.get(roseSector(p.dir)) ?? by.set(roseSector(p.dir), []).get(roseSector(p.dir))!).push(p.val));
  let best: { sect: string; med: number; n: number } | null = null;
  by.forEach((v, sect) => {
    if (v.length < minH) return;
    const m = med(v);
    if (!best || m < best.med) best = { sect, med: m, n: v.length };
  });
  return best;
}

/** Polar scatter (north up, clockwise): angle = direction the wind comes from, radius = speed [km/h], colour =
 * value on turbo between lo and hi (low = blue = good, high = red = bad, as the map), white outlines. Dark-panel style of the site. */
export function windRoseSvg(pts: RosePt[], lo: number, hi: number): string {
  const S = 300,
    C = S / 2,
    R = 118;
  const vmax = Math.max(10, ...pts.map((p) => p.speed));
  const step = vmax > 120 ? 40 : vmax > 60 ? 20 : vmax > 30 ? 10 : 5,
    top = Math.ceil(vmax / step) * step,
    rr = (v: number) => (Math.min(v, top) / top) * R,
    xy = (dir: number, v: number) => [C + rr(v) * Math.sin(dir * D2R), C - rr(v) * Math.cos(dir * D2R)] as const;
  let g = `<circle cx="${C}" cy="${C}" r="${R}" fill="#1b2438" stroke="#3a4258"/>`;
  for (let v = step; v < top; v += step) g += `<circle cx="${C}" cy="${C}" r="${rr(v)}" fill="none" stroke="#3a4258" stroke-width="0.7"/>`;
  ROSE_SECT.forEach((lab, k) => {
    const a = k * 45,
      [x, y] = xy(a, top),
      lx = C + (R + 15) * Math.sin(a * D2R),
      ly = C - (R + 15) * Math.cos(a * D2R) + 4;
    g += `<line x1="${C}" y1="${C}" x2="${x}" y2="${y}" stroke="#3a4258" stroke-width="0.7"/>`;
    g += `<text x="${lx}" y="${ly}" text-anchor="middle" font-size="11" font-weight="${k % 2 ? 400 : 600}" fill="${k % 2 ? C_TXT : "#e6ebf6"}">${tr(lab)}</text>`;
  });
  for (let v = step; v <= top; v += step) {
    const [x, y] = xy(22.5, v);
    g += `<text x="${x + 2}" y="${y}" font-size="9" fill="${C_TXT}">${v}</text>`;
  }
  g += `<text x="${C + R * 0.42}" y="${C - R - 16}" font-size="9" fill="${C_TXT}">km/h</text>`;
  // worst values drawn last, on top
  [...pts]
    .sort((a, b) => a.val - b.val)
    .forEach((p) => {
      const [x, y] = xy(p.dir, p.speed),
        c = turbo(Math.min(1, Math.max(0, (p.val - lo) / (hi - lo || 1))));
      g += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.8" fill="rgb(${c})" stroke="#fff" stroke-width="0.8"/>`;
    });
  return g;
}
