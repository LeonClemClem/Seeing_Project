/**
 * Global seeing map (canvas): only real data. The maps of the latest run (GET /api/map, V2bd over the
 * whole AROME grid, land and sea, night hours 19h-05h UTC, mean of the night 20h-04h) and the AROME
 * orography drawn as in research/carte_seeing.py: coastline = 1 m contour of the 5x5-median relief,
 * relief contours (1000 / 2000 m in white on large views, every 250 m with labels when zoomed), cities.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as RPointerEvent } from "react";
import { useLocation } from "react-router-dom";

import { ColorBar, Seg } from "../components/ui";
import { useUser } from "../data/auth";
import { MAX_PLACES, selectPlace, siteToPlace, useCurrentPlace, usePlaceActions, usePlaces } from "../data/places";
import { tr } from "../i18n";
import { CORSE, DOM, FRA, inDomain, inPoly, LANDS, parseCoord, SARD, VILLES, ZONES, type Box } from "../lib/geo";
import { useGlobalMap, useLatestRunTime } from "../lib/hooks";
import type { MapGrid } from "../api";
import { canvasToPng, downloadBlob, encodeGif } from "../lib/export";
import { D2R, esc, fmt, pad2, runLabel, turbo, turboGradient } from "../lib/util";
import { REF } from "../mock/engine";
import { setState, useUi } from "../store";

const CW = 720,
  CH = 700;
/** Max zoom: 100 km tall. */
const ZMIN = 100 / 111.2;
/* Map hours: 19h-05h UTC for 2 nights (NH frames each); the night mean uses 20h-04h only. */
const NIGHT_H = [19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5],
  NH = NIGHT_H.length,
  MAPH = [...NIGHT_H, ...NIGHT_H],
  inMean = (i: number) => MAPH[i] !== 19 && MAPH[i] !== 5;
const LEADMAX = 51;
const KGLOB = [1, 30, 0.1];
const JS = ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."];
const LUT = [...Array(256)].map((_, k) => turbo(k / 255));
/** Colour of a seeing value: turbo on a fixed 0-10" range with a fixed square-root stretch, the same for
 * every run so that nights can be compared (1" -> 32 %, 2" -> 45 %, 3" -> 55 %, 5" -> 71 % of the scale). */
const SEE_TOP = 10;
const seeColor = (s: number) => LUT[Math.round(Math.sqrt(Math.min(Math.max(s, 0), SEE_TOP) / SEE_TOP) * 255)]!;
/** Views taller than this show the large-zone style (1000 / 2000 m contours), else 250 m contours. */
const FINE_VIEW_DEG = 4;

function fitBox(b: Box): Box {
  const r = CW / CH,
    cla = (b.la0 + b.la1) / 2,
    c = Math.cos(cla * D2R);
  let sl = b.la1 - b.la0,
    so = b.lo1 - b.lo0;
  if ((so * c) / sl > r) sl = (so * c) / r;
  else so = (sl * r) / c;
  return { la0: cla - sl / 2, la1: cla + sl / 2, lo0: (b.lo0 + b.lo1) / 2 - so / 2, lo1: (b.lo0 + b.lo1) / 2 + so / 2 };
}
/** The whole AROME domain fills the view: no panning then, only zooming in. */
const isFullView = (v: Box) => v.la1 - v.la0 >= fitBox(DOM).la1 - fitBox(DOM).la0 - 1e-9;
/** Clamp zoom and centre to the domain; the whole-domain view is always centred on the domain. */
function clampView(v: Box): Box {
  const DV = fitBox(DOM),
    sl = v.la1 - v.la0,
    so = v.lo1 - v.lo0,
    sl2 = Math.min(DV.la1 - DV.la0, Math.max(ZMIN, sl)),
    f = sl2 / sl,
    cla = (v.la0 + v.la1) / 2,
    clo = (v.lo0 + v.lo1) / 2;
  if (sl2 >= DV.la1 - DV.la0 - 1e-9) return DV;
  const nl = Math.min(DOM.la1, Math.max(DOM.la0, cla)),
    no = Math.min(DOM.lo1, Math.max(DOM.lo0, clo));
  return { la0: nl - sl2 / 2, la1: nl + sl2 / 2, lo0: no - (so * f) / 2, lo1: no + (so * f) / 2 };
}
interface Cache {
  key: string;
  las: Float32Array;
  los: Float32Array;
  /** invisible land mask, only for the zone hit test of the domain view */
  mask: Uint8ClampedArray;
}

function landMask(V: Box): Uint8ClampedArray {
  const c = document.createElement("canvas");
  c.width = CW;
  c.height = CH;
  const g = c.getContext("2d")!;
  const P = (la: number, lo: number) => [((lo - V.lo0) / (V.lo1 - V.lo0)) * CW, ((V.la1 - la) / (V.la1 - V.la0)) * CH] as const;
  g.fillStyle = "#000";
  g.strokeStyle = "#000";
  g.lineWidth = Math.max(2, (CW / (V.lo1 - V.lo0)) * 0.12);
  LANDS.forEach((poly) => {
    g.beginPath();
    poly.forEach((q, k) => {
      const [x, y] = P(...q);
      if (k) g.lineTo(x, y);
      else g.moveTo(x, y);
    });
    g.closePath();
    g.fill();
    g.stroke();
  });
  return g.getImageData(0, 0, CW, CH).data;
}

function viewCache(V: Box, prev: Cache | null): Cache {
  const key = [V.la0, V.la1, V.lo0, V.lo1].map((v) => v.toFixed(5)).join(",");
  if (prev?.key === key) return prev;
  const n = CW * CH,
    las = new Float32Array(n),
    los = new Float32Array(n);
  for (let y = 0; y < CH; y++)
    for (let x = 0; x < CW; x++) {
      las[y * CW + x] = V.la1 - (y / CH) * (V.la1 - V.la0);
      los[y * CW + x] = V.lo0 + (x / CW) * (V.lo1 - V.lo0);
    }
  return { key, las, los, mask: landMask(V) };
}

/** Contour segments of a grid at `level`, flat [lat1, lon1, lat2, lon2, ...]: marching squares with linear
 * interpolation along the cell edges, as matplotlib's `contour` (saddles split with the cell centre). */
