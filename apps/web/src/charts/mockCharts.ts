/** SVG-string charts over the fictitious model (mockup's drawPrev / cn2Svg / drawCorr). */
import { tr } from "../i18n";
import {
  conv,
  currentEpisode,
  episodes,
  hbl,
  hhOf,
  I0,
  I1,
  isN,
  NOW,
  nightSegs,
  prof,
  REF,
  see,
  Z,
} from "../mock/engine";
import type { K3, UiState } from "../store";
import { C_AR, C_DAY, C_LINE, C_NIGHT, C_OBS, C_OBSD, C_TXT, corr, dnText, fmt, HOUR, med, pl, yaxis } from "../lib/util";

const lab = (i: number) => {
  const d = new Date(REF + i * HOUR);
  return String(d.getUTCDate()).padStart(2, "0") + "/" + String(d.getUTCMonth() + 1).padStart(2, "0");
};

export function taxis(X: (i: number) => number, i0: number, i1: number, y: number) {
  let g = "";
  for (let i = Math.ceil(i0); i <= i1; i++) {
    const h = hhOf(i);
    g += `<line x1="${X(i)}" x2="${X(i)}" y1="${y}" y2="${y + 4}" stroke="${C_LINE}"/>`;
    if (h % 2 === 0)
      g += `<text x="${X(i)}" y="${y + 16}" text-anchor="middle" font-size="11" fill="${h === 0 ? "#e6ebf6" : C_TXT}" ${h === 0 ? 'font-weight="500"' : ""}>${h === 0 ? lab(i) : h}</text>`;
  }
  return g;
}

export function nightLabels(X: (i: number) => number, i0: number, i1: number, y: number) {
  let g = "",
    s = Math.floor(i0),
    cur = isN(s);
  for (let i = s + 1; i <= i1; i++) {
    const n = i < i1 ? isN(i) : !cur;
    if (n !== cur || i === i1) {
      if (i - s >= 3) g += dnText((X(s) + X(i)) / 2, y, cur);
      s = i;
      cur = n;
    }
  }
  return g;
}

const VI = ["#440154", "#414487", "#2a788e", "#22a884", "#7ad151", "#fde725"];
const viridis = (v: number) => {
  let x = (Math.log10(Math.max(v, 1e-20)) + 18) / 4;
  x = Math.max(0, Math.min(0.999, x)) * 5;
  const k = Math.floor(x),
    f = x - k,
    a = VI[k]!,
    b = VI[k + 1]!,
    c = (j: number) => Math.round(parseInt(a.substr(j, 2), 16) * (1 - f) + parseInt(b.substr(j, 2), 16) * f);
  return `rgb(${c(1)},${c(3)},${c(5)})`;
};

type Flags = Pick<UiState, "mesf">;

