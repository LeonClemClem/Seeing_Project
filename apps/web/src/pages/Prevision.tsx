/**
 * Per-place forecast. API sites show the real latest run (seeing, Cn², boundary layer); personal places
 * use the fictitious model with the K in use, plus mock measurements.
 */
import { useState } from "react";
import { Link } from "react-router-dom";

import { corrChart } from "../charts/lieuCharts";
import { cn2Svg, prevSvg } from "../charts/mockCharts";
import { PVDEF, PVGRP, prevRealSvg, pvPanel } from "../charts/realCharts";
import { Cn2RealPanel, DataChips, HistPanel } from "../components/panels";
import { useHourlyMedians, useRealForecast, useSiteHistory, type View } from "../data/forecast";
import { Cn2Legend, LegArome, LegBreak, LegDay, LegMed, LegMes, Seg, Sw, SvgChart } from "../components/ui";
import { kHidden, kTxt, useCurrentPlace, type Place } from "../data/places";
import { tr } from "../i18n";
import { fmt } from "../lib/util";
import { lieuData } from "../mock/engine";
import { useLangMemo, useUi } from "../store";

export default function Prevision() {
  const place = useCurrentPlace();
  const showObs = useUi((s) => s.showObs);
  const OB = showObs && !place.real;

  return (
    <section>
      <h1>
        {tr("Prévision")} · {tr(place.nom)}
      </h1>
      <p className="lead">
        {tr(
          "Seeing V2bd au lieu, panneau Cn², historique et corrélation avec tes mesures, avec les K en service pour ce lieu. Les K se règlent dans l'onglet Calibrer.",
        )}
      </p>
      <div id="popts">
        <DataChips id="popts" />
      </div>
      <div className="stack">
        <div className="panel">
          <h2>{tr("Seeing prévu")}</h2>
          <div className="legend">
            <LegArome />
            {!place.real && (
              <span>
                <Sw style={{ width: 16, borderTop: "2px dashed #9cc7ff" }} />
                {tr("V2bd avec les K calés")}
              </span>
            )}
            {OB && <LegMes />}
            {OB && <LegMed />}
            <LegDay />
          </div>
          {place.real ? <RealSeeing place={place} /> : <MockSeeing place={place} />}
        </div>
        <div className="panel">
          <h2>{tr("Cn² (altitude × temps)")}</h2>
          <Cn2Legend obs={OB} convective={!place.real} />
          {place.real ? <Cn2RealPanel place={place} defaultView="run" /> : <MockCn2 place={place} />}
          <KRead place={place} />
        </div>
        <div className="panel">
          <h2>{tr(OB ? "Historique (prévisions et mesures du lieu)" : "Historique des prévisions du lieu")}</h2>
          <div className="legend">
            <span>
              <Sw style={{ width: 16, height: 3, background: "var(--arome)" }} />
              V2bd
            </span>
            {OB && <LegMes />}
            {OB && <LegMed />}
            <LegBreak />
          </div>
          {place.real ? <RealHistory place={place} OB={OB} /> : <MockHistory place={place} OB={OB} />}
        </div>
        <div className="grid2" style={{ gridTemplateColumns: "minmax(0,1fr) minmax(0,1.5fr)", alignItems: "start" }}>
          <div className="panel">
            <h2>{tr("Corrélation prévu / mesuré (nuit)")}</h2>
            {place.real ? <RealCorr place={place} /> : <MockCorr place={place} />}
          </div>
          <div className="panel">
            <h2>{tr("Variables du modèle (passées et prévues)")}</h2>
            {place.real ? <ModelVars place={place} /> : <p className="muted small">{tr("Pas de variables enregistrées pour ce lieu.")}</p>}
          </div>
        </div>
      </div>
    </section>
  );
}

/** Research history of a real site (sent by research/envoi_site.py). */
function RealHistory({ place, OB }: { place: Place; OB: boolean }) {
  const data = useSiteHistory(place);
  if (!data || !data.episodes.length) return <NoData text="Pas de période avec prévision et mesures pour ce lieu." />;
  return <HistPanel data={data} OB={OB} />;
}

