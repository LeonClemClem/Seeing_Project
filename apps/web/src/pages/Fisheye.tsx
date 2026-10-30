/**
 * Seeing fisheye for the selected place, 19h–05h UTC, from the global maps of the latest run (fictitious
 * field while there is none); stars, catalogue objects, Sun, Moon and planets at their real positions.
 */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import { api, type Fisheye as FisheyeData } from "../api";

import { Chip, ColorBar, Seg } from "../components/ui";
import { useCurrentPlace } from "../data/places";
import { tr } from "../i18n";
import { useLatestRunTime } from "../lib/hooks";
import {
  altaz,
  CAT,
  LN,
  moonAltAz,
  moonPhase,
  PL,
  planetRaDec,
  ST,
  sunAltAz,
  type CatObj,
} from "../lib/sky";
import { D2R, pad2, runLabel, turbo, turboGradient } from "../lib/util";
import { KDEF, REF } from "../mock/engine";
import { useUi, type K3 } from "../store";

/** Compass point of an azimuth (8 directions, French). */
const dir8 = (az: number) => ["N", "NE", "E", "SE", "S", "SO", "O", "NO"][Math.round(az / 45) % 8]!;

const FN = 520,
  FR = 232,
  FC = FN / 2,
  ELMIN = 5;
/* Only real elements: horizon = AROME orography of the run (always drawn); clouds = AROME low / medium / high cover. */
const OPT0 = {
  cons: ["Constellations", true],
  sol: ["Soleil et Lune", true],
  trk: ["Course des objets", true],
  nua: ["Nuages", false],
} as const;
type OptKey = keyof typeof OPT0;

/** Small symbols of the display options, drawn like the fisheye (16 x 16 SVG). */
const OPT_ICON: Record<OptKey, string> = {
  // three stars joined by lines
  cons:
    '<path d="M2.5 11.5 L7 4.5 L13 7.5" fill="none" stroke="#e6ebf6" stroke-width="1" opacity=".75"/>' +
    '<circle cx="2.5" cy="11.5" r="1.6" fill="#fff"/><circle cx="7" cy="4.5" r="1.9" fill="#fff"/><circle cx="13" cy="7.5" r="1.5" fill="#fff"/>',
  // Sun and crescent Moon
  sol:
    '<circle cx="5.5" cy="6" r="3" fill="#f2c14e"/>' +
    '<path d="M5.5 1.2v1.2M5.5 9.6v1.2M0.7 6h1.2M9.1 6h1.2M2.1 2.6l.8.8M8.1 8.6l.8.8M2.1 9.4l.8-.8M8.1 3.4l.8-.8" stroke="#f2c14e" stroke-width="1"/>' +
    '<path d="M13.6 9.2a3.6 3.6 0 1 1-3.6-3.9 2.9 2.9 0 0 0 3.6 3.9z" fill="#c9d3e6"/>',
  // dotted arc of a track with the object on it
  trk: '<path d="M1.5 13 Q8 0 14.5 13" fill="none" stroke="#9cc7ff" stroke-width="1.3" stroke-dasharray="1.6 1.8"/><circle cx="8" cy="6.6" r="2" fill="#9cc7ff"/>',
  // cloud
  nua: '<path d="M4.3 12.5h7.6a2.7 2.7 0 0 0 .3-5.4 3.7 3.7 0 0 0-7.1-.9 2.9 2.9 0 0 0-.8 6.3z" fill="#c4cad6" stroke="#8a93a6" stroke-width=".8"/>',
};

const LAMBDA = 500e-9;
const seeOfJ = (J: number) => (J > 0 ? 0.98 * LAMBDA * Math.pow(0.423 * (2 * Math.PI / LAMBDA) ** 2 * J, 0.6) * 206265 : NaN);

