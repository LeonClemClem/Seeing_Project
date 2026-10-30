/** Chart panels shared by Prévision, Calibrer and Mes lieux. */
import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";

import { histChart, histSvg, seeHist } from "../charts/lieuCharts";
import { cn2AxisLeft, cn2AxisRight, cn2Ctx, cn2ProfileSvg, cn2RealSvg, type Cn2Ctx } from "../charts/realCharts";
import { hourlyMedians, useHourlyMedians, useRawMeasurements, useRealForecast, type View } from "../data/forecast";
import type { Place } from "../data/places";
import { tr } from "../i18n";
import type { LieuData } from "../mock/engine";
import { setState, useLangMemo, useUi, type UiState } from "../store";
import { exportSvgIn, fileSafe } from "../lib/export";
import { pad2 } from "../lib/util";
import { Chip, Seg, Spinner, SvgChart } from "./ui";

/** Measurement display chips ("Données : brutes / médianes horaires / courbe / ☾ médianes nocturnes"). */
export function DataChips({ id }: { id: string }) {
  const showObs = useUi((s) => s.showObs);
  const mesf = useUi((s) => s.mesf);
  const corrf = useUi((s) => s.corrf);
  const on = (k: "brut" | "horaire" | "courbe" | "nuit") =>
    // brutes / médianes horaires drive both the charts (mesf) and the correlation (corrf), which Mes lieux sets
    // apart: lit when either shows them, and a click sets both, so that the chip never says "off" while drawn
    k === "nuit" ? corrf.nuit : k === "courbe" ? mesf.courbe : mesf[k] || corrf[k];
  const toggle = (k: "brut" | "horaire" | "courbe" | "nuit") => {
    const v = !on(k);
    setState((s: UiState) => ({
      corrf: k === "courbe" ? s.corrf : { ...s.corrf, [k]: v },
      mesf: k === "nuit" ? s.mesf : { ...s.mesf, [k]: v },
    }));
  };
  return (
    <>
      <Chip on={showObs} onToggle={() => setState({ showObs: !showObs })}>
        {tr("Afficher les mesures du seeing monitor")}
      </Chip>
      <span className="small muted">{tr("Données :")}</span>
      <Chip on={on("brut")} onToggle={() => toggle("brut")}>
        {tr("brutes")}
      </Chip>
      <Chip on={on("horaire")} onToggle={() => toggle("horaire")}>
        {tr("médianes horaires")}
      </Chip>
      <Chip on={on("courbe")} onToggle={() => toggle("courbe")}>
        {tr("courbe médiane horaire")}
      </Chip>
      <Chip on={on("nuit")} onToggle={() => toggle("nuit")}>
        {tr("☾ médianes nocturnes")}
      </Chip>
      <span style={{ width: 12 }} />
      <span className="small muted" data-id={id}>
        {tr("Nuit seulement (17h30–06h TU)")}
      </span>
    </>
  );
}

/** History chart with horizontal zoom and the auto vertical stretch on the visible part. */
/** `head` (title and legend) goes in the left column of the header, as in the mock-up: the histogram inset on
 * the right then spans from the top of the panel down to the zoom row. */