/** Cn² panel (altitude × time) with the seeing on the right axis. viewBox 0 0 900 270. */
export function cn2Svg(K: K3, KCAL: K3, OB: boolean, ui: Flags, f = 1) {
  const W = 900,
    H = 270,
    L = 48,
    R = 84,
    T = 8,
    B = 30,
    pw = W - L - R,
    ph = H - T - B,
    X = (i: number) => L + ((i - I0) / (I1 - I0)) * pw,
    lz = (z: number) => T + ph - ((Math.log10(z) - 1) / 3) * ph,
    cw = pw / (I1 - I0);
  const ep = currentEpisode(f);
  let g = "";
  for (let i = I0; i < I1; i++) {
    const p = i === I0 ? null : prof(i, K, KCAL);
    for (let k = 0; k < Z.length - 1; k++) {
      const y0 = lz(Z[k + 1]!),
        y1 = lz(Z[k]!);
      g += `<rect x="${X(i)}" y="${y0}" width="${cw + 0.5}" height="${y1 - y0 + 0.5}" fill="${p ? viridis(p[k]!.v) : C_NIGHT}"/>`;
    }
  }
  let run: number[] = [];
  const flush = () => {
    if (run.length) {
      let d = `M${X(run[0]!)},${lz(10)}`;
      run.forEach((i) => {
        const y = lz(hbl(i));
        d += `L${X(i)},${y}L${X(i + 1)},${y}`;
      });
      d += `L${X(run[run.length - 1]! + 1)},${lz(10)}Z`;
      g += `<path d="${d}" fill="url(#hh)" fill-opacity=".5" stroke="#000"/>`;
    }
    run = [];
  };
  for (let i = I0 + 1; i < I1; i++) {
    if (conv(i)) run.push(i);
    else flush();
  }
  flush();
  g += `<text x="${X(I0) + cw / 2}" y="${T + ph / 2}" font-size="10" text-anchor="middle" fill="${C_TXT}" transform="rotate(-90 ${X(I0) + cw / 2} ${T + ph / 2})">${tr("H+0 sans TKE")}</text>`;
  [10, 100, 1000, 10000].forEach(
    (z) =>
      (g += `<text x="${L - 5}" y="${lz(z) + 4}" text-anchor="end" font-size="11" fill="${C_TXT}">${z >= 1000 ? z / 1000 + " km" : z + " m"}</text>`),
  );
  g += taxis(X, I0, I1, T + ph) + nightLabels(X, I0 + 1, I1, T + 14);
  const sv: number[] = [];
  for (let i = I0 + 1; i <= I1; i++) sv.push(see(i, K, KCAL));
  const smax = Math.max(4, Math.ceil(Math.max(...sv, ...(OB ? ep.H.map((h) => h.m) : [])) * 1.1)),
    YS = (v: number) => T + ph - (Math.min(v, smax) / smax) * ph;
  nightSegs(sv.map((_, j) => I0 + 1 + j)).forEach((s) => {
    const q = s.map((i) => [X(i), YS(sv[i - I0 - 1]!)]);
    g += pl(q, 'stroke="#000" stroke-width="4"') + pl(q, 'stroke="#fff" stroke-width="2"');
  });
  if (OB && ui.mesf.brut)
    ep.P.filter((p) => isN(p.t)).forEach(
      (p) => (g += `<circle cx="${X(p.t)}" cy="${YS(p.v)}" r="1.5" fill="#fff" opacity=".75"/>`),
    );
  if (OB && ui.mesf.horaire)
    ep.H.filter((h) => isN(h.t)).forEach(
      (h) => (g += `<circle cx="${X(h.t)}" cy="${YS(h.m)}" r="3.6" fill="#fff" stroke="#000"/>`),
    );
  const st = smax > 8 ? 2 : 1;
  for (let v = 0; v <= smax; v += st) g += `<text x="${L + pw + 5}" y="${YS(v) + 4}" font-size="11" fill="${C_TXT}">${v}"</text>`;
  const cx = W - 30;
  for (let k = 0; k < 40; k++)
    g += `<rect x="${cx}" y="${T + ph - ((k + 1) * ph) / 40}" width="10" height="${ph / 40 + 0.6}" fill="${viridis(Math.pow(10, -18 + (4 * (k + 0.5)) / 40))}"/>`;
  [-18, -17, -16, -15, -14].forEach(
    (e) =>
      (g += `<text x="${cx - 3}" y="${T + ph - ((e + 18) / 4) * ph + 4}" text-anchor="end" font-size="10" fill="${C_TXT}">${e}</text>`),
  );
  g += `<text x="${cx + 5}" y="${H - 4}" text-anchor="middle" font-size="10" fill="${C_TXT}">log Cn²</text>`;
  return g;
}

/** Forecast seeing (V2bd with the K in use, fitted K dashed when manual). viewBox 0 0 900 220. */
export function prevSvg(K: K3, KCAL: K3, manual: boolean, OB: boolean, ui: Flags, f = 1) {
  const W = 900,
    H = 220,
    L = 36,
    R = 10,
    T = 10,
    B = 30,
    pw = W - L - R,
    ph = H - T - B,
    X = (i: number) => L + ((i - I0) / (I1 - I0)) * pw;
  const ep = currentEpisode(f);
  const r: number[] = [];
  for (let i = I0 + 1; i <= I1; i++) r.push(i);
  const ymax = Math.ceil(
      Math.max(...r.map((i) => Math.max(see(i, K, KCAL), see(i, KCAL, KCAL))), ...(OB ? ep.H.map((h) => h.m) : [])) * 1.15,
    ),
    Y = (v: number) => T + ph - (Math.min(v, ymax) / ymax) * ph;
  let g = "";
  for (let i = I0; i < I1; i++)
    if (!isN(i)) g += `<rect x="${X(i)}" y="${T}" width="${pw / (I1 - I0) + 0.6}" height="${ph}" fill="${C_DAY}"/>`;
  g += yaxis(Y, L, W - R, ymax, ymax > 8 ? 2 : 1) + taxis(X, I0, I1, T + ph) + nightLabels(X, I0, I1, T + 13);
  if (manual)
    nightSegs(r).forEach((s) => {
      g += pl(
        s.map((i) => [X(i), Y(see(i, KCAL, KCAL))]),
        'stroke="#9cc7ff" stroke-width="1.5" stroke-dasharray="5 4"',
      );
    });
  nightSegs(r).forEach((s) => {
    g += pl(
      s.map((i) => [X(i), Y(see(i, K, KCAL))]),
      `stroke="${C_AR}" stroke-width="2.2"`,
    );
  });
  if (OB) {
    if (ui.mesf.brut)
      ep.P.forEach((p) => isN(p.t) && (g += `<circle cx="${X(p.t)}" cy="${Y(p.v)}" r="1.9" fill="${C_OBS}"/>`));
    if (ui.mesf.horaire)
      ep.H.forEach(
        (h) =>
          isN(h.t) &&
          (g += `<rect x="${X(h.t) - 3.5}" y="${Y(h.m) - 3.5}" width="11" height="11" fill="${C_OBSD}" stroke="#0a0f1d" stroke-width="1"/>`),
      );
  }
  g += `<line x1="${X(NOW)}" x2="${X(NOW)}" y1="${T}" y2="${T + ph}" stroke="#e6ebf6" stroke-dasharray="2 3"/><text x="${X(NOW) + 4}" y="${T + 12}" font-size="11" fill="#e6ebf6">${tr("maintenant")}</text>`;
  g += `<rect x="${X(I0)}" y="${T}" width="${pw / (I1 - I0)}" height="${ph}" fill="#0a0f1d" opacity=".75"/>`;
  g += `<text x="${L + 6}" y="${T + ph - 6}" font-size="11" fill="${C_TXT}">K_TKE = ${fmt(K[0])}  K_CIS = ${fmt(K[1])}  K_conv = 0.1</text>`;
  return g;
}