function RealCorr({ place }: { place: Place }) {
  const data = useSiteHistory(place);
  const corrf = useUi((s) => s.corrf);
  const c = useLangMemo(() => (data && data.paires.length ? corrChart(data, corrf) : null), [data, corrf]);
  if (!c) return <NoData text="Corrélation : choisis un lieu avec seeing monitor." />;
  return (
    <>
      <p className="small muted mono" style={{ margin: "0 0 2px" }}>
        {c.ct}
      </p>
      <SvgChart html={c.svg} viewBox="0 0 340 320" label="Corrélation du lieu" style={{ maxWidth: 520 }} />
    </>
  );
}

function NoData({ text }: { text: string }) {
  return (
    <p className="muted" style={{ textAlign: "center", padding: "40px 0" }}>
      {tr(text)}
    </p>
  );
}

function KRead({ place }: { place: Place }) {
  const role = useUi((s) => s.role);
  const K = useUi((s) => s.K);
  const kmode = useUi((s) => s.kmode);
  const txt = place.real
    ? `${kTxt(place.K, kHidden(place, role), fmt)} (${tr("calcul du run, données réelles")})`
    : `K_TKE = ${fmt(K[0])}  K_CIS = ${fmt(K[1])}  K_conv = 0.1 (${tr(kmode === "A" ? "calés" : "manuels")})`;
  return (
    <p className="small muted" style={{ margin: 0 }}>
      {tr("K en service :")} <span className="mono">{tr(txt)}</span> ·{" "}
      <Link to="/calibrer" style={{ color: "#9cc7ff" }}>
        {tr("régler les K dans Calibrer")}
      </Link>
    </p>
  );
}

function RealSeeing({ place }: { place: Place }) {
  const role = useUi((s) => s.role);
  const showObs = useUi((s) => s.showObs);
  const { forecast } = useRealForecast(place);
  const obs = useHourlyMedians(place);
  const svg = useLangMemo(
    () => (forecast.data ? prevRealSvg(forecast.data, kTxt(place.K, kHidden(place, role), fmt), showObs ? obs : undefined) : ""),
    [forecast.data, place, role, obs, showObs],
  );
  if (forecast.isLoading) return <p className="muted small">{tr("Chargement…")}</p>;
  if (forecast.isError || !forecast.data) return <NoData text="Pas de prévision enregistrée pour ce lieu." />;
  return <SvgChart html={svg} viewBox="0 0 900 220" label="Seeing prévu" />;
}

function MockSeeing({ place }: { place: Place }) {
  const K = useUi((s) => s.K);
  const KCAL = useUi((s) => s.KCAL);
  const kmode = useUi((s) => s.kmode);
  const showObs = useUi((s) => s.showObs);
  const mesf = useUi((s) => s.mesf);
  const svg = useLangMemo(() => prevSvg(K, KCAL, kmode === "M", showObs, { mesf }, place.f), [K, KCAL, kmode, showObs, mesf, place.f]);
  return <SvgChart html={svg} viewBox="0 0 900 220" label="Seeing prévu" />;
}

function MockCn2({ place }: { place: Place }) {
  const K = useUi((s) => s.K);
  const KCAL = useUi((s) => s.KCAL);
  const showObs = useUi((s) => s.showObs);
  const mesf = useUi((s) => s.mesf);
  const svg = useLangMemo(() => cn2Svg(K, KCAL, showObs, { mesf }, place.f), [K, KCAL, showObs, mesf, place.f]);
  return (
    <>
      <SvgChart html={svg} viewBox="0 0 900 270" label="Panneau Cn2" />
      <p className="small muted">{tr("Seeing : 0 NaN (H+0 masqué) · Cn² : 0 NaN, trous mis à 0.")}</p>
    </>
  );
}

function MockHistory({ place, OB }: { place: Place; OB: boolean }) {
  const K = useUi((s) => s.K);
  const KCAL = useUi((s) => s.KCAL);
  const data = useLangMemo(() => lieuData(place.nom, place.f, K, KCAL), [place, K, KCAL]);
  return <HistPanel data={data} OB={OB} />;
}

function MockCorr({ place }: { place: Place }) {
  const K = useUi((s) => s.K);
  const KCAL = useUi((s) => s.KCAL);
  const corrf = useUi((s) => s.corrf);
  const c = useLangMemo(() => corrChart(lieuData(place.nom, place.f, K, KCAL), corrf), [place, K, KCAL, corrf]);
  return (
    <>
      <p className="small muted mono" style={{ margin: "0 0 2px" }}>
        {c.ct}
      </p>
      <SvgChart html={c.svg} viewBox="0 0 340 320" label="Corrélation du lieu" style={{ maxWidth: 520 }} />
    </>
  );
}

