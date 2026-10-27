/**
 * Global seeing map (canvas): the real maps of the latest run (GET /api/map, V2bd over the whole AROME
 * grid, night hours 19h-05h UTC, mean of the night 20h-04h), or a fictitious field while there is none. Public sites come from
 * the API, personal places are mock.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as RPointerEvent } from "react";
import { useLocation } from "react-router-dom";

import { ColorBar, Seg } from "../components/ui";
import { useUser } from "../data/auth";
import { MAX_PLACES, selectPlace, siteToPlace, useCurrentPlace, usePlaceActions, usePlaces } from "../data/places";
import { tr } from "../i18n";
import { CORSE, DOM, FRA, inDomain, inPoly, LANDS, parseCoord, relief, SARD, SHAREDV, ZONES, type Box, type Poly } from "../lib/geo";
import { useGlobalMap, useLatestRunTime } from "../lib/hooks";
import type { MapGrid } from "../api";
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
  inMean = (i: number) => MAPH[i] !== 19 && MAPH[i] !== 5,
  TREND = [1.2, 1.14, 1.06, 1.0, 0.95, 0.92, 0.93, 0.97, 1.01, 1.07, 1.12, 1.24, 1.18, 1.1, 1.03, 0.98, 0.94, 0.95, 0.99, 1.04, 1.1, 1.16];
const LEADMAX = 51;
const KGLOB = [2, 57, 0.1];
const JS = ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."];
const LUT = [...Array(256)].map((_, k) => turbo(k / 255));
const OTHERS: Poly[] = LANDS.filter((p) => p !== CORSE);

const baseSee = (la: number, lo: number, r: number) =>
  Math.max(
    0.5,
    4.3 -
      3.0 * Math.min(1, r / 1500) +
      (0.25 * (la - 46)) / 5 +
      0.6 * Math.sin(la * 1.7 + lo * 0.9) * Math.cos(lo * 1.3 - la * 0.5) +
      0.3 * Math.sin(la * 7.1 + 1) * Math.cos(lo * 6.3),
  );
const hourFac = (i: number, la: number, lo: number) =>
  TREND[i]! * (1 + 0.2 * Math.sin(la * 1.3 + i * 0.55) * Math.cos(lo * 0.9 - i * 0.4));

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
/** Clamp zoom and centre to the domain. */
function clampView(v: Box): Box {
  const DV = fitBox(DOM),
    sl = v.la1 - v.la0,
    so = v.lo1 - v.lo0,
    sl2 = Math.min(DV.la1 - DV.la0, Math.max(ZMIN, sl)),
    f = sl2 / sl,
    cla = (v.la0 + v.la1) / 2,
    clo = (v.lo0 + v.lo1) / 2;
  const nl = Math.min(DOM.la1, Math.max(DOM.la0, cla)),
    no = Math.min(DOM.lo1, Math.max(DOM.lo0, clo));
  return { la0: nl - sl2 / 2, la1: nl + sl2 / 2, lo0: no - (so * f) / 2, lo1: no + (so * f) / 2 };
}
const isoStep = (V: Box) => {
  const s = V.la1 - V.la0;
  return s > 4 ? 1000 : s > 1.2 ? 500 : 250;
};

interface Cache {
  key: string;
  base: Float32Array;
  las: Float32Array;
  los: Float32Array;
  sea: Uint8Array;
  iso: Uint8Array;
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
  const iso0 = isoStep(V),
    n = CW * CH,
    mask = landMask(V),
    base = new Float32Array(n),
    las = new Float32Array(n),
    los = new Float32Array(n),
    sea = new Uint8Array(n),
    iso = new Uint8Array(n),
    rel = new Float32Array(n);
  for (let y = 0; y < CH; y++)
    for (let x = 0; x < CW; x++) {
      const j = y * CW + x,
        la = V.la1 - (y / CH) * (V.la1 - V.la0),
        lo = V.lo0 + (x / CW) * (V.lo1 - V.lo0),
        r = relief(la, lo);
      rel[j] = r;
      base[j] = baseSee(la, lo, r);
      las[j] = la;
      los[j] = lo;
      sea[j] = mask[j * 4 + 3] ? 0 : 1;
    }
  for (let y = 1; y < CH; y++)
    for (let x = 1; x < CW; x++) {
      const j = y * CW + x;
      if (sea[j]) continue;
      const a = Math.floor(rel[j]! / iso0);
      if (a !== Math.floor(rel[j - 1]! / iso0) || a !== Math.floor(rel[j - CW]! / iso0)) iso[j] = 1;
    }
  return { key, base, las, los, sea, iso, mask };
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
  const { pub, mine } = usePlaces();
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
  const [newPt, setNewPt] = useState<[number, number] | null>(null);
  const loc = useLocation();
  const [showNew, setShowNew] = useState(() => !!(loc.state as { newPlace?: boolean } | null)?.newPlace);
  const [nl, setNl] = useState({ lat: "", lon: "", name: "Nouveau lieu", share: false });
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