function contourSegs(g: MapGrid, a: Float32Array, level: number): Float32Array {
  const out: number[] = [];
  const { nx, ny, lat0, lon0, dlat, dlon } = g;
  // corners 0 (r, c), 1 (r, c+1), 2 (r+1, c+1), 3 (r+1, c); edges as corner pairs
  const EDGES = [[0, 1], [1, 2], [3, 2], [0, 3]] as const;
  const v = [0, 0, 0, 0],
    rc = [[0, 0], [0, 1], [1, 1], [1, 0]] as const;
  for (let r = 0; r < ny - 1; r++)
    for (let c = 0; c < nx - 1; c++) {
      v[0] = a[r * nx + c]!;
      v[1] = a[r * nx + c + 1]!;
      v[2] = a[(r + 1) * nx + c + 1]!;
      v[3] = a[(r + 1) * nx + c]!;
      if (v.some((x) => isNaN(x))) continue;
      const up = v.map((x) => x >= level);
      if (up.every((u) => u) || up.every((u) => !u)) continue;
      const pts: [number, number][] = [];
      EDGES.forEach(([p, q], e) => {
        if (up[p] === up[q]) return;
        const f = (level - v[p]!) / (v[q]! - v[p]!);
        pts[e] = [r + rc[p]![0] + f * (rc[q]![0] - rc[p]![0]), c + rc[p]![1] + f * (rc[q]![1] - rc[p]![1])];
      });
      const ks = pts.map((_, e) => e).filter((e) => pts[e]);
      let pairs: [number, number][];
      if (ks.length === 2) pairs = [[ks[0]!, ks[1]!]];
      else {
        // saddle: corners 0 and 2 on one side, 1 and 3 on the other
        const centreUp = (v[0]! + v[1]! + v[2]! + v[3]!) / 4 >= level;
        pairs = centreUp === up[0] ? [[0, 1], [2, 3]] : [[3, 0], [1, 2]];
      }
      for (const [e1, e2] of pairs) {
        const A = pts[e1]!,
          B = pts[e2]!;
        out.push(lat0 + A[0] * dlat, lon0 + A[1] * dlon, lat0 + B[0] * dlat, lon0 + B[1] * dlon);
      }
    }
  return Float32Array.from(out);
}

/** 5x5 median of a grid (NaN ignored), as scipy.ndimage.median_filter(relief, 5) for the coastline. */
function median5(g: MapGrid, a: Float32Array): Float32Array {
  const out = new Float32Array(a.length),
    w: number[] = [];
  for (let r = 0; r < g.ny; r++)
    for (let c = 0; c < g.nx; c++) {
      w.length = 0;
      for (let dr = -2; dr <= 2; dr++)
        for (let dc = -2; dc <= 2; dc++) {
          const rr = r + dr,
            cc = c + dc;
          if (rr < 0 || cc < 0 || rr >= g.ny || cc >= g.nx) continue;
          const v = a[rr * g.nx + cc]!;
          if (!isNaN(v)) w.push(v);
        }
      w.sort((x, y) => x - y);
      out[r * g.nx + c] = w.length ? w[w.length >> 1]! : NaN;
    }
  return out;
}

/** Land of the 5x5-median relief (>= 1 m, the coastline level) without the islets made by the ripples of the
 * AROME orography over the sea: a connected patch (4-neighbours) is kept only if its raw relief reaches
 * ISLET_MIN somewhere. The ripples stay below 3 m, real islands (Guernsey, Ouessant...) reach 6 m and more. */
const ISLET_MIN = 5;
function landOf(g: MapGrid, med: Float32Array, raw: Float32Array): Uint8Array {
  const n = g.nx * g.ny,
    land = new Uint8Array(n),
    seen = new Uint8Array(n),
    stack: number[] = [],
    patch: number[] = [];
  for (let i0 = 0; i0 < n; i0++) {
    if (seen[i0] || !(med[i0]! >= 1)) continue;
    patch.length = 0;
    let top = -Infinity;
    stack.push(i0);
    seen[i0] = 1;
    while (stack.length) {
      const i = stack.pop()!,
        r = Math.floor(i / g.nx),
        c = i - r * g.nx;
      patch.push(i);
      if (raw[i]! > top) top = raw[i]!;
      for (const j of [c > 0 ? i - 1 : -1, c < g.nx - 1 ? i + 1 : -1, r > 0 ? i - g.nx : -1, r < g.ny - 1 ? i + g.nx : -1])
        if (j >= 0 && !seen[j] && med[j]! >= 1) {
          seen[j] = 1;
          stack.push(j);
        }
    }
    if (top >= ISLET_MIN) for (const i of patch) land[i] = 1;
  }
  return land;
}

type PinKind = "pub" | "sh" | "mine";
const PIN_FILL: Record<PinKind, string> = { pub: "#fff", sh: "#9cc7ff", mine: "#f2a23a" };
/** Path of a map pin: tip on (x, y), round head of radius r centred 2.1 r above. */
function pinPath(r: number) {
  const d = 2.1 * r,
    f = Math.acos(r / d),
    p = (a: number) => `${(r * Math.cos(a)).toFixed(2)},${(-d + r * Math.sin(a)).toFixed(2)}`;
  return `M0,0 L${p(Math.PI / 2 + f)} A${r},${r} 0 1 1 ${p(Math.PI / 2 - f)} Z`;
}
/** Glyph in the pin head: observatory dome (public monitor), dot (shared place), star (my places). */
function pinGlyph(r: number, kind: PinKind) {
  const cy = -2.1 * r;
  if (kind === "pub") {
    const b = cy + 0.4 * r,
      dr = 0.55 * r;
    return `M${-dr},${b} A${dr},${dr} 0 0 1 ${dr},${b} Z M${-0.72 * r},${b} h${1.44 * r} v${0.2 * r} h${-1.44 * r} Z`;
  }
  if (kind === "sh") return `M${-0.36 * r},${cy} a${0.36 * r},${0.36 * r} 0 1 0 ${0.72 * r},0 a${0.36 * r},${0.36 * r} 0 1 0 ${-0.72 * r},0 Z`;
  let s = "";
  for (let k = 0; k < 10; k++) {
    const a = -Math.PI / 2 + (k * Math.PI) / 5,
      rr = k % 2 ? r * 0.27 : r * 0.62;
    s += `${k ? "L" : "M"}${(rr * Math.cos(a)).toFixed(2)},${(cy + rr * Math.sin(a)).toFixed(2)}`;
  }
  return s + "Z";
}
/** Map pin of a place, with a soft shadow at the tip. */
function pin(cx: CanvasRenderingContext2D, x: number, y: number, r: number, kind: PinKind) {
  cx.save();
  cx.translate(x, y);
  cx.beginPath();
  cx.ellipse(0, 0, 0.6 * r, 0.22 * r, 0, 0, 7);
  cx.fillStyle = "rgba(0,0,0,.35)";
  cx.fill();
  const body = new Path2D(pinPath(r));
  cx.fillStyle = PIN_FILL[kind];
  cx.fill(body);
  cx.strokeStyle = "#000";
  cx.lineWidth = 1.3;
  cx.stroke(body);
  cx.fillStyle = kind === "mine" ? "#fff" : "#0a0f1d";
  cx.fill(new Path2D(pinGlyph(r, kind)));
  cx.restore();
}
/** The same pin for the legend. */
function PinIcon({ kind }: { kind: PinKind }) {
  const r = 5;
  return (
    <svg width="14" height="18" viewBox="-7 -16.5 14 18" style={{ flex: "none" }} aria-hidden="true">
      <path d={pinPath(r)} fill={PIN_FILL[kind]} stroke="#000" strokeWidth="1" />
      <path d={pinGlyph(r, kind)} fill={kind === "mine" ? "#fff" : "#0a0f1d"} />
    </svg>
  );
}