export function HistPanel({
  data,
  OB,
  inset = true,
  head,
  rm,
}: {
  data: LieuData;
  OB: boolean;
  inset?: boolean;
  head?: ReactNode;
  /** hours left out of the calibration, hourKey "night|h" (Calibrer) */
  rm?: ReadonlySet<string>;
}) {
  const mesf = useUi((s) => s.mesf);
  const sel = useUi((s) => s.selNight);
  const [zoom, setZoom] = useState(1);
  const [stretch, setStretch] = useState(true);
  const [win, setWin] = useState<[number, number] | null>(null);
  const sc = useRef<HTMLDivElement>(null);

  const measure = () => {
    const el = sc.current;
    const W = 1100 * zoom;
    if (!el || !stretch || zoom <= 1 || el.scrollWidth <= el.clientWidth + 2) return setWin(null);
    setWin([(el.scrollLeft / el.scrollWidth) * W, ((el.scrollLeft + el.clientWidth) / el.scrollWidth) * W]);
  };
  useEffect(measure, [zoom, stretch]);
  useEffect(() => {
    const el = sc.current;
    if (!el) return;
    let tm: ReturnType<typeof setTimeout>;
    const on = () => {
      clearTimeout(tm);
      tm = setTimeout(measure, 120);
    };
    el.addEventListener("scroll", on);
    return () => {
      clearTimeout(tm);
      el.removeEventListener("scroll", on);
    };
  });

  const h = useLangMemo(() => histChart(data, { OB, mesf, zoom, win, sel, rm }), [data, OB, mesf, zoom, win, sel, rm]);
  /** Click on a night: highlight it in the history and the correlation (click again: none). */
  const pick = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect(),
      x = ((e.clientX - r.left) / r.width) * 1100 * zoom,
      hit = h.hits.find((q) => x >= q.x0 && x <= q.x1);
    if (hit) setState({ selNight: sel === hit.night ? null : hit.night });
  };
  const hv = useMemo(() => (inset ? seeHist(data) : []), [data, inset]);
  // inset as the mock-up: it takes the height of the header row, the histogram fills it
  const insetRef = useRef<HTMLDivElement>(null);
  const [hh, setHh] = useState(56);
  useEffect(() => {
    const el = insetRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setHh(Math.max(52, Math.round(el.clientHeight - 6))));
    ro.observe(el);
    return () => ro.disconnect();
  }, [hv.length, OB]);
  const small = useLangMemo(() => (hv.length ? histSvg(hv, 332, hh, true).svg : ""), [hv, hh]);

  return (
    <>
      <div className="hghead">
        <div className="hgleft">
          {head}
          <div style={{ display: "flex", gap: 6, alignItems: "center", margin: "4px 0", flexWrap: "wrap" }}>
            <span className="small muted">{tr("Zoom :")}</span>
            <button onClick={() => setZoom((z) => Math.max(1, z * 0.5))}>−</button>
            <button onClick={() => setZoom((z) => Math.min(16, z * 2))}>+</button>
            <button onClick={() => setZoom(1)}>{tr("tout voir")}</button>
            <Chip on={stretch} onToggle={() => setStretch(!stretch)} style={{ margin: "0 0 0 6px" }}>
              {tr("étirement vertical auto")}
            </Chip>
            <span className="small muted">{zoom > 1 ? tr(`× ${zoom} (fais défiler horizontalement)`) : ""}</span>
          </div>
        </div>
        {OB && small && (
          <div className="hginset" ref={insetRef}>
            <SvgChart
              html={small}
              viewBox={`0 0 332 ${hh}`}
              label="Histogramme du seeing enregistré"
              style={{ position: "absolute", left: 4, top: 2, width: "calc(100% - 8px)", height: hh, maxWidth: "none" }}
            />
          </div>
        )}
      </div>
      <div ref={sc} style={{ overflowX: "auto" }}>
        <div onClick={pick} style={{ width: `${100 * zoom}%`, minWidth: `${700 * zoom}px`, cursor: "pointer" }}>
          <SvgChart html={h.svg} viewBox={`0 0 ${1100 * zoom} 240`} label="Historique du lieu" style={{ width: "100%", maxWidth: "none" }} />
        </div>
      </div>
      <p className="small muted" style={{ margin: "4px 0 0" }}>
        {h.note}{" "}
        {sel ? (
          <>
            · <b style={{ color: "#f2c14e" }}>{tr(`nuit du ${sel.slice(8, 10)}/${sel.slice(5, 7)} surlignée`)}</b>{" "}
            <button className="small" onClick={() => setState({ selNight: null })}>
              {tr("ne plus surligner")}
            </button>
          </>
        ) : (
          tr("· clique sur une nuit pour la surligner ici et dans la corrélation.")
        )}
      </p>
    </>
  );
}

/** Real Cn² panel: week (up to 7 days of main runs stitched) or latest forecasts, altitude range, zoom,
 * measured hourly medians, and the profile under the cursor (with the jet stream). */
/** Copies of the two vertical axes of the zoomed Cn² panel, pinned on the edges of the visible part. Opaque
 * margins (panel colour) hide the drawing scrolling under them; the right one also keeps the "Seeing (″)" title.
 * No pointer events: dragging and hovering go through to the drawing. */
function FixedAxes({ ctx, axes, height }: { ctx: Cn2Ctx; axes: { left: string; right: string }; height: number }) {
  const k = height / ctx.H,
    R = ctx.L + ctx.pw,
    TW = 90, // the right copy starts TW units before the right edge, for the title
    bg = "fill:var(--panel)";
  const common: CSSProperties = { position: "absolute", top: 0, height, pointerEvents: "none", maxWidth: "none" };
  return (
    <>
      <SvgChart
        html={`<rect x="0" y="0" width="${ctx.L}" height="${ctx.H}" style="${bg}"/>${axes.left}`}
        viewBox={`0 0 ${ctx.L} ${ctx.H}`}
        label="Axe des altitudes"
        style={{ ...common, left: 0, width: ctx.L * k }}
      />
      <SvgChart
        html={`<rect x="${R}" y="0" width="${ctx.W - R}" height="${ctx.H}" style="${bg}"/><rect x="${ctx.W - TW}" y="0" width="${TW}" height="${ctx.T - 1}" style="${bg}"/>${axes.right}`}
        viewBox={`${ctx.W - TW} 0 ${TW} ${ctx.H}`}
        label="Axe du seeing"
        style={{ ...common, right: 0, width: TW * k }}
      />
    </>
  );
}