/** Bilinear sampler in elevation / azimuth of the [elevation][azimuth] grids of a fisheye response. */
function dirSampler(d: FisheyeData, alt: number, az: number) {
  const e = d.elevations,
    a = d.azimuths,
    de = e[1]! - e[0]!,
    da = a[1]! - a[0]!;
  const el = Math.max(e[0]!, Math.min(90, alt)),
    i = Math.min(e.length - 2, Math.floor((el - e[0]!) / de)),
    fi = (el - e[i]!) / de,
    x = (((az % 360) + 360) % 360) / da,
    j = Math.floor(x) % a.length,
    j1 = (j + 1) % a.length,
    fj = x - Math.floor(x);
  const g = (m: (number | null)[][], r: number, c: number) => m[r]?.[c] ?? NaN;
  return (m: (number | null)[][]) =>
    (1 - fi) * ((1 - fj) * g(m, i, j) + fj * g(m, i, j1)) + fi * ((1 - fj) * g(m, i + 1, j) + fj * g(m, i + 1, j1));
}

/** Seeing of one direction from the real fisheye frame (bilinear in elevation / azimuth), rescaled to K. */
function realSee(d: FisheyeData, fr: FisheyeData["frames"][number], K: K3, alt: number, az: number): number {
  const e = d.elevations,
    bil = dirSampler(d, alt, az);
  // below the lowest computed elevation: same direction, longer path (1 / sin)
  const low = alt < e[0]! ? Math.sin(e[0]! * D2R) / Math.sin(Math.max(alt, 2) * D2R) : 1;
  return seeOfJ(((K[0] / d.k[0]!) * bil(fr.j_low) + (K[1] / d.k[1]!) * bil(fr.j_high)) * low);
}

const fxy = (alt: number, az: number) => {
  const r = ((90 - alt) / 90) * FR;
  return [FC - r * Math.sin(az * D2R), FC - r * Math.cos(az * D2R)] as const;
};