type ZoneHit = [x: number, y: number, w: number, h: number, i: number];

/** Bilinear sampling of a map grid at (lat, lon), ignoring undefined corners; NaN outside. */
function sampler(g: MapGrid, a: Float32Array) {
  return (la: number, lo: number) => {
    const r = (la - g.lat0) / g.dlat,
      c = (lo - g.lon0) / g.dlon;
    if (!(r >= 0 && c >= 0 && r <= g.ny - 1 && c <= g.nx - 1)) return NaN;
    const r0 = Math.floor(r),
      c0 = Math.floor(c),
      r1 = Math.min(r0 + 1, g.ny - 1),
      c1 = Math.min(c0 + 1, g.nx - 1),
      fr = r - r0,
      fc = c - c0;
    let s = 0,
      w = 0;
    for (const [rr, cc, ww] of [
      [r0, c0, (1 - fr) * (1 - fc)],
      [r0, c1, (1 - fr) * fc],
      [r1, c0, fr * (1 - fc)],
      [r1, c1, fr * fc],
    ] as const) {
      const v = a[rr * g.nx + cc]!;
      if (!isNaN(v) && ww > 0) {
        s += v * ww;
        w += ww;
      }
    }
    return w > 0 ? s / w : NaN;
  };
}

export default function Carte() {
  const role = useUi((s) => s.role);
  const lang = useUi((s) => s.lang);
  const place = useCurrentPlace();
  const { pub, sh, mine } = usePlaces();
  const user = useUser();
  const { create: createPlace } = usePlaceActions();
  const { runTime } = useLatestRunTime();
  const gmap = useGlobalMap();
  const RUN0 = gmap ? Date.parse(gmap.meta.run_time) : runTime ? Date.parse(runTime) : REF + 12 * 3600000;

  const canvas = useRef<HTMLCanvasElement>(null);
  const cache = useRef<Cache | null>(null);
  const zones = useRef<ZoneHit[]>([]);
  const drag = useRef<{ x: number; y: number; moved: boolean; snap: HTMLCanvasElement } | null>(null);

  const [VW, setVW] = useState<Box>(() => fitBox(DOM));
  const [ext, setExt] = useState<"dom" | "zoom" | "reg">("dom");
  const [reg, setReg] = useState("");
  const [mode, setMode] = useState<"m" | "h">("m");
  const [MI, setMI] = useState(0);
  const [MNI, setMNI] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [MZH, setMZH] = useState(-1);
  const [tip, setTip] = useState<string | null>(null);
  const loc = useLocation();
  // "Créer un lieu ici" of the one-off forecast (Prévision) brings the coordinates
  const st0 = loc.state as { newPlace?: boolean; lat?: number; lon?: number } | null;
  const [newPt, setNewPt] = useState<[number, number] | null>(() => (st0?.lat != null && st0.lon != null ? [st0.lat, st0.lon] : null));
  const [showNew, setShowNew] = useState(() => !!st0?.newPlace);
  const [nl, setNl] = useState(() => ({
    lat: st0?.lat != null ? st0.lat.toFixed(5) : "",
    lon: st0?.lon != null ? st0.lon.toFixed(5) : "",
    name: "Nouveau lieu",
    share: false,
  }));
  const [nlMsg, setNlMsg] = useState<{ ok: boolean; t: string } | null>(null);

  const frameT = useCallback(
    (i: number) => {
      const k = Math.floor(i / NH),
        h = MAPH[i]!,
        r = new Date(RUN0),
        d = new Date(Date.UTC(r.getUTCFullYear(), r.getUTCMonth(), r.getUTCDate() + k, 20));
      if (h < 12) d.setUTCDate(d.getUTCDate() + 1);
      d.setUTCHours(h);
      return d;
    },
    [RUN0],
  );
  const NIGHTS = useMemo(
    () =>
      [0, 1]
        .map((k) => {
          const a = frameT(k * NH),
            b = frameT(k * NH + NH - 1);
          return { i0: k * NH, i1: k * NH + NH - 1, lab: `${pad2(a.getUTCDate())} au ${pad2(b.getUTCDate())}/${pad2(b.getUTCMonth() + 1)}` };
        })
        .filter((n) => (frameT(n.i0).getTime() - RUN0) / 3600000 <= LEADMAX),
    [frameT, RUN0],
  );
  const night = NIGHTS[Math.min(MNI, NIGHTS.length - 1)] ?? { i0: 0, i1: NH - 1, lab: "" };
  /** File name stamp: run and, hour by hour, the hour shown. */
  const fileStamp = () =>
    `run${new Date(RUN0).toISOString().slice(0, 13).replace(/[-T]/g, "")}Z_` +
    (mode === "m" ? `nuit_${night.lab.replace(/[^0-9]+/g, "-")}` : frameT(MI).toISOString().slice(0, 13).replace(/[-T]/g, "") + "h");
  const [gifBusy, setGifBusy] = useState(false);
  /** Animated GIF of the night: every hour of the chosen night, drawn one by one on the map canvas (the frames are
   * already loaded, each hour is drawn on the next paint), then the view is put back. */
  const exportGif = async () => {
    const cv = canvas.current?.getContext("2d");
    if (!cv) return;
    setGifBusy(true);
    const keep = { mode, MI, playing };
    setPlaying(false);
    setMode("h");
    const frames: ImageData[] = [];
    const paint = () => new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
    try {
      for (let i = night.i0; i <= night.i1; i++) {
        setMI(i);
        await paint();
        frames.push(cv.getImageData(0, 0, CW, CH));
      }
      downloadBlob(encodeGif(frames, 90), `carte_seeing_run${new Date(RUN0).toISOString().slice(0, 13).replace(/[-T]/g, "")}Z_nuit_${night.lab.replace(/[^0-9]+/g, "-")}.gif`);
    } finally {
      setMode(keep.mode);
      setMI(keep.MI);
      setPlaying(keep.playing);
      setGifBusy(false);
    }
  };


  /* Real map: the frame of the chosen hour, or the mean seeing of the night's frames. Hours the run
     does not cover are left out (no interpolation, no fictitious field): no value at all for a
     missing hour, and the mean says which hours it really uses. */
  const real = useMemo(() => {
    if (!gmap) return null;
    const idx = mode === "m" ? [...Array(night.i1 - night.i0 + 1)].map((_, k) => night.i0 + k).filter(inMean) : [MI];
    const used = idx.filter((i) => gmap.frames.has(Math.round((frameT(i).getTime() - RUN0) / 3600000)));
    const arrs = used.map((i) => gmap.frames.get(Math.round((frameT(i).getTime() - RUN0) / 3600000))!);
    if (!arrs.length) return { sample: (): number => NaN, hours: [] as number[], expected: idx.length };
    const n = arrs[0]!.length,
      mean = new Float32Array(n);
    for (let j = 0; j < n; j++) {
      let s = 0,
        c = 0;
      for (const a of arrs) {
        const v = a[j]!;
        if (!isNaN(v)) {
          s += v;
          c++;
        }
      }
      mean[j] = c ? s / c : NaN;
    }
    return { sample: sampler(gmap.meta.grid, mean), hours: used.map((i) => MAPH[i]!), expected: idx.length };
  }, [gmap, mode, MI, night.i0, night.i1, frameT, RUN0]);
  const sample = real?.sample ?? null;
  /** Real AROME orography of the map grid, when the run has it, and its 5x5 median (coastline). */
  const relReal = useMemo(() => (gmap?.relief ? sampler(gmap.meta.grid, gmap.relief) : null), [gmap]);
  /** Land of the AROME relief (coastline without the islets of the sea ripples): no relief drawn or read at sea. */
  const land = useMemo(() => {
    if (!gmap?.relief) return null;
    const g = gmap.meta.grid,
      med = median5(g, gmap.relief),
      l = landOf(g, med, gmap.relief);
    return { med: med.map((v, i) => (l[i] ? v : 0)), at: sampler(g, Float32Array.from(l)) };
  }, [gmap]);
  /** Contours as research/carte_seeing.py, once per map: domain views = coastline (1 m contour of the 5x5-median
   * relief, black 0.6) + 1000 / 2000 m (white 0.3, alpha 0.6); zoomed views = every 250 m (black 0.4, alpha
   * 0.5) with "… m" labels and no coastline. */
  const contours = useMemo(() => {
    if (!gmap?.relief || !land) return null;
    const g = gmap.meta.grid;
    return {
      coast: contourSegs(g, land.med, 1),
      major: [1000, 2000].map((lv) => contourSegs(g, gmap.relief!, lv)),
      fine: Array.from({ length: 11 }, (_, k) => 250 * (k + 1)).map((lv) => [lv, contourSegs(g, gmap.relief!, lv)] as const),
    };
  }, [gmap, land]);

  const toXY = useCallback(
    (la: number, lo: number) => [((lo - VW.lo0) / (VW.lo1 - VW.lo0)) * CW, ((VW.la1 - la) / (VW.la1 - VW.la0)) * CH] as const,
    [VW],
  );
  const LA = useCallback((y: number) => VW.la1 - (y / CH) * (VW.la1 - VW.la0), [VW]);
  const LO = useCallback((x: number) => VW.lo0 + (x / CW) * (VW.lo1 - VW.lo0), [VW]);

  /* ---------- drawing ---------- */
  useEffect(() => {
    const cv = canvas.current;
    if (!cv) return;
    const cx = cv.getContext("2d")!;
    const C = (cache.current = viewCache(VW, cache.current));
    const img = cx.createImageData(CW, CH),
      D = img.data;
    for (let j = 0; j < CW * CH; j++) {
      const p = j * 4,
        s = sample ? sample(C.las[j]!, C.los[j]!) : NaN;
      // no map yet, or hour not covered by the run: neutral grey (no fictitious field)
      const c = isNaN(s) ? [60, 66, 80] : seeColor(s);
      D[p] = c[0]!;
      D[p + 1] = c[1]!;
      D[p + 2] = c[2]!;
      D[p + 3] = 255;
    }
    cx.putImageData(img, 0, 0);
    // contours as smooth anti-aliased lines (matplotlib widths in points, the canvas is ~1.3 px per point)
    const fineView = VW.la1 - VW.la0 <= FINE_VIEW_DEG,
      labels: [number, number, string][] = [];
    const stroke = (s: Float32Array, style: string, w: number, lv?: number) => {
      cx.beginPath();
      let k = 0;
      for (let i = 0; i < s.length; i += 4) {
        const [x1, y1] = toXY(s[i]!, s[i + 1]!),
          [x2, y2] = toXY(s[i + 2]!, s[i + 3]!);
        if ((x1 < 0 && x2 < 0) || (x1 > CW && x2 > CW) || (y1 < 0 && y2 < 0) || (y1 > CH && y2 > CH)) continue;
        cx.moveTo(x1, y1);
        cx.lineTo(x2, y2);
        // clabel-like labels: spread out, at most 30
        if (lv != null && k++ % 40 === 0 && labels.length < 30 && x1 > 30 && x1 < CW - 60 && y1 > 20 && y1 < CH - 30)
          if (labels.every(([a, b2]) => (a - x1) ** 2 + (b2 - y1) ** 2 > 130 ** 2)) labels.push([x1, y1, `${lv} m`]);
      }
      cx.strokeStyle = style;
      cx.lineWidth = w;
      cx.lineCap = "round";
      cx.stroke();
    };
    if (contours) {
      if (fineView) contours.fine.forEach(([lv, s]) => stroke(s, "rgba(0,0,0,.5)", 0.55, lv));
      else {
        contours.major.forEach((s) => stroke(s, "rgba(255,255,255,.6)", 0.45));
        stroke(contours.coast, "#000", 0.8);
      }
    }
    const big = VW.la1 - VW.la0 < 3.2;
    cx.font = "9px 'IBM Plex Sans',sans-serif";
    labels.forEach(([x, y, txt]) => {
      cx.lineWidth = 2.5;
      cx.strokeStyle = "rgba(255,255,255,.55)";
      cx.strokeText(txt, x + 2, y - 2);
      cx.fillStyle = "#000";
      cx.fillText(txt, x + 2, y - 2);
    });
    if (!gmap) {
      cx.font = "500 14px 'IBM Plex Sans',sans-serif";
      cx.fillStyle = "#e6ebf6";
      cx.textAlign = "center";
      cx.fillText(tr("La carte apparaîtra après le prochain run du batch."), CW / 2, CH / 2);
      cx.textAlign = "left";
    }
    // Places shared by the community (the API blurs other members' positions by 5-11 km).
    sh.forEach(({ lat: la, lon: lo }) => {
      const [x, y] = toXY(la, lo);
      pin(cx, x, y, big ? 8 : 6, "sh");
    });
    cx.font = "500 12px 'IBM Plex Sans',sans-serif";
    const label = (t: string, x: number, y: number) => {
      cx.lineWidth = 3;
      cx.strokeStyle = "rgba(0,0,0,.8)";
      cx.strokeText(t, x, y);
      cx.fillStyle = "#fff";
      cx.fillText(t, x, y);
    };
    pub.forEach((s) => {
      const [x, y] = toXY(s.lat, s.lon);
      pin(cx, x, y, big ? 9 : 7, "pub");
      if (big) label(s.nom, x + 10, y - (big ? 14 : 10));
    });
    // Cities, as research/carte_seeing.py (ajoute_villes): white dots ringed in black, small translucent names.
    cx.font = `${big ? 11 : 9}px 'IBM Plex Sans',sans-serif`;
    const domView = VW.la1 - VW.la0 > 12;
    VILLES.forEach(([nom, la, lo, minor]) => {
      if (minor && domView) return;
      const [x, y] = toXY(la, lo);
      if (x < -20 || x > CW + 20 || y < -20 || y > CH + 20) return;
      cx.beginPath();
      cx.arc(x, y, big ? 3 : 2.2, 0, 7);
      cx.fillStyle = "#fff";
      cx.fill();
      cx.strokeStyle = "#000";
      cx.lineWidth = 0.9;
      cx.stroke();
      cx.lineWidth = 2;
      cx.strokeStyle = "rgba(255,255,255,.45)";
      cx.strokeText(nom, x + 4, y - 3);
      cx.fillStyle = "rgba(0,0,0,.6)";
      cx.fillText(nom, x + 4, y - 3);
    });
    cx.font = "500 12px 'IBM Plex Sans',sans-serif";
    // Only real places: the example places of a logged-out visitor are not drawn on the map.
    mine.filter((p) => p.real).forEach((p) => {
      const [x, y] = toXY(p.lat, p.lon);
      pin(cx, x, y, big ? 10 : 8, "mine");
      if (big) label(tr(p.nom), x + 12, y - (big ? 16 : 12));
    });
    const zh: ZoneHit[] = [];
    if (VW.la1 - VW.la0 > 12) {
      cx.font = "600 13px 'IBM Plex Sans',sans-serif";
      ZONES.forEach((z, i) => {
        const [x, y] = toXY(z[1], z[2]),
          name = tr(z[0]),
          w = cx.measureText(name).width + 18,
          h = 24,
          on = MZH === i;
        cx.fillStyle = on ? "rgba(242,193,78,.95)" : "rgba(10,15,29,.78)";
        cx.strokeStyle = on ? "#000" : "rgba(255,255,255,.75)";
        cx.lineWidth = 1.2;
        cx.beginPath();
        cx.roundRect(x - w / 2, y - h / 2, w, h, 12);
        cx.fill();
        cx.stroke();
        cx.fillStyle = on ? "#000" : "#fff";
        cx.textAlign = "center";
        cx.fillText(name, x, y + 4.5);
        cx.textAlign = "left";
        zh.push([x - w / 2, y - h / 2, w, h, i]);
        if (on) {
          const b = z[3],
            [x0, y0] = toXY(b.la1, b.lo0),
            [x1, y1] = toXY(b.la0, b.lo1);
          cx.setLineDash([6, 4]);
          cx.strokeStyle = "#000";
          cx.lineWidth = 1.6;
          cx.strokeRect(x0, y0, x1 - x0, y1 - y0);
          cx.setLineDash([]);
        }
      });
      cx.font = "500 12px 'IBM Plex Sans',sans-serif";
    }
    zones.current = zh;
    if (newPt) {
      const [x, y] = toXY(newPt[0], newPt[1]);
      cx.strokeStyle = "#fff";
      cx.lineWidth = 2;
      cx.beginPath();
      cx.arc(x, y, 9, 0, 7);
      cx.moveTo(x - 14, y);
      cx.lineTo(x + 14, y);
      cx.moveTo(x, y - 14);
      cx.lineTo(x, y + 14);
      cx.stroke();
    }
    const km = Math.round((VW.lo1 - VW.lo0) * 111.32 * Math.cos(((VW.la0 + VW.la1) / 2) * D2R));
    label(
      tr("Calibration globale (administrateur)") +
        (role === "admin" ? ` · K_TKE = ${fmt(KGLOB[0]!)}  K_CIS = ${fmt(KGLOB[1]!)}  K_conv = ${fmt(KGLOB[2]!)}` : ""),
      10,
      CH - 12,
    );
    const hkm = Math.round((VW.la1 - VW.la0) * 111.2),
      zmax = VW.la1 - VW.la0 <= ZMIN + 1e-6;
    label(tr(`${hkm} × ${km} km${zmax ? " · zoom maximal" : ""} · isolignes ${VW.la1 - VW.la0 <= FINE_VIEW_DEG ? "250" : "1000 / 2000"} m`), CW - (zmax ? 300 : 200), CH - 12);
  }, [VW, sample, contours, gmap, toXY, pub, sh, mine, MZH, newPt, role, lang]);

  /* ---------- animation ---------- */
  const last = NIGHTS[NIGHTS.length - 1]?.i1 ?? NH - 1;
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      setMI((m) => {
        const n = (m + 1) % (last + 1);
        setMNI(Math.max(0, NIGHTS.findIndex((q) => n >= q.i0 && n <= q.i1)));
        return n;
      });
    }, 900);
    return () => clearInterval(id);
  }, [playing, last, NIGHTS]);

  /* ---------- interactions ---------- */
  const setView = (v: Box, e: "dom" | "zoom" | "reg" | null = null) => {
    setVW(clampView(v));
    if (e) setExt(e);
    if (e !== "reg") setReg("");
  };
  const zoomAt = (x: number, y: number, f: number) => {
    const la = LA(y),
      lo = LO(x);
    setView({ la0: la - (la - VW.la0) * f, la1: la + (VW.la1 - la) * f, lo0: lo - (lo - VW.lo0) * f, lo1: lo + (VW.lo1 - lo) * f });
  };
  const canvasXY = (e: { clientX: number; clientY: number }) => {
    const r = canvas.current!.getBoundingClientRect();
    if (!r.width || !r.height) return [CW / 2, CH / 2] as const;
    return [((e.clientX - r.left) / r.width) * CW, ((e.clientY - r.top) / r.height) * CH] as const;
  };
  const onLand = (x: number, y: number) => !!cache.current?.mask[(Math.floor(y) * CW + Math.floor(x)) * 4 + 3];
  const zoneAt = (x: number, y: number): ZoneHit | undefined => {
    const zh = zones.current,
      e = zh.find(([a, b, w, h]) => x >= a && x <= a + w && y >= b && y <= b + h);
    if (e || !zh.length || !onLand(x, y)) return e;
    const la = LA(y),
      lo = LO(x),
      Zf = (i: number) => zh.find((q) => q[4] === i);
    if (inPoly(la, lo, FRA)) return Zf(0);
    if (inPoly(la, lo, CORSE) || inPoly(la, lo, SARD)) return Zf(6);
    let best: number | null = null,
      ba = 1e9;
    ZONES.forEach((z, i) => {
      const b = z[3];
      if (i === 0 || i === 6 || la < b.la0 || la > b.la1 || lo < b.lo0 || lo > b.lo1) return;
      const ar = (b.la1 - b.la0) * (b.lo1 - b.lo0);
      if (ar < ba) {
        ba = ar;
        best = i;
      }
    });
    return best == null ? undefined : Zf(best);
  };

  useEffect(() => {
    const cv = canvas.current;
    if (!cv) return;
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      const [x, y] = canvasXY(e);
      zoomAt(x, y, e.deltaY < 0 ? 0.8 : 1.25);
    };
    cv.addEventListener("wheel", wheel, { passive: false });
    return () => cv.removeEventListener("wheel", wheel);
  });

  const down = (e: RPointerEvent<HTMLCanvasElement>) => {
    const [x, y] = canvasXY(e);
    const snap = document.createElement("canvas");
    snap.width = CW;
    snap.height = CH;
    snap.getContext("2d")!.drawImage(canvas.current!, 0, 0);
    drag.current = { x, y, moved: false, snap };
    canvas.current!.setPointerCapture(e.pointerId);
  };
  const move = (e: RPointerEvent<HTMLCanvasElement>) => {
    const [x, y] = canvasXY(e);
    const d = drag.current;
    if (d) {
      const dx = x - d.x,
        dy = y - d.y;
      if (Math.hypot(dx, dy) > 4) d.moved = true;
      if (d.moved && !isFullView(VW)) {
        const c = canvas.current!.getContext("2d")!;
        c.fillStyle = "#1b2740";
        c.fillRect(0, 0, CW, CH);
        c.drawImage(d.snap, dx, dy);
      }
      return;
    }
    const zz = zoneAt(x, y),
      zi = zz ? zz[4] : -1;
    if (zi !== MZH) setMZH(zi);
    canvas.current!.style.cursor = zi >= 0 ? "pointer" : isFullView(VW) ? "default" : "grab";
    if (zz) return setTip(`${tr("Clique pour zoomer sur")} <b>${esc(tr(ZONES[zi]![0]))}</b>`);
    const la = LA(y),
      lo = LO(x);
    setTip(
      relReal || onLand(x, y)
        ? `<span class="mono">${la.toFixed(3)} N · ${lo.toFixed(3)} E</span>` +
            (relReal && land && land.at(la, lo) >= 0.5 ? ` · ${tr("relief AROME")} <span class="mono">${Math.round(relReal(la, lo))} m</span>` : "")
        : `<span class="mono">${la.toFixed(2)} N · ${lo.toFixed(2)} E</span> · ${tr("hors de la zone du calcul global")}`,
    );
  };
  const up = (e: RPointerEvent<HTMLCanvasElement>) => {
    const d = drag.current;
    if (!d) return;
    drag.current = null;
    const [x, y] = canvasXY(e);
    if (d.moved) {
      const dla = ((y - d.y) / CH) * (VW.la1 - VW.la0),
        dlo = ((x - d.x) / CW) * (VW.lo1 - VW.lo0);
      return setView({ la0: VW.la0 + dla, la1: VW.la1 + dla, lo0: VW.lo0 - dlo, lo1: VW.lo1 - dlo });
    }
    const zz = zoneAt(x, y);
    if (zz) {
      setMZH(-1);
      setReg(String(zz[4]));
      return setView(fitBox(ZONES[zz[4]]![3]), "reg");
    }
    const pt: [number, number] = [LA(y), LO(x)];
    setNewPt(pt);
    setShowNew(true);
    setNlMsg(null);
    setNl((s) => ({ ...s, lat: pt[0].toFixed(4), lon: pt[1].toFixed(4) }));
  };

  const fromInputs = (lat: string, lon: string) => {
    setNl((s) => ({ ...s, lat, lon }));
    const la = parseCoord(lat, true),
      lo = parseCoord(lon, false);
    if (la == null || lo == null) return setNewPt(null);
    setNewPt([la, lo]);
    if (inDomain(la, lo) && (la < VW.la0 || la > VW.la1 || lo < VW.lo0 || lo > VW.lo1)) {
      const hl = (VW.la1 - VW.la0) / 2,
        ho = (VW.lo1 - VW.lo0) / 2;
      setView({ la0: la - hl, la1: la + hl, lo0: lo - ho, lo1: lo + ho });
    }
  };
  const create = () => {
    const n = nl.name.trim();
    if (!newPt) return setNlMsg({ ok: false, t: tr("Clique sur la carte ou saisis des coordonnées GPS valides.") });
    if (!n) return setNlMsg({ ok: false, t: tr("Donne un nom au lieu.") });
    if (!user) return setNlMsg({ ok: false, t: tr("Connecte-toi (onglet Compte) pour enregistrer tes lieux.") });
    if (!inDomain(newPt[0], newPt[1])) return setNlMsg({ ok: false, t: tr("Hors du domaine AROME : pas encore possible.") });
    if (role !== "admin" && mine.length >= MAX_PLACES) return setNlMsg({ ok: false, t: tr(`${MAX_PLACES} lieux au maximum par compte.`) });
    createPlace.mutate(
      { name: n, lat: newPt[0], lon: newPt[1], shared: nl.share },
      {
        onSuccess: (s) => {
          setState(selectPlace(siteToPlace(s)));
          setNlMsg({
            ok: true,
            t: tr(`« ${n} » créé${nl.share ? ", partagé (position approchée)" : ", privé"}. Prévisions dès le prochain run AROME.`),
          });
        },
        onError: (e) => setNlMsg({ ok: false, t: e.message }),
      },
    );
  };

  const fd = frameT(MI),
    lead = Math.round((fd.getTime() - RUN0) / 3600000);
  // Hour range really averaged (the run may stop before the end of the night).
  const meanRange = (() => {
    const h = real?.hours ?? [];
    if (!real) return "20h–04h TU";
    if (!h.length) return "aucune heure couverte par le run";
    const txt = `${pad2(h[0]!)}h–${pad2(h[h.length - 1]!)}h TU`;
    return h.length < real.expected ? `${txt}, run incomplet : ${h.length} h sur ${real.expected}` : txt;
  })();
  const hourLabel =
    mode === "m"
      ? tr(`moyenne nuit du ${night.lab} (${meanRange})`)
      : tr(`${JS[fd.getUTCDay()]} ${pad2(fd.getUTCDate())}/${pad2(fd.getUTCMonth() + 1)} · ${pad2(fd.getUTCHours())}h TU · +${lead} h`) +
        (real && !real.hours.length ? tr(" · pas de prévision à cette heure") : "");
  const runL = runLabel(RUN0),
    endL = new Date(RUN0 + LEADMAX * 3600000);
  const nextRun = pad2(new Date(RUN0 + 6 * 3600000).getUTCHours()) + "Z";
  const nlInDomain = newPt ? inDomain(newPt[0], newPt[1]) : false;

  return (
    <section>
      <h1>{tr("Carte globale du seeing")}</h1>
      <p className="lead">
        {tr(
          "Seeing V2bd sur tout le domaine AROME (France, îles Britanniques, péninsule Ibérique, Benelux, Allemagne, Alpes, Italie), recalculé toutes les 6 heures, à chaque run principal d'AROME (00Z, 06Z, 12Z, 18Z). Sur la vue du domaine, clique n'importe où dans une zone (France, Royaume-Uni…) pour zoomer dessus ; une fois zoomé, survole la carte pour lire une maille et clique pour créer un lieu.",
        )}
      </p>
      <div className="grid2">
        <div className="panel">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              <Seg
                label={tr("Étendue")}
                value={ext}
                onChange={(v) => {
                  if (v === "dom") setView(fitBox(DOM), "dom");
                  else if (v === "zoom")
                    setView({ la0: place.lat - 0.85, la1: place.lat + 0.85, lo0: place.lon - 1.27, lo1: place.lon + 1.27 }, "zoom");
                }}
                options={[
                  ["dom", tr("Domaine AROME")],
                  ["zoom", tr("Mon lieu")],
                ]}
              />
              <select
                aria-label={tr("Zone")}
                value={reg}
                onChange={(e) => {
                  const z = ZONES[+e.target.value];
                  setReg(e.target.value);
                  if (e.target.value !== "" && z) setView(fitBox(z[3]), "reg");
                }}
              >
                <option value="">{tr("Zone…")}</option>
                {ZONES.map((z, i) => (
                  <option key={z[0]} value={i}>
                    {tr(z[0])}
                  </option>
                ))}
              </select>
              <button aria-label={tr("Zoomer")} onClick={() => zoomAt(CW / 2, CH / 2, 0.67)}>
                +
              </button>
              <button aria-label={tr("Dézoomer")} onClick={() => zoomAt(CW / 2, CH / 2, 1.5)}>
                −
              </button>
              <button title={tr("Télécharger la carte affichée (PNG)")} onClick={() => canvas.current && canvasToPng(canvas.current, `carte_seeing_${fileStamp()}.png`)}>
                ⤓ PNG
              </button>
              <button title={tr("Télécharger l'animation des heures de la nuit choisie (GIF)")} disabled={gifBusy} onClick={() => void exportGif()}>
                {gifBusy ? tr("GIF…") : "⤓ GIF"}
              </button>
            </div>
          </div>
          <canvas
            ref={canvas}
            width={CW}
            height={CH}
            style={{ cursor: "grab", touchAction: "none" }}
            aria-label={tr("Carte globale du seeing de la nuit, déplaçable et zoomable")}
            onPointerDown={down}
            onPointerMove={move}
            onPointerUp={up}
            onPointerCancel={() => (drag.current = null)}
            onPointerLeave={() => setTip(null)}
          />
          <ColorBar left={tr("bon")} right={tr("mauvais")} gradient={turboGradient()} />
          <p className="small muted" style={{ margin: "4px 0 0", textAlign: "center" }}>
            <i>{tr("Les valeurs absolues seront bientôt disponibles, après la calibration globale.")}</i>
          </p>
          {tip ? (
            <p className="tip" dangerouslySetInnerHTML={{ __html: tip }} />
          ) : (
            <p className="tip">
              {tr(
                "Molette ou boutons + et − pour zoomer, glisser pour se déplacer, clic pour créer un lieu. Le zoom affiche la carte déjà calculée, sans calcul supplémentaire, jusqu'à 100 km de côté.",
              )}
            </p>
          )}
        </div>
        <div className="stack">
          <div className="panel">
            <h2>{tr("Réglage")}</h2>
            <div style={{ marginBottom: 10 }}>
              <span className="small muted">
                run <span className="mono">{runL}</span> · {tr("prévision jusqu'à")} <span className="mono">+{LEADMAX} h</span> (
                {`${pad2(endL.getUTCDate())}/${pad2(endL.getUTCMonth() + 1)} ${pad2(endL.getUTCHours())}h`} {tr("TU")}) ·{" "}
                {tr("nuits seulement (19h–05h TU, moyenne 20h–04h)")}
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
              <span className="small muted" style={{ minWidth: 52 }}>
                {tr("Nuit")}
              </span>
              <Seg
                label={tr("Nuit")}
                value={MNI}
                onChange={(k) => {
                  setMNI(k);
                  if (mode === "h") setMI(NIGHTS[k]!.i0);
                }}
                options={NIGHTS.map((n, k) => [k, tr(`Nuit du ${n.lab}`)])}
              />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
              <span className="small muted" style={{ minWidth: 52 }}>
                {tr("Affichage")}
              </span>
              <Seg
                label={tr("Affichage du temps")}
                value={mode}
                onChange={(m) => {
                  if (m === "m") setPlaying(false);
                  else if (MI < night.i0 || MI > night.i1) setMI(night.i0);
                  setMode(m);
                }}
                options={[
                  ["m", tr("Moyenne de la nuit (20h–04h TU)")],
                  ["h", tr("Heure par heure")],
                ]}
              />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span className="small muted" style={{ minWidth: 52 }}>
                {tr("Heure")}
              </span>
              <button
                aria-label={tr("Animer la carte sur les heures de nuit")}
                onClick={() => {
                  if (!playing) setMode("h");
                  setPlaying(!playing);
                }}
              >
                {playing ? "❚❚" : "▶"}
              </button>
              <input
                type="range"
                min={0}
                max={last}
                step={1}
                value={MI}
                style={{ flex: 1, minWidth: 120 }}
                aria-label={tr("Date et heure de la carte")}
                onChange={(e) => {
                  const v = +e.target.value;
                  setMI(v);
                  setMNI(Math.max(0, NIGHTS.findIndex((n) => v >= n.i0 && v <= n.i1)));
                  setMode("h");
                }}
              />
              <span className="mono" style={{ flexBasis: "100%", textAlign: "right", fontWeight: 500 }}>
                {hourLabel}
              </span>
            </div>
          </div>
          <div className="panel">
            <h2>{tr("Ce que montre la carte")}</h2>
            <div className="legend" style={{ flexDirection: "column", gap: 6 }}>
              <span>
                <PinIcon kind="pub" />
                {tr("Seeing monitor public (position exacte)")}
              </span>
              <span>
                <PinIcon kind="sh" />
                {tr("Lieu partagé (")}
                <b>{tr("position floutée à 5–11 km")}</b>)
              </span>
              <span>
                <PinIcon kind="mine" />
                {tr("Mes lieux")}
              </span>
              <span>
                <span className="sw" style={{ width: 14, borderTop: "1px solid rgba(0,0,0,.6)" }} />
                {tr("Relief AROME : trait de côte, isolignes 1000 et 2000 m (tous les 250 m en zoom)")}
              </span>
              <span>
                <span className="sw" style={{ width: 14, height: 12, background: "rgb(60,66,80)" }} />
                {tr("Pas de prévision à cette heure (run incomplet)")}
              </span>
            </div>
          </div>
          <div className="panel">
            <h2>{tr("Cette nuit")}</h2>
            <p className="small" style={{ margin: "0 0 8px" }}>
              {tr("Carte du run")} <b className="mono">{runL}</b> {tr("· prochaine mise à jour avec le run")} <b className="mono">{nextRun}</b>
              {tr(", dans 6 h")}{" "}
              <span className="muted">
                {tr("(résultats disponibles environ")} <span className="mono">1 h 15</span> {tr("après l'arrivée du run)")}
              </span>
            </p>
            <p className="note">
              {tr(
                "Calcul global sur tout le domaine AROME, terre et mer, toutes les 6 heures, à chaque run principal : 00Z, 06Z, 12Z, 18Z ; les runs secondaires ne sont pas utilisés. La carte est calibrée une fois pour toutes par l'administrateur : elle ne change pas avec la calibration des lieux. Hors du domaine AROME, un lieu passe par la file d'attente.",
              )}
            </p>
          </div>
          {showNew && (
            <div className="panel">
              <h2>{tr("Nouveau lieu")}</h2>
              <p className="small muted" style={{ margin: "0 0 8px" }}>
                {tr(
                  "Clique sur la carte ou saisis les coordonnées GPS (degrés décimaux : 44.1234 et 5.6789, ou degrés minutes secondes : 44°07'24\" N et 5°40'44\" E).",
                )}
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 6 }}>
                <div>
                  <label className="small muted" htmlFor="nllat">
                    {tr("Latitude")}
                  </label>
                  <input
                    id="nllat"
                    className="mono"
                    style={{ width: "100%", marginTop: 2 }}
                    placeholder={tr("44.1234 ou 44°07'24\" N")}
                    autoComplete="off"
                    value={nl.lat}
                    onChange={(e) => fromInputs(e.target.value, nl.lon)}
                  />
                </div>
                <div>
                  <label className="small muted" htmlFor="nllon">
                    {tr("Longitude")}
                  </label>
                  <input
                    id="nllon"
                    className="mono"
                    style={{ width: "100%", marginTop: 2 }}
                    placeholder={tr("5.6789 ou 5°40'44\" E")}
                    autoComplete="off"
                    value={nl.lon}
                    onChange={(e) => fromInputs(nl.lat, e.target.value)}
                  />
                </div>
              </div>
              <p className="small muted" style={{ margin: "0 0 8px" }}>
                {newPt
                  ? `${newPt[0].toFixed(4)} N · ${newPt[1].toFixed(4)} E · ` +
                    tr(
                      nlInDomain
                        ? "dans le domaine AROME : prévision dès le prochain run principal"
                        : "hors du domaine AROME : prévision via la file d'attente",
                    )
                  : nl.lat || nl.lon
                    ? tr("Coordonnées non reconnues.")
                    : ""}
              </p>
              <label className="small muted" htmlFor="nlname">
                {tr("Nom")}
              </label>
              <input id="nlname" style={{ width: "100%", margin: "2px 0 8px" }} value={nl.name} onChange={(e) => setNl({ ...nl, name: e.target.value })} />
              <label className="small" style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 8 }}>
                <input type="checkbox" checked={nl.share} onChange={(e) => setNl({ ...nl, share: e.target.checked })} />{" "}
                {tr("Partager avec la communauté")}
              </label>
              <p style={{ margin: "-4px 0 10px", fontSize: 15, fontWeight: 700, color: "#f2c14e" }}>
                <span
                  style={{
                    display: "inline-flex",
                    width: 20,
                    height: 20,
                    borderRadius: "50%",
                    background: "#f2c14e",
                    color: "#000",
                    justifyContent: "center",
                    alignItems: "center",
                    marginRight: 6,
                    fontWeight: 800,
                  }}
                >
                  !
                </span>
                {tr("Position floutée à 5–11 km")}
              </p>
              <button className="primary" onClick={create}>
                {tr("Créer le lieu")}
              </button>
              <p className={nlMsg?.ok ? "okmsg" : "err"}>{nlMsg?.t ?? ""}</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

