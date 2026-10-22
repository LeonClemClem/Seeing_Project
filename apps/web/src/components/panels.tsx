/** Chart panels shared by Prévision, Calibrer and Mes lieux. */
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { histChart, histSvg, seeHist } from "../charts/lieuCharts";
import { cn2Ctx, cn2ProfileSvg, cn2RealSvg } from "../charts/realCharts";
import { useRealForecast } from "../data/forecast";
import type { Place } from "../data/places";
import { tr } from "../i18n";
import type { LieuData } from "../mock/engine";
import { setState, useLangMemo, useUi, type UiState } from "../store";
import { Chip, SvgChart } from "./ui";

/** Measurement display chips ("Données : brutes / médianes horaires / courbe / ☾ médianes nocturnes"). */
export function DataChips({ id }: { id: string }) {
  const showObs = useUi((s) => s.showObs);
  const mesf = useUi((s) => s.mesf);
  const corrf = useUi((s) => s.corrf);
  const on = (k: "brut" | "horaire" | "courbe" | "nuit") =>
    k === "nuit" ? corrf.nuit : k === "courbe" ? mesf.courbe : mesf[k] && corrf[k];
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
export function HistPanel({ data, OB, inset = true }: { data: LieuData; OB: boolean; inset?: boolean }) {
  const mesf = useUi((s) => s.mesf);
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

  const h = useLangMemo(() => histChart(data, { OB, mesf, zoom, win }), [data, OB, mesf, zoom, win]);
  const hv = useMemo(() => (inset ? seeHist(data) : []), [data, inset]);
  const small = useLangMemo(() => (hv.length ? histSvg(hv, 332, 56, true).svg : ""), [hv]);

  return (
    <>
      <div className="hghead">
        <div className="hgleft" style={{ display: "flex", gap: 6, alignItems: "center", margin: "4px 0", flexWrap: "wrap" }}>
          <span className="small muted">{tr("Zoom :")}</span>
          <button onClick={() => setZoom((z) => Math.max(1, z * 0.5))}>−</button>
          <button onClick={() => setZoom((z) => Math.min(16, z * 2))}>+</button>
          <button onClick={() => setZoom(1)}>{tr("tout voir")}</button>
          <Chip on={stretch} onToggle={() => setStretch(!stretch)} style={{ margin: "0 0 0 6px" }}>
            {tr("étirement vertical auto")}
          </Chip>
          <span className="small muted">{zoom > 1 ? tr(`× ${zoom} (fais défiler horizontalement)`) : ""}</span>
        </div>
        {OB && small && (
          <div className="hginset" style={{ padding: "2px 4px" }}>
            <SvgChart html={small} viewBox="0 0 332 56" label="Histogramme du seeing enregistré" />
          </div>
        )}
      </div>
      <div ref={sc} style={{ overflowX: "auto" }}>
        <SvgChart
          html={h.svg}
          viewBox={`0 0 ${1100 * zoom} 240`}
          label="Historique du lieu"
          style={{ width: `${100 * zoom}%`, minWidth: `${700 * zoom}px`, maxWidth: "none" }}
        />
      </div>
      <p className="small muted" style={{ margin: "4px 0 0" }}>
        {h.note}
      </p>
    </>
  );
}

/** Real Cn² panel (latest run) with altitude range and the profile under the cursor. */
export function Cn2RealPanel({ place, profile = true, style }: { place: Place; profile?: boolean; style?: CSSProperties }) {
  const [alt, setAlt] = useState("4");
  const { forecast, cn2 } = useRealForecast(place);
  const ctx = useMemo(() => (cn2.data ? cn2Ctx(cn2.data, forecast.data, alt) : null), [cn2.data, forecast.data, alt]);
  const svg = useLangMemo(() => (ctx && cn2.data ? cn2RealSvg(ctx, Date.parse(cn2.data.run_time)) : ""), [ctx, cn2.data]);
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<HTMLDivElement>(null);
  const hi = hover ?? (ctx ? Math.min(ctx.n - 1, 6) : 0);
  const pf = useLangMemo(() => (ctx && profile ? cn2ProfileSvg(ctx, hi, 130) : ""), [ctx, hi, profile]);

  if (cn2.isLoading) return <p className="muted small">{tr("Chargement…")}</p>;
  if (cn2.isError || !ctx)
    return (
      <SvgChart
        html={`<text x="450" y="190" text-anchor="middle" font-size="13" fill="#97a2bd">${tr("Pas de panneau Cn² enregistré pour ce lieu.")}</text>`}
        viewBox="0 0 900 400"
        label="Panneau Cn2"
      />
    );
  const mm = (e: React.MouseEvent) => {
    const el = svgRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect(),
      x = ((e.clientX - r.left) / r.width) * ctx.W,
      i = Math.floor(((x - ctx.L) / ctx.pw) * ctx.n);
    if (i >= 0 && i < ctx.n) setHover(i);
  };
  return (
    <div style={style}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", margin: "4px 0 6px" }}>
        <label className="small muted" htmlFor={"alt-" + place.id}>
          {tr("Altitude")}
        </label>
        <select id={"alt-" + place.id} value={alt} onChange={(e) => setAlt(e.target.value)}>
          <option value="bl">{tr("0–1 km (couche limite)")}</option>
          <option value="4">{tr("0–4 km")}</option>
          <option value="jet">{tr("jet stream (8–16 km d'altitude)")}</option>
          <option value="tout">{tr("jusqu'en haut (16 km)")}</option>
        </select>
        {profile && <span className="small muted">{tr("survole le panneau : profil à l'heure choisie")}</span>}
      </div>
      <div style={{ display: "flex", gap: 2, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div ref={svgRef} style={{ flex: "1 1 520px", minWidth: 0 }} onMouseMove={profile ? mm : undefined}>
          <SvgChart html={svg} viewBox={`0 0 ${ctx.W} ${ctx.H}`} label="Panneau Cn2" />
        </div>
        {profile && (
          <SvgChart html={pf} viewBox="0 0 130 400" label="Profil de Cn2 à l'heure survolée" style={{ flex: "0 0 130px", width: 130 }} />
        )}
      </div>
    </div>
  );
}