export default function Fisheye() {
  const place = useCurrentPlace();
  const lang = useUi((s) => s.lang);
  const { runTime } = useLatestRunTime();
  const runMs = runTime ? Date.parse(runTime) : REF + 12 * 3600000;
  const T0 = useMemo(() => {
    const r = new Date(runMs);
    return Date.UTC(r.getUTCFullYear(), r.getUTCMonth(), r.getUTCDate(), 19);
  }, [runMs]);
  const nights = useMemo(
    () =>
      [0, 1].map((k) => {
        const a = new Date(T0 + k * 86400000),
          b = new Date(T0 + (k + 1) * 86400000);
        return `${pad2(a.getUTCDate())} au ${pad2(b.getUTCDate())}/${pad2(b.getUTCMonth() + 1)}`;
      }),
    [T0],
  );

  const [FNI, setFNI] = useState(0);
  const [fcur, setFcur] = useState(3);
  const [playing, setPlaying] = useState(false);
  const [cal, setCal] = useState<"mine" | "def">("mine");
  const [hov, setHov] = useState<{ x: number; y: number; alt: number; az: number; s: number; c: number } | null>(null);
  const [opt, setOpt] = useState<Record<OptKey, boolean>>({ cons: true, sol: true, trk: true, nua: false });
  const [plOn, setPlOn] = useState(() => new Set(["Jupiter", "Saturne", "Mars"]));
  const [tgts, setTgts] = useState<CatObj[]>(() => [CAT[0]!, CAT[9]!]);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("all");
  const cv = useRef<HTMLCanvasElement>(null);

  const { lat, lon } = place;
  const tOf = (i: number) => T0 + (FNI * 24 + i) * 3600000;
  // Real fisheye from the global maps of the latest run (any point of the AROME domain).
  // the place's altitude (when known) is the observer's height for the horizon, else the AROME ground
  const fq = useQuery({
    queryKey: ["fisheye", lat.toFixed(4), lon.toFixed(4), place.alt ?? "", runTime ?? ""],
    queryFn: () => api.fisheye(lat, lon, place.alt),
    retry: false,
    staleTime: 30 * 60 * 1000,
  });
  const fe = fq.data;
  const frameAt = (i: number) => {
    if (!fe) return undefined;
    const lead = Math.round((tOf(i) - Date.parse(fe.run_time)) / 3600000);
    return fe.frames.find((f) => f.lead_hour === lead);
  };
  const K: K3 = cal === "mine" ? place.K : fe ? [fe.k[0]!, fe.k[1]!, fe.k[2]!] : KDEF;
  /** Elevation of the relief [deg] in a direction (AROME orography of the run, every 2 degrees, interpolated). */
  const horizonAt = (az: number) => {
    const h = fe?.horizon;
    if (!h || !h.length) return 0;
    const x = ((((az % 360) + 360) % 360) / 360) * h.length,
      i = Math.floor(x) % h.length,
      f = x - Math.floor(x);
    return h[i]! * (1 - f) + h[(i + 1) % h.length]! * f;
  };
  /** Sky seen: above the relief and above ELMIN. */
  const vis = (alt: number, az: number) => alt >= Math.max(ELMIN, horizonAt(az));
  const seeSky = (i: number, alt: number, az: number) => {
    const fr = frameAt(i);
    // no fisheye data (yet) or hour not covered by the run: no value, never a fictitious field
    return fe && fr ? realSee(fe, fr, K, alt, az) : NaN;
  };
  /** Cloud cover 0-1 seen in a direction (NaN: run stored without clouds). */
  const cloudSky = (i: number, alt: number, az: number) => {
    const fr = frameAt(i);
    return fe && fr?.cloud ? dirSampler(fe, alt, az)(fr.cloud) : NaN;
  };
  const hasClouds = !!fe?.frames.some((f) => f.cloud);
  const best = (o: CatObj) => {
    let b: [number, number] | null = null;
    for (let k = 0; k <= 10; k++) {
      const [a, z] = altaz(o[3], o[4], tOf(k), lat, lon);
      if (!vis(a, z)) continue;
      const s = seeSky(k, a, z);
      if (!b || s < b[0]) b = [s, k];
    }
    return b;
  };

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setFcur((c) => (c + 1) % 11), 900);
    return () => clearInterval(id);
  }, [playing]);

  const t = tOf(fcur);
  const sun = sunAltAz(t, lat, lon),
    moon = moonAltAz(t, lat, lon),
    phase = moonPhase(t);

  useEffect(() => {
    const c = cv.current?.getContext("2d");
    if (!c) return;
    const img = c.createImageData(FN, FN),
      D = img.data;
    for (let y = 0; y < FN; y++)
      for (let x = 0; x < FN; x++) {
        const dx = x - FC,
          dy = FC - y,
          r = Math.hypot(dx, dy),
          p = (y * FN + x) * 4;
        if (r > FR) {
          D[p + 3] = 0;
          continue;
        }
        const alt = 90 - (r / FR) * 90,
          az = (Math.atan2(-dx, dy) / D2R + 360) % 360;
        const s = vis(alt, az) ? seeSky(fcur, alt, az) : NaN;
        // same colours as the map: turbo, 0-10" with a fixed square-root stretch
        // relief in dark brown; below ELMIN (or no value) grey
        let col: number[] =
          alt < horizonAt(az) ? [62, 52, 42] : isNaN(s) ? [55, 62, 80] : turbo(Math.sqrt(Math.min(Math.max(s, 0), 10) / 10));
        if (opt.nua && vis(alt, az)) {
          // grey veil as research/ciel_seeing.py: light grey and see-through for thin cover, darker when overcast
          const cc = Math.min(Math.max(cloudSky(fcur, alt, az), 0), 1);
          if (cc > 0) {
            const a = 0.82 * cc,
              grey = [204 - 97 * cc, 204 - 97 * cc, 214 - 94 * cc];
            col = col.map((v, k) => v * (1 - a) + grey[k]! * a);
          }
        }
        D[p] = col[0]!;
        D[p + 1] = col[1]!;
        D[p + 2] = col[2]!;
        D[p + 3] = 255;
      }
    c.putImageData(img, 0, 0);
    // skyline of the relief
    if (fe?.horizon?.length) {
      c.strokeStyle = "rgba(0,0,0,.85)";
      c.lineWidth = 1.4;
      c.beginPath();
      for (let az = 0; az <= 360; az += 2) {
        const [x, y] = fxy(Math.max(0, horizonAt(az)), az);
        if (az) c.lineTo(x, y);
        else c.moveTo(x, y);
      }
      c.stroke();
    }
    c.strokeStyle = "rgba(255,255,255,.35)";
    c.lineWidth = 1;
    [30, 60].forEach((e) => {
      c.beginPath();
      c.arc(FC, FC, ((90 - e) / 90) * FR, 0, 2 * Math.PI);
      c.stroke();
    });
    c.strokeStyle = "#000";
    c.lineWidth = 1.5;
    c.beginPath();
    c.arc(FC, FC, FR, 0, 2 * Math.PI);
    c.stroke();
    const sym = (s: string, x: number, y: number, col: string, size: number, label: string) => {
      c.font = `${size}px serif`;
      c.textAlign = "center";
      c.textBaseline = "middle";
      c.lineWidth = 3;
      c.strokeStyle = "#000";
      c.strokeText(s + "︎", x, y);
      c.fillStyle = col;
      c.fillText(s + "︎", x, y);
      c.textBaseline = "alphabetic";
      c.textAlign = "left";
      c.font = "11px 'IBM Plex Sans',sans-serif";
      c.lineWidth = 2.5;
      c.strokeText(label, x + size / 2 + 2, y - 8);
      c.fillStyle = "#fff";
      c.fillText(label, x + size / 2 + 2, y - 8);
    };
    const track = (ra: number, dec: number, col: string) => {
      c.strokeStyle = col;
      c.lineWidth = 1.2;
      c.setLineDash([2, 3]);
      c.beginPath();
      let st = false;
      for (let k = 0; k <= 10; k += 0.25) {
        const [a, z] = altaz(ra, dec, tOf(k), lat, lon);
        if (!vis(a, z)) {
          st = false;
          continue;
        }
        const [x, y] = fxy(a, z);
        if (st) c.lineTo(x, y);
        else c.moveTo(x, y);
        st = true;
      }
      c.stroke();
      c.setLineDash([]);
    };
    if (opt.cons)
      Object.entries(ST).forEach(([n, s]) => {
        const P = s.map(([ra, de]) => altaz(ra, de, t, lat, lon));
        c.strokeStyle = "rgba(255,255,255,.55)";
        c.lineWidth = 1;
        LN[n]!.forEach(([a, b]) => {
          if (vis(...P[a]!) && vis(...P[b]!)) {
            const p1 = fxy(...P[a]!),
              p2 = fxy(...P[b]!);
            c.beginPath();
            c.moveTo(...p1);
            c.lineTo(...p2);
            c.stroke();
          }
        });
        P.forEach((qq) => {
          if (vis(...qq)) {
            const [x, y] = fxy(...qq);
            c.fillStyle = "#fff";
            c.beginPath();
            c.arc(x, y, 1.8, 0, 7);
            c.fill();
          }
        });
        const v = P.filter((qq) => vis(...qq));
        if (v.length) {
          const [x, y] = fxy(...v[0]!);
          c.font = "italic 11px 'IBM Plex Sans',sans-serif";
          c.fillStyle = "rgba(255,255,255,.85)";
          c.fillText(tr(n), x + 5, y + 12);
        }
      });
    PL.forEach(([n, s, col]) => {
      if (!plOn.has(n)) return;
      const [ra, dec] = planetRaDec(n, t);
      if (opt.trk) track(ra, dec, col);
      const [a, z] = altaz(ra, dec, t, lat, lon);
      if (vis(a, z)) {
        const [x, y] = fxy(a, z);
        sym(s, x, y, col, 20, tr(n));
      }
    });
    if (opt.sol && vis(...moon)) {
      const [x, y] = fxy(...moon);
      c.fillStyle = "#F1EFE8";
      c.beginPath();
      c.arc(x, y, 9, 0, 7);
      c.fill();
      // Shadow disc clipped to the Moon: offset grows with the illuminated fraction.
      c.save();
      c.beginPath();
      c.arc(x, y, 9, 0, 7);
      c.clip();
      c.fillStyle = "#2C2C2A";
      c.beginPath();
      c.arc(x + ((phase.waxing ? -1 : 1) * 18 * phase.pct) / 100, y, 9, 0, 7);
      c.fill();
      c.restore();
      c.strokeStyle = "#000";
      c.lineWidth = 1;
      c.beginPath();
      c.arc(x, y, 9, 0, 7);
      c.stroke();
      c.font = "11px 'IBM Plex Sans',sans-serif";
      c.fillStyle = "#fff";
      c.fillText(tr("Lune"), x + 12, y - 8);
    }
    tgts.forEach((o) => {
      if (opt.trk) track(o[3], o[4], "#fff");
      const [a, z] = altaz(o[3], o[4], t, lat, lon);
      if (!vis(a, z)) return;
      const [x, y] = fxy(a, z);
      c.strokeStyle = "#000";
      c.lineWidth = 3;
      c.beginPath();
      c.arc(x, y, 7, 0, 7);
      c.stroke();
      c.strokeStyle = "#fff";
      c.lineWidth = 1.5;
      c.beginPath();
      c.arc(x, y, 7, 0, 7);
      c.moveTo(x - 11, y);
      c.lineTo(x - 4, y);
      c.moveTo(x + 4, y);
      c.lineTo(x + 11, y);
      c.moveTo(x, y - 11);
      c.lineTo(x, y - 4);
      c.moveTo(x, y + 4);
      c.lineTo(x, y + 11);
      c.stroke();
      c.font = "500 11px 'IBM Plex Sans',sans-serif";
      c.lineWidth = 2.5;
      c.strokeStyle = "#000";
      c.strokeText(o[0], x + 10, y + 14);
      c.fillStyle = "#fff";
      c.fillText(o[0], x + 10, y + 14);
    });
    c.fillStyle = "#e6ebf6";
    c.font = "500 13px 'IBM Plex Sans',sans-serif";
    c.textAlign = "center";
    (
      [
        ["N", 0],
        ["E", 90],
        ["S", 180],
        [lang === "en" ? "W" : "O", 270],
      ] as const
    ).forEach(([l, a]) => {
      const [x, y] = fxy(-8, a);
      c.fillText(l, x, y + 5);
    });
    c.textAlign = "left";
  });

  const d = new Date(t);
  const results = CAT.filter(
    (o) => (cat === "all" || o[2] === cat) && (!q.trim() || (o[0] + " " + o[1]).toLowerCase().includes(q.trim().toLowerCase())) && !tgts.includes(o),
  ).slice(0, 5);

  return (
    <section>
      <h1>{tr("Fisheye du seeing")}</h1>
      <p className="lead">
        {tr(
          "Seeing V2bd dans chaque direction, de 19h à 05h TU, jusqu'à 5° d'élévation. Calculé à partir du run global, avec par défaut la calibration de ton lieu : changer la calibration ou l'heure est instantané et ne consomme pas de quota.",
        )}
      </p>
      <div className="grid2">
        <div className="panel">
          <div style={{ position: "relative" }} onMouseLeave={() => setHov(null)}>
            <canvas
              ref={cv}
              width={FN}
              height={FN}
              aria-label={tr("Fisheye du seeing avec objets du ciel")}
              style={{ cursor: "crosshair" }}
              onMouseMove={(e) => {
                // seeing in the direction under the cursor, same computation as the colours
                const b = e.currentTarget.getBoundingClientRect(),
                  x = ((e.clientX - b.left) / b.width) * FN,
                  y = ((e.clientY - b.top) / b.height) * FN,
                  dx = x - FC,
                  dy = FC - y,
                  r = Math.hypot(dx, dy);
                if (r > FR) return setHov(null);
                const alt = 90 - (r / FR) * 90,
                  az = (Math.atan2(-dx, dy) / D2R + 360) % 360;
                const on = vis(alt, az);
                setHov({
                  x: e.clientX - b.left,
                  y: e.clientY - b.top,
                  alt,
                  az,
                  s: on ? seeSky(fcur, alt, az) : NaN,
                  c: on && opt.nua ? cloudSky(fcur, alt, az) : NaN,
                });
              }}
            />
            {hov && (
              <div
                className="mono small"
                style={{
                  position: "absolute",
                  left: hov.x + 14,
                  top: hov.y + 14,
                  transform: hov.x > 300 ? "translateX(calc(-100% - 28px))" : undefined,
                  pointerEvents: "none",
                  background: "rgba(10,15,29,.88)",
                  border: "1px solid #3a4a72",
                  borderRadius: 6,
                  padding: "3px 7px",
                  whiteSpace: "nowrap",
                }}
              >
                {/* one value per line: seeing, elevation, azimuth (then clouds when shown) */}
                {hov.alt < horizonAt(hov.az) ? (
                  <b>{tr("Relief")}</b>
                ) : hov.alt < ELMIN ? (
                  <b>{tr(`sous ${ELMIN}° d'élévation`)}</b>
                ) : (
                  <b style={{ fontSize: 14, display: "block" }}>{isNaN(hov.s) ? "–" : hov.s.toFixed(2) + "″"}</b>
                )}
                <div>{`${tr("élév.")} ${Math.round(hov.alt)}°`}</div>
                <div>{`az ${Math.round(hov.az)}° ${dir8(hov.az)}`}</div>
                {!isNaN(hov.c) && <div>{`${tr("nuages")} ${Math.round(hov.c * 100)} %`}</div>}
              </div>
            )}
          </div>
          <ColorBar left={'0"'} right={'10"'} gradient={turboGradient()} />
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            <span className="small muted">{tr("Nuit :")}</span>
            <Seg
              label={tr("Nuit du fisheye")}
              value={FNI}
              onChange={setFNI}
              options={nights.map((n, k) => [k, tr((k ? "" : "Cette nuit · ") + `Nuit du ${n}`)])}
            />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8 }}>
            <button aria-label={tr("Animer la nuit")} onClick={() => setPlaying(!playing)}>
              {playing ? "❚❚" : "▶"}
            </button>
            <input
              type="range"
              min={0}
              max={10}
              step={1}
              value={fcur}
              style={{ flex: 1 }}
              aria-label={tr("Heure")}
              onChange={(e) => setFcur(+e.target.value)}
            />
            <span className="mono" style={{ minWidth: 76, textAlign: "right", fontWeight: 500 }}>
              {`${pad2(d.getUTCDate())}/${pad2(d.getUTCMonth() + 1)} · ${pad2(d.getUTCHours())}h00 ${tr("TU")}`}
              {fe && !frameAt(fcur) ? tr(" · pas de prévision à cette heure") : ""}
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            <span className="small muted">{tr("Calibration :")}</span>
            <Seg
              label={tr("Calibration du fisheye")}
              value={cal}
              onChange={setCal}
              options={[
                ["mine", tr("Calibration de mon lieu")],
                ["def", tr("Sans calibration (K par défaut)")],
              ]}
            />
            <span className="small muted">{cal === "mine" ? `${tr("K calés de")} ${tr(place.nom)}` : tr("K des voisins")}</span>
          </div>
        </div>
        <div className="stack">
          <div className="panel">
            <div className="tiles">
              <div className="tile">
                <div className="l">{tr("Seeing au zénith")}</div>
                <div className="v">{(() => {
                  const z = seeSky(fcur, 90, 0);
                  return isNaN(z) ? "–" : z.toFixed(2) + "\"";
                })()}</div>
              </div>
              <div className="tile">
                <div className="l">{tr("Soleil")}</div>
                <div className="v" style={{ fontSize: 13 }}>
                  {sun[0].toFixed(0)}° · {tr(sun[0] < -18 ? "nuit astronomique" : sun[0] < -12 ? "crépuscule astronomique" : "crépuscule")}
                </div>
              </div>
              <div className="tile" style={{ gridColumn: "1/-1" }}>
                <div className="l">{tr("Lune")}</div>
                <div className="v" style={{ fontSize: 13 }}>
                  {tr(phase.name)}, {phase.pct} % · {moon[0] > 0 ? `${tr("élévation")} ${moon[0].toFixed(0)}°` : tr("couchée")}
                </div>
              </div>
            </div>
            <p className="small" style={{ margin: "10px 0 0" }}>
              <span className="pill p-ok">{tr("Fisheye du jour : 1 / 1")}</span>{" "}
              <span className="muted">
                {tr(place.nom)} · run {runLabel(runMs)} · {tr("calculé en 18 s")}
              </span>
            </p>
          </div>
          <div className="panel">
            <h2>{tr("Afficher")}</h2>
            <div>
              {(Object.keys(OPT0) as OptKey[]).map((k) => (
                <Chip key={k} on={opt[k]} onToggle={() => setOpt({ ...opt, [k]: !opt[k] })}>
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 16 16"
                    aria-hidden="true"
                    style={{ verticalAlign: "-3px", marginRight: 4 }}
                    dangerouslySetInnerHTML={{ __html: OPT_ICON[k] }}
                  />
                  {tr(OPT0[k][0])}
                </Chip>
              ))}
            </div>
            {opt.nua && fe && !hasClouds && (
              <p className="small muted" style={{ margin: "4px 0 0" }}>
                {tr("Pas de nuages pour ce run : ils arrivent avec le prochain run AROME.")}
              </p>
            )}
          </div>
          <div className="panel">
            <h2>{tr("Planètes")}</h2>
            <div>
              {PL.map(([n, s, col]) => (
                <Chip
                  key={n}
                  on={plOn.has(n)}
                  onToggle={() => {
                    const x = new Set(plOn);
                    if (x.has(n)) x.delete(n);
                    else x.add(n);
                    setPlOn(x);
                  }}
                >
                  <span style={{ color: col, fontSize: 16, lineHeight: 1, fontFamily: "serif" }}>{s}︎</span>
                  {tr(n)}
                </Chip>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="panel" style={{ marginTop: 16 }}>
        <h2>{tr("Mes objets cibles")}</h2>
        <div className="tablewrap">
          <table className="list">
            <thead>
              <tr>
                <th>{tr("Objet")}</th>
                <th>{tr("Élévation")}</th>
                <th>Seeing</th>
                <th>{tr("Meilleur moment")}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {tgts.length ? (
                tgts.map((o, n) => {
                  const [a, z] = altaz(o[3], o[4], t, lat, lon),
                    v = vis(a, z),
                    b = best(o);
                  return (
                    <tr key={o[0]}>
                      <td>
                        <b style={{ fontWeight: 500 }}>{o[0]}</b> <span className="small muted">{tr(o[1])}</span>
                      </td>
                      <td className="mono">
                        {v ? (
                          a.toFixed(0) + "°"
                        ) : (
                          <span className="muted" style={{ fontFamily: "var(--f-body)" }}>
                            {tr("sous l'horizon")}
                          </span>
                        )}
                      </td>
                      <td className="mono">{v ? seeSky(fcur, a, z).toFixed(1) + '"' : "–"}</td>
                      <td className="mono">
                        {b ? (
                          pad2(new Date(tOf(b[1])).getUTCHours()) + "h · " + b[0].toFixed(1) + '"'
                        ) : (
                          <span className="muted">{tr("invisible")}</span>
                        )}
                      </td>
                      <td>
                        <button aria-label={`${tr("Retirer")} ${o[0]}`} onClick={() => setTgts(tgts.filter((_, k) => k !== n))}>
                          ✕
                        </button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={5} className="muted">
                    {tr("Aucun objet. Cherche dans un catalogue ci-dessous.")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "180px minmax(0,1fr)", gap: 8, marginTop: 12 }}>
          <select aria-label={tr("Catalogue")} value={cat} onChange={(e) => setCat(e.target.value)}>
            <option value="all">{tr("Tous les catalogues")}</option>
            {["Messier", "NGC", "Caldwell", "Étoiles doubles"].map((c) => (
              <option key={c} value={c}>
                {tr(c)}
              </option>
            ))}
          </select>
          <input placeholder={tr("M31, Andromède, Albireo…")} aria-label={tr("Chercher un objet")} value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div style={{ marginTop: 6 }}>
          {(q.trim() || cat !== "all") &&
            results.map((o) => (
              <div
                key={o[0]}
                style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "5px 0", borderBottom: "1px solid var(--line)", fontSize: 13 }}
              >
                <span>
                  <b style={{ fontWeight: 500 }}>{o[0]}</b>{" "}
                  <span className="small muted">
                    {tr(o[1])} · {tr(o[2])}
                  </span>
                </span>
                <button onClick={() => setTgts([...tgts, o])}>{tr("+ Ajouter")}</button>
              </div>
            ))}
        </div>
        <p className="note">
          {tr("Étoiles, objets, planètes, Soleil et Lune placés à leurs vraies positions pour ce lieu et cette nuit.")}
        </p>
      </div>
    </section>
  );
}