function ModelVars({ place }: { place: Place }) {
  const [view, setView] = useState<View>("week");
  const [zoom, setZoom] = useState(1);
  const { forecast } = useRealForecast(place, view);
  const [sel, setSel] = useState<Set<string>[]>(() => [new Set(["see"]), new Set(["u10", "u100", "u500"])]);
  const panels = useLangMemo(
    () => (forecast.data ? [0, 1].map((k) => pvPanel(forecast.data!, place.nom, sel[k]!, zoom)) : null),
    [forecast.data, place.nom, sel, zoom],
  );
  if (!forecast.data || !panels) return <p className="muted small">{tr("Pas de variables enregistrées pour ce lieu.")}</p>;
  const dg = (v: number) => (Math.abs(v) >= 20 ? v.toFixed(0) : Math.abs(v) >= 2 ? v.toFixed(1) : v.toFixed(2));
  const toggle = (k: number, id: string) =>
    setSel((s) => {
      const n = s.map((x) => new Set(x));
      if (n[k]!.has(id)) n[k]!.delete(id);
      else n[k]!.add(id);
      return n;
    });
  return (
    <>
      <p className="small muted" style={{ margin: "0 0 6px" }}>
        {tr(
          `${place.nom} · ${view === "week" ? "jusqu'à 7 jours de runs principaux collés" : "dernières prévisions"} · dernier run ${forecast.data.run_time.slice(0, 13).replace("T", " ")}Z · nuits seulement`,
        )}
      </p>
      <div className="legend" style={{ marginBottom: 6, alignItems: "center" }}>
        {view === "week" && (
          <span>
            <Sw style={{ width: 16, height: 0, borderTop: "2px solid #cfd6e6" }} />
            {tr("passé (runs principaux collés)")}
          </span>
        )}
        <span>
          <Sw style={{ width: 16, height: 0, borderTop: "2px dashed #cfd6e6" }} />
          {tr("prévu (dernier run)")}
        </span>
        <Seg
          value={view}
          onChange={setView}
          options={[
            ["week", tr("Semaine (7 j max)")],
            ["run", tr("Dernières prévisions")],
          ]}
        />
        <span className="small muted">{tr("Zoom :")}</span>
        <button onClick={() => setZoom((z) => Math.max(1, z / 2))}>−</button>
        <button onClick={() => setZoom((z) => Math.min(16, z * 2))}>+</button>
        <button onClick={() => setZoom(1)}>{tr("tout voir")}</button>
      </div>
      {panels.map((p, k) => (
        <div className="pvrow" key={k}>
          <div style={{ flex: "1 1 auto", minWidth: 0, overflowX: zoom > 1 ? "auto" : "visible" }}>
            <div style={{ width: `${zoom * 100}%` }}>
              <SvgChart html={p.svg} viewBox={`0 0 ${p.W} ${p.H}`} label={`Variables du modèle ${k + 1}`} />
            </div>
          </div>
          <div className="pvlist">
            {PVDEF.filter((q) => PVGRP[k]!.includes(q[0])).map(([id, lab, u, col, real]) => (
              <label key={id}>
                <input type="checkbox" checked={sel[k]!.has(id)} onChange={() => toggle(k, id)} />
                <span className="sw" style={{ background: col }} />
                {tr(lab)}
                {!real && (
                  <span className="muted" title={tr("fictif dans la maquette")}>
                    *
                  </span>
                )}
                {sel[k]!.has(id) && (
                  <span className="rg">
                    {dg(p.ranges[id]![0])}–{dg(p.ranges[id]![1])}
                    {u.trim()}
                  </span>
                )}
              </label>
            ))}
          </div>
        </div>
      ))}
      <p className="small muted" style={{ margin: 0 }}>
        {tr("Variables du modèle AROME au point du lieu : vent et température au-dessus du sol (10 m, 100 m, 500 m), stabilité 10–100 m, cisaillement du jet-stream (6–14 km).")}
      </p>
    </>
  );
}