export function Cn2RealPanel({
  place,
  profile = true,
  style,
  defaultView = "week",
}: {
  place: Place;
  profile?: boolean;
  style?: CSSProperties;
  defaultView?: View;
}) {
  const [alt, setAlt] = useState("4");
  const [view, setView] = useState<View>(defaultView);
  const [zoom, setZoom] = useState(1);
  const [smooth, setSmooth] = useState(false);
  const { forecast, cn2 } = useRealForecast(place, view);
  const histMed = useHourlyMedians(place);
  const raw = useRawMeasurements(place);
  const showObs = useUi((s) => s.showObs);
  const mesf = useUi((s) => s.mesf);
  // hourly medians: research history first, then those of the raw points (daily monitor collection)
  const obs = useMemo(() => new Map([...hourlyMedians(raw), ...histMed]), [raw, histMed]);
  const ctx = useMemo(
    () => (cn2.data ? cn2Ctx(cn2.data, forecast.data, alt, showObs ? obs : undefined, zoom, showObs ? raw : [], mesf) : null),
    [cn2.data, forecast.data, alt, obs, raw, showObs, zoom, mesf],
  );
  const svg = useLangMemo(
    () => (ctx && cn2.data ? cn2RealSvg(ctx, Date.parse(cn2.data.run_time), smooth) : ""),
    [ctx, cn2.data, smooth],
  );
  // zoomed: both vertical axes stay on the edges of the visible part (the drawing scrolls under them)
  const axes = useLangMemo(() => (ctx && ctx.n ? { left: cn2AxisLeft(ctx), right: cn2AxisRight(ctx) } : null), [ctx]);
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<HTMLDivElement>(null);
  const scRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; s: number } | null>(null);
  // as the mock-up: zoomed, the drawing is (frame width x zoom) px wide at the same height, and the
  // profile on its right takes the height of the drawing
  const [scw, setScw] = useState(900);
  const [hp, setHp] = useState(400);
  useEffect(() => {
    const sc = scRef.current,
      el = svgRef.current;
    if (!sc || !el) return;
    const ro = new ResizeObserver(() => {
      setScw(sc.clientWidth || 900);
      setHp(el.getBoundingClientRect().height || 400);
    });
    ro.observe(sc);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ctx]);
  const pfW = Math.max(90, Math.round((130 * 400) / hp));
  const hi = hover ?? (ctx ? Math.min(ctx.n - 1, 6) : 0);
  const pf = useLangMemo(() => (ctx && profile ? cn2ProfileSvg(ctx, hi, pfW) : ""), [ctx, hi, profile, pfW]);
  /** Zoom keeping the centre of the visible part in place (as the mock-up). */
  const setZoomC = (f: number) => {
    const sc = scRef.current,
      frac = sc && sc.scrollWidth ? (sc.scrollLeft + sc.clientWidth / 2) / sc.scrollWidth : 0.5;
    const z = f ? Math.min(16, Math.max(1, zoom * f)) : 1;
    setZoom(z);
    requestAnimationFrame(() => {
      const s2 = scRef.current;
      if (s2) s2.scrollLeft = frac * s2.scrollWidth - s2.clientWidth / 2;
    });
  };

  const controls = (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", margin: "4px 0 6px" }}>
      <Seg
        value={view}
        onChange={(v) => {
          setView(v);
          setHover(null);
        }}
        options={[
          ["week", tr("Semaine (7 j max)")],
          ["run", tr("Dernières prévisions")],
        ]}
      />
      <label className="small muted" htmlFor={"alt-" + place.id}>
        {tr("Altitude")}
      </label>
      <select id={"alt-" + place.id} value={alt} onChange={(e) => setAlt(e.target.value)}>
        <option value="bl">{tr("0–1 km (couche limite)")}</option>
        <option value="4">{tr("0–4 km")}</option>
        <option value="jet">{tr("jet stream (8–16 km d'altitude)")}</option>
        <option value="tout">{tr("jusqu'en haut (16 km)")}</option>
      </select>
      <span className="small muted">{tr("Zoom :")}</span>
      <button onClick={() => setZoomC(0.5)}>−</button>
      <button onClick={() => setZoomC(2)}>+</button>
      <button onClick={() => setZoomC(0)}>{tr("tout voir")}</button>
      <button
        title={tr("Télécharger le panneau Cn² (PNG)")}
        onClick={() => exportSvgIn(svgRef.current, `cn2_${fileSafe(place.nom)}_${(cn2.data?.run_time ?? "").slice(0, 13).replace(/[-T]/g, "")}Z.png`)}
      >
        ⤓ PNG
      </button>
      <Chip on={smooth} onToggle={() => setSmooth(!smooth)} title={tr("Fondu entre heures voisines, pour l'image seulement")}>
        {tr("Interpolation temporelle")}
      </Chip>
      {profile && <span className="small muted">{tr("survole le panneau : profil à l'heure choisie")}</span>}
    </div>
  );
  if (cn2.isLoading)
    return (
      <div style={style}>
        {controls}
        <Spinner />
      </div>
    );
  if (cn2.isError || !ctx)
    return (
      <div style={style}>
        {controls}
        <SvgChart
          html={`<text x="450" y="190" text-anchor="middle" font-size="13" fill="#97a2bd">${tr("Pas de panneau Cn² enregistré pour ce lieu.")}</text>`}
          viewBox="0 0 900 400"
          label="Panneau Cn2"
        />
      </div>
    );
  const mm = (e: React.MouseEvent) => {
    const el = svgRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect(),
      x = ((e.clientX - r.left) / r.width) * ctx.W,
      i = Math.floor(((x - ctx.L) / ctx.pw) * ctx.n);
    if (i >= 0 && i < ctx.n) setHover(i);
  };
  const t0 = ctx.times[0],
    t1 = ctx.times[ctx.n - 1],
    holes = ctx.lg.filter((row) => row.every((v) => v == null)).length,
    fmtT = (t: number) => {
      const d = new Date(t);
      return `${pad2(d.getUTCDate())}/${pad2(d.getUTCMonth() + 1)} ${pad2(d.getUTCHours())}h`;
    };
  return (
    <div style={style}>
      {controls}
      <div style={{ display: "flex", gap: 2, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 520px", minWidth: 0, position: "relative" }}>
          <div
            ref={scRef}
            style={{ minWidth: 0, overflowX: "auto", cursor: zoom > 1 ? "grab" : undefined }}
            onMouseDown={(e) => {
              if (zoom > 1 && scRef.current) drag.current = { x: e.clientX, s: scRef.current.scrollLeft };
            }}
            onMouseMove={(e) => {
              if (drag.current && scRef.current) scRef.current.scrollLeft = drag.current.s - (e.clientX - drag.current.x);
            }}
            onMouseUp={() => (drag.current = null)}
            onMouseLeave={() => (drag.current = null)}
          >
            <div
              ref={svgRef}
              style={
                zoom > 1
                  ? { width: scw * zoom, minWidth: 0, maxWidth: "none" }
                  : { width: "100%", minWidth: 520, maxWidth: "100%" }
              }
              onMouseMove={profile ? mm : undefined}
            >
              <SvgChart html={svg} viewBox={`0 0 ${ctx.W} ${ctx.H}`} label="Panneau Cn2" style={{ width: "100%", maxWidth: "none" }} />
            </div>
          </div>
          {zoom > 1 && axes && <FixedAxes ctx={ctx} axes={axes} height={hp} />}
        </div>
        {profile && (
          <SvgChart
            html={pf}
            viewBox={`0 0 ${pfW} 400`}
            label="Profil de Cn2 à l'heure survolée"
            style={{ flex: "0 0 130px", width: 130, height: hp }}
          />
        )}
      </div>
      {t0 != null && t1 != null && cn2.data && (
        <p className="small muted mono" style={{ margin: "4px 0 0" }}>
          {tr(view === "week" ? "jusqu'à 7 jours de runs principaux collés" : "dernières prévisions")} · {tr("du")} {fmtT(t0)} {tr("au")} {fmtT(t1)}{" "}
          {tr("TU")} · {tr("dernier run")} {cn2.data.run_time.slice(0, 13).replace("T", " ")}Z · {tr("seeing de nuit seulement")} · {holes}{" "}
          {tr("h sans Cn² (H+0 ou trou)")}
        </p>
      )}
    </div>
  );
}