  const frameFac = useCallback(
    (la: number, lo: number) => {
      if (mode === "m") {
        let s = 0,
          n = 0;
        for (let i = night.i0; i <= night.i1; i++)
          if (inMean(i)) {
            s += hourFac(i, la, lo);
            n++;
          }
        return s / n;
      }
      return hourFac(MI, la, lo);
    },
    [mode, MI, night.i0, night.i1],
  );

  /* Real map: the frame of the chosen hour, or the mean seeing of the night's frames. */
  const sample = useMemo(() => {
    if (!gmap) return null;
    const idx = mode === "m" ? [...Array(night.i1 - night.i0 + 1)].map((_, k) => night.i0 + k).filter(inMean) : [MI];
    const arrs = idx
      .map((i) => gmap.frames.get(Math.round((frameT(i).getTime() - RUN0) / 3600000)))
      .filter((a): a is Float32Array => !!a);
    if (!arrs.length) return null;
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
    return sampler(gmap.meta.grid, mean);
  }, [gmap, mode, MI, night.i0, night.i1, frameT, RUN0]);

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
      const p = j * 4;
      if (C.sea[j]) {
        D[p] = 27;
        D[p + 1] = 39;
        D[p + 2] = 64;
        D[p + 3] = 255;
        continue;
      }
      // Fixed colour stretch (0–6") so that maps stay comparable from one run to the next.
      const s = sample ? sample(C.las[j]!, C.los[j]!) : C.base[j]! * frameFac(C.las[j]!, C.los[j]!);
      if (isNaN(s)) {
        D[p] = 60;
        D[p + 1] = 66;
        D[p + 2] = 80;
        D[p + 3] = 255;
        continue;
      }
      const c = LUT[Math.min(255, Math.round((s / 6) * 255))]!,
        d = C.iso[j] ? 0.45 : 1;
      D[p] = c[0] * d;
      D[p + 1] = c[1] * d;
      D[p + 2] = c[2] * d;
      D[p + 3] = 255;
    }
    cx.putImageData(img, 0, 0);
    const big = VW.la1 - VW.la0 < 3.2;
    const poly = (pl: Poly) => {
      cx.beginPath();
      pl.forEach((q, k) => {
        const [x, y] = toXY(...q);
        if (k) cx.lineTo(x, y);
        else cx.moveTo(x, y);
      });
      cx.closePath();
      cx.stroke();
    };
    cx.lineWidth = 1;
    cx.strokeStyle = "rgba(255,255,255,.55)";
    OTHERS.forEach(poly);
    cx.strokeStyle = "rgba(255,255,255,.8)";
    [FRA, CORSE].forEach(poly);
    SHAREDV.forEach(([la, lo]) => {
      const [x, y] = toXY(la, lo),
        r = big ? 7 : 5;
      cx.beginPath();
      cx.moveTo(x, y - r);
      cx.lineTo(x + r, y);
      cx.lineTo(x, y + r);
      cx.lineTo(x - r, y);
      cx.closePath();
      cx.fillStyle = "#9cc7ff";
      cx.fill();
      cx.strokeStyle = "#000";
      cx.lineWidth = 1.4;
      cx.stroke();
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
      cx.fillStyle = "#fff";
      cx.strokeStyle = "#000";
      cx.lineWidth = 2;
      cx.beginPath();
      cx.arc(x, y, big ? 6 : 4, 0, 7);
      cx.fill();
      cx.stroke();
      if (big) label(s.nom, x + 9, y + 4);
    });
    const star = (x: number, y: number, r: number) => {
      cx.beginPath();
      for (let k = 0; k < 10; k++) {
        const a = -Math.PI / 2 + (k * Math.PI) / 5,
          rr = k % 2 ? r * 0.45 : r;
        cx.lineTo(x + rr * Math.cos(a), y + rr * Math.sin(a));
      }
      cx.closePath();
      cx.fillStyle = "#f2a23a";
      cx.fill();
      cx.strokeStyle = "#000";
      cx.lineWidth = 1.2;
      cx.stroke();
    };
    mine.forEach((p) => {
      const [x, y] = toXY(p.lat, p.lon);
      star(x, y, big ? 10 : 7);
      if (big) label(tr(p.nom), x + 12, y + 4);
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
          cx.strokeStyle = "#f2c14e";
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
    label(tr(`${hkm} × ${km} km${zmax ? " · zoom maximal" : ""} · isolignes ${isoStep(VW)} m`), CW - (zmax ? 300 : 200), CH - 12);
  }, [VW, frameFac, sample, toXY, pub, mine, MZH, newPt, role, lang]);

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
      if (d.moved) {
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
    canvas.current!.style.cursor = zi >= 0 ? "pointer" : "grab";
    if (zz) return setTip(`${tr("Clique pour zoomer sur")} <b>${esc(tr(ZONES[zi]![0]))}</b>`);
    const la = LA(y),
      lo = LO(x);
    setTip(
      onLand(x, y)
        ? `<span class="mono">${la.toFixed(3)} N · ${lo.toFixed(3)} E</span> · ${tr("relief AROME")} <span class="mono">${Math.round(relief(la, lo))} m</span>`
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
  const hourLabel =
    mode === "m"
      ? tr(`moyenne nuit du ${night.lab} (20h–04h TU)`)
      : tr(`${JS[fd.getUTCDay()]} ${pad2(fd.getUTCDate())}/${pad2(fd.getUTCMonth() + 1)} · ${pad2(fd.getUTCHours())}h TU · +${lead} h`);
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
            </div>
          </div>
          <div style={{ border: "1px solid #3a4a72", borderRadius: 12, padding: "10px 12px", marginBottom: 10, background: "var(--panel2)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
              <b>{tr("Réglage")}</b>
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
              <span className="mono" style={{ minWidth: 210, textAlign: "right", fontWeight: 500 }}>
                {hourLabel}
              </span>
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
            <h2>{tr("Ce que montre la carte")}</h2>
            <div className="legend" style={{ flexDirection: "column", gap: 6 }}>
              <span>
                <span className="sw" style={{ width: 12, height: 12, borderRadius: "50%", background: "#fff", border: "2px solid #000" }} />
                {tr("Seeing monitor public (position exacte)")}
              </span>
              <span>
                <span className="sw" style={{ width: 12, height: 12, background: "#9cc7ff", clipPath: "polygon(50% 0,100% 50%,50% 100%,0 50%)" }} />
                {tr("Lieu partagé (")}
                <b>{tr("position floutée à 5–11 km")}</b>)
              </span>
              <span>
                <span
                  className="sw"
                  style={{
                    width: 12,
                    height: 12,
                    background: "#f2a23a",
                    clipPath: "polygon(50% 0,61% 35%,98% 35%,68% 57%,79% 91%,50% 70%,21% 91%,32% 57%,2% 35%,39% 35%)",
                  }}
                />
                {tr("Mes lieux")}
              </span>
              <span>
                <span className="sw" style={{ width: 14, borderTop: "1px solid rgba(0,0,0,.6)" }} />
                {tr("Relief AROME, isolignes tous les 1000 m (500 m en zoom)")}
              </span>
              <span>
                <span className="sw" style={{ width: 14, height: 12, background: "#1b2740" }} />
                {tr("Mer, hors bande côtière : non calculée")}
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
                "Calcul global sur tout le domaine AROME (terres et bande côtière de 106 km) toutes les 6 heures, à chaque run principal : 00Z, 06Z, 12Z, 18Z ; les runs secondaires ne sont pas utilisés. La carte est calibrée une fois pour toutes par l'administrateur : elle ne change pas avec la calibration des lieux. Hors du domaine, ou en mer au-delà de la bande côtière, un lieu passe par la file d'attente.",
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