/** Forecast vs measured, hourly medians and per-night medians. viewBox 0 0 340 300. */
export function corrMock(K: K3, KCAL: K3, f = 1) {
  const pts: { x: number; y: number; n: boolean }[] = [],
    grp: { x: number; y: number; n: boolean }[] = [];
  episodes(f).forEach((e, n) => {
    const G: Record<string, typeof pts> = {};
    e.H.forEach((h) => {
      const p = { x: h.m, y: see(h.t, K, KCAL), n: isN(h.t) };
      pts.push(p);
      const key = n + (p.n ? "n" + Math.floor((h.t + 6) / 24) : "j" + Math.floor(h.t / 24));
      (G[key] = G[key] || []).push(p);
    });
    Object.values(G).forEach((a) => {
      if (a.length >= 2) grp.push({ x: med(a.map((p) => p.x)), y: med(a.map((p) => p.y)), n: a[0]!.n });
    });
  });
  const cr = (a: typeof pts) =>
    corr(
      a.map((p) => p.x),
      a.map((p) => p.y),
    );
  const W = 340,
    H = 300,
    L = 34,
    T = 8,
    B = 32,
    R = 10,
    pw = W - L - R,
    ph = H - T - B,
    m = Math.ceil(Math.max(...pts.map((p) => Math.max(p.x, p.y))) * 1.08),
    X = (v: number) => L + (v / m) * pw,
    Y = (v: number) => T + ph - (v / m) * ph,
    st = m > 8 ? 2 : 1;
  let g = "";
  for (let v = 0; v <= m; v += st)
    g += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${C_LINE}" stroke-width="0.6"/><line y1="${T}" y2="${T + ph}" x1="${X(v)}" x2="${X(v)}" stroke="${C_LINE}" stroke-width="0.6"/><text x="${L - 5}" y="${Y(v) + 4}" text-anchor="end" font-size="11" fill="${C_TXT}">${v}"</text><text x="${X(v)}" y="${T + ph + 14}" text-anchor="middle" font-size="11" fill="${C_TXT}">${v}"</text>`;
  g += `<line x1="${X(0)}" y1="${Y(0)}" x2="${X(m)}" y2="${Y(m)}" stroke="${C_TXT}" stroke-dasharray="4 3"/>`;
  pts.forEach((p) => (g += `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="3.2" fill="${p.n ? "#2a78d6" : "#e34948"}"/>`));
  grp.forEach(
    (p) =>
      (g += `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="9" fill="none" stroke="${p.n ? "#2a78d6" : "#e34948"}" stroke-width="2"/>`),
  );
  g += `<text x="${L + pw / 2}" y="${H - 2}" text-anchor="middle" font-size="11" fill="${C_TXT}">${tr("mesuré (médiane horaire)")}</text><text x="10" y="${T + ph / 2}" text-anchor="middle" font-size="11" fill="${C_TXT}" transform="rotate(-90 10 ${T + ph / 2})">${tr("prévu V2bd")}</text>`;
  const b = pts.reduce((s, p) => s + p.y - p.x, 0) / pts.length,
    ea = pts.reduce((s, p) => s + Math.abs(p.y - p.x), 0) / pts.length;
  return {
    svg: g,
    ct: tr(`r = ${cr(pts).toFixed(2)} · n = ${pts.length} h · biais ${b >= 0 ? "+" : ""}${b.toFixed(2)}" · écart moyen ${ea.toFixed(2)}"`),
    rDayNight: cr(pts.filter((p) => !p.n)).toFixed(2) + " / " + cr(pts.filter((p) => p.n)).toFixed(2),
    bias: (b >= 0 ? "+" : "") + b.toFixed(2) + '" · ' + ea.toFixed(2) + '"',
  };
}
