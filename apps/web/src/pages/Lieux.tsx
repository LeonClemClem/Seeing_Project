/**
 * Personal places (mock), public sites (API) and community places (mock, blurred positions):
 * measurement histogram, AROME cells around the place, history, correlation and Cn².
 */
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { corrChart, histSvg, mailleSvg, roseBest, seeHist, windRoseSvg, type RosePt } from "../charts/lieuCharts";
import { cn2Svg } from "../charts/mockCharts";
import { Cn2RealPanel, HistPanel } from "../components/panels";
import { api, queryKeys } from "../api";
import { Chip, Cn2Legend, ColorBar, LegBreak, LegDay, LegMed, LegMes, Seg, Spinner, Sw, SvgChart } from "../components/ui";
import { usePlaceLoading, useSiteHistory } from "../data/forecast";
import { kHidden, kTxt, MAX_PLACES, useCurrentPlace, usePlaceActions, usePlaces, type Place } from "../data/places";
import { tr } from "../i18n";
import { C_TXT, ddmm, fmt, pd, turboGradient } from "../lib/util";
import { lieuData, type LieuData } from "../mock/engine";
import { setState, useLangMemo, useUi } from "../store";

type Sel = { t: "lx"; id: string };

export default function Lieux() {
  const { pub, sh, mine } = usePlaces();
  const { remove } = usePlaceActions();
  const current = useUi((s) => s.place);
  const mesf = useUi((s) => s.mesf);
  const nav = useNavigate();
  const [sel, setSel] = useState<Sel>({ t: "lx", id: current });
  const [open, setOpen] = useState({ pub: false, sh: false });

  const all = [...mine, ...pub, ...sh];
  const cur = useCurrentPlace();
  const l = all.find((p) => p.id === sel.id) ?? mine[0] ?? pub[0] ?? cur;
  const toggleM = (k: "brut" | "horaire" | "courbe") => setState((s) => ({ mesf: { ...s.mesf, [k]: !s.mesf[k] } }));

  const tile = (on: boolean, key: string, onClick: () => void, body: JSX.Element) => (
    <button
      key={key}
      className="tile"
      onClick={onClick}
      style={{ textAlign: "left", display: "block", border: `1px solid ${on ? "var(--arome)" : "var(--line)"}`, background: on ? "#173257" : "var(--panel2)" }}
    >
      {body}
    </button>
  );

  return (
    <section>
      <h1>{tr("Mes lieux")}</h1>
      <p className="lead">
        {tr(
          "Tes lieux personnels : historique des prévisions et des mesures, corrélation et panneau Cn². Tu peux aussi consulter les sites publics et les lieux partagés par la communauté (lecture seule, K confidentiels).",
        )}{" "}
        <b>{tr("Données réelles")}</b> {tr("pour les sites publics (prévisions AROME V2bd du dernier run), contrairement au reste de la maquette.")}
      </p>
      <h2 style={{ marginTop: 6 }}>{tr("Mes lieux personnels")}</h2>
      <div className="panel">
        <div className="tablewrap">
          <table className="list">
            <thead>
              <tr>
                <th>{tr("Lieu")}</th>
                <th>{tr("Visibilité")}</th>
                <th>{tr("Mesures")}</th>
                <th>{tr("K (TKE / CIS)")}</th>
                <th>{tr("Prévision")}</th>
              </tr>
            </thead>
            <tbody>
              {!mine.length && (
                <tr>
                  <td colSpan={5} className="muted">
                    {tr("Aucun lieu pour l'instant : ajoute-le depuis la carte.")}
                  </td>
                </tr>
              )}
              {mine.map((p) => (
                <tr
                  key={p.id}
                  style={{ cursor: "pointer", background: sel.t === "lx" && sel.id === p.id ? "#173257" : undefined }}
                  title={tr("Afficher les panneaux de ce lieu")}
                  onClick={() => setSel({ t: "lx", id: p.id })}
                >
                  <td>
                    <b style={{ fontWeight: 500 }}>{tr(p.nom)}</b>
                    <div className="small muted mono">
                      {p.lat.toFixed(3)} N · {p.lon.toFixed(3)} E
                    </div>
                  </td>
                  <td>
                    <span className={"pill " + (p.vis === "privé" ? "p-mut" : "p-acc")}>{tr(p.vis ?? "")}</span>
                  </td>
                  <td className={p.mesures ? undefined : "muted"}>{p.mesures ? tr(p.mesures) : tr("aucune")}</td>
                  <td className="mono">
                    {fmt(p.K[0])} / {fmt(p.K[1])}{" "}
                    <span
                      className={"pill " + (p.kSrc === "indépendants" ? "p-pro" : p.kSrc === "facteur" ? "p-acc" : "p-mut")}
                      style={{ fontFamily: "var(--f-body)" }}
                    >
                      {tr(p.kSrc ?? "")}
                    </span>
                  </td>
                  <td>
                    <span className={"pill " + (p.prev?.startsWith("hors") ? "p-warn" : "p-ok")}>{tr(p.real ? "AROME, chaque run" : (p.prev ?? ""))}</span>
                    {p.real && p.slug && (
                      <button
                        className="small"
                        style={{ marginLeft: 8 }}
                        aria-label={tr("Supprimer ce lieu")}
                        title={tr("Supprimer ce lieu")}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (window.confirm(tr(`Supprimer « ${p.nom} » et ses prévisions ?`))) remove.mutate(p.slug!);
                        }}
                      >
                        ✕
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ marginTop: 12 }}>
          <button className="primary" onClick={() => nav("/carte", { state: { newPlace: true } })}>
            {tr("Ajouter un lieu")}
          </button>{" "}
          <span className="small muted">{tr(`${mine.length} lieux sur ${MAX_PLACES}`)}</span>
        </div>
      </div>

      <details
        open={open.pub}
        onToggle={(e) => setOpen({ ...open, pub: (e.target as HTMLDetailsElement).open })}
        style={{ marginTop: 10, border: "1px solid var(--line)", borderRadius: 10, padding: "8px 12px", background: "var(--panel)" }}
      >
        <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 14 }}>
          {tr("Sites publics (consultation)")} <span className="small muted">({pub.length})</span>
        </summary>
        <div className="tiles" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))", marginTop: 6 }}>
          {pub.map((p) =>
            tile(
              sel.t === "lx" && sel.id === p.id,
              p.id,
              () => setSel({ t: "lx", id: p.id }),
              <>
                <div style={{ fontWeight: 500 }}>{p.nom}</div>
                <div className="small muted mono">
                  {p.lat.toFixed(3)} N · {p.lon.toFixed(3)} E
                </div>
                <div className="small" style={{ marginTop: 4 }}>
                  {p.alt != null ? `${Math.round(p.alt)} m` : "–"}
                </div>
                <div className="small muted">{tr("prévisions du dernier run · pas de mesures")}</div>
              </>,
            ),
          )}
        </div>
      </details>
      <details
        open={open.sh}
        onToggle={(e) => setOpen({ ...open, sh: (e.target as HTMLDetailsElement).open })}
        style={{ marginTop: 10, border: "1px solid var(--line)", borderRadius: 10, padding: "8px 12px", background: "var(--panel)" }}
      >
        <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 14 }}>
          {tr("Partagés par la communauté")} <span className="small muted">({sh.length})</span>
        </summary>
        <div className="tiles" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))", marginTop: 6 }}>
          {!sh.length && (
            <div style={{ gridColumn: "1/-1" }} className="small muted">
              {tr("Aucun lieu partagé pour l'instant.")}
            </div>
          )}
          {sh.map((p) =>
            tile(
              sel.t === "lx" && sel.id === p.id,
              p.id,
              () => setSel({ t: "lx", id: p.id }),
              <>
                <div style={{ fontWeight: 500 }}>{p.nom}</div>
                <div className="small muted mono">
                  {p.lat.toFixed(3)} N · {p.lon.toFixed(3)} E
                </div>
                <div className="small" style={{ marginTop: 4 }}>
                  {p.alt != null ? `${Math.round(p.alt)} m` : "–"}
                </div>
                <div className="small muted">{tr("prévisions du dernier run · pas de mesures")}</div>
              </>,
            ),
          )}
        </div>
      </details>

      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
        <span className="small muted">{tr("Nuit seulement (17h30–06h TU)")}</span>
        <span style={{ width: 12 }} />
        <span className="small muted">{tr("Mesures :")}</span>
        <Chip on={mesf.brut} onToggle={() => toggleM("brut")}>
          {tr("brutes")}
        </Chip>
        <Chip on={mesf.horaire} onToggle={() => toggleM("horaire")}>
          {tr("médianes horaires")}
        </Chip>
        <Chip on={mesf.courbe} onToggle={() => toggleM("courbe")}>
          {tr("courbe médiane horaire")}
        </Chip>
      </div>

      <PlaceDetail l={l} />

      <div className="tiles" style={{ marginTop: 16 }}>
        <div className="tile">
          <div className="l">{tr("Recalcul")}</div>
          <div className="v" style={{ fontSize: 15 }}>
            {tr("chaque run principal")}
          </div>
          <div className="small muted">00Z · 06Z · 12Z · 18Z</div>
        </div>
      </div>
    </section>
  );
}

function PlaceDetail({ l }: { l: Place }) {
  const role = useUi((s) => s.role);
  const corrf = useUi((s) => s.corrf);
  const mesf = useUi((s) => s.mesf);
  const hid = kHidden(l, role);
  const real = useSiteHistory(l);
  const placeLoading = usePlaceLoading(l);
  const loading = l.real && !real && placeLoading;
  const data = useLangMemo(() => (l.real ? (real ?? null) : lieuData(l.nom, l.f, l.K, l.K)), [l, real]);
  const histo = useLangMemo(() => {
    const v = data ? seeHist(data) : [];
    return { ...histSvg(v, 460, 220, false), v };
  }, [data]);
  const maille = useLangMemo(() => mailleSvg(tr(l.nom), l.lat, l.lon, l.alt, l.cells), [l]);
  const corr = useLangMemo(() => (data ? corrChart(data, corrf) : null), [data, corrf]);
  const cn2 = useLangMemo(() => (l.real ? "" : cn2Svg(l.K, l.K, true, { mesf }, l.f)), [l, mesf]);
  const first = data?.episodes[0],
    lastE = data?.episodes[data.episodes.length - 1];
  const toggleC = (k: "horaire" | "nuit" | "brut") => setState((s) => ({ corrf: { ...s.corrf, [k]: !s.corrf[k] } }));
  const none = (t: string, vb: string, x: number, y: number) => (
    <SvgChart html={`<text x="${x}" y="${y}" text-anchor="middle" font-size="13" fill="${C_TXT}">${tr(t)}</text>`} viewBox={vb} label={t} />
  );

  return (
    <div className="stack" style={{ marginTop: 16 }}>
      <div className="grid2" style={{ gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", alignItems: "start" }}>
        <div className="panel">
          <h2>{tr("Histogramme du seeing enregistré")}</h2>
          <p className="small muted mono" style={{ margin: "0 0 4px" }}>
            {histo.n
              ? tr(
                  `${histo.n.toLocaleString("fr-FR")} mesures de nuit · médiane ${histo.md.toFixed(2)}″ · quartiles ${histo.q1.toFixed(2)}–${histo.q3.toFixed(2)}″ · courbe : loi log-normale ajustée (médiane ${Math.exp(histo.mu).toFixed(2)}″, σ ${histo.sg.toFixed(2)})`,
                )
              : loading
                ? ""
                : tr("Pas de mesure de nuit.")}
          </p>
          {histo.n ? (
            <SvgChart html={histo.svg} viewBox="0 0 460 220" label="Histogramme du seeing enregistré" />
          ) : loading ? (
            <Spinner />
          ) : (
            none("Pas de mesure de nuit.", "0 0 460 220", 230, 110)
          )}
        </div>
        <div className="panel">
          <h2>{tr("Mailles AROME autour du lieu")}</h2>
          <p className="small muted" style={{ margin: "0 0 4px" }}>
            {maille.caption}
          </p>
          <SvgChart html={maille.svg} viewBox="0 0 520 420" label="Schéma des mailles AROME autour du lieu" />
        </div>
      </div>
      <div className="panel">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
          <h2>
            {tr("Historique")} · {tr(l.nom)}
            {l.kind === "pub" ? tr(l.shared ? " (partagé par la communauté)" : " (site public)") : ""}
          </h2>
          <span className="small muted mono">
            {tr(kTxt(l.K, hid, fmt))}
            {first && lastE ? tr(` · mesures du ${ddmm(pd(first.a))} au ${ddmm(pd(lastE.b))}`) : ""}
          </span>
        </div>
        <div className="legend">
          <span>
            <Sw style={{ width: 16, height: 3, background: "var(--arome)" }} />
            AROME V2bd
          </span>
          <LegMes />
          <LegMed />
          <LegDay />
          <LegBreak />
        </div>
        {data ? <HistPanel data={data} OB={true} inset={false} /> : loading ? <Spinner /> : none("Pas de période avec prévision et mesures pour ce lieu.", "0 0 1100 240", 550, 120)}
      </div>
      <div className="grid2" style={{ gridTemplateColumns: "minmax(0,1fr) minmax(0,1.6fr)" }}>
        <div className="panel">
          <h2>{tr("Corrélation prévu / mesuré")}</h2>
          <p className="small muted mono" style={{ margin: "0 0 2px" }}>
            {corr?.ct ?? "–"}
          </p>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", margin: "2px 0 6px" }}>
            <span className="small muted">{tr("Afficher :")}</span>
            <Chip on={corrf.horaire} onToggle={() => toggleC("horaire")}>
              {tr("médianes horaires")}
            </Chip>
            <Chip on={corrf.nuit} onToggle={() => toggleC("nuit")}>
              {tr("☾ médianes nocturnes")}
            </Chip>
            <Chip on={corrf.brut} onToggle={() => toggleC("brut")}>
              {tr("données brutes")}
            </Chip>
          </div>
          {corr ? <SvgChart html={corr.svg} viewBox="0 0 340 320" label="Corrélation du lieu" /> : loading ? <Spinner /> : none("Pas d'heure de nuit comparée.", "0 0 340 320", 170, 160)}
          <div className="legend">
            <span>
              <Sw style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--night)", border: "1px solid #fff" }} />
              {tr("médiane horaire (nuit)")}
            </span>
            <span>
              <Sw style={{ width: 12, height: 12, borderRadius: "50%", border: "2px solid var(--night)" }} />
              {tr("☾ médiane d'une nuit")}
            </span>
          </div>
          <div className="tiles" style={{ marginTop: 8 }}>
            <div className="tile">
              <div className="l">{tr("r nuit")}</div>
              <div className="v">{corr?.tiles.rn ?? "–"}</div>
              <div className="small muted">{corr?.tiles.nn}</div>
            </div>
            <div className="tile">
              <div className="l">{tr("biais nuit")}</div>
              <div className="v">{corr?.tiles.rj ?? "–"}</div>
              <div className="small muted">{corr?.tiles.nj}</div>
            </div>
          </div>
        </div>
        <div className="panel">
          <h2>{tr("Cn² (altitude × temps)")}</h2>
          <Cn2Legend obs seeLabel="Seeing prévu (axe droit)" />
          {l.real ? <Cn2RealPanel place={l} profile={false} /> : <SvgChart html={cn2} viewBox="0 0 900 270" label="Panneau Cn2 du lieu" />}
        </div>
      </div>
      {l.real && data && <WindRoses place={l} data={data} />}
    </div>
  );
}

/* ---------- wind roses: AROME wind of the hour vs the night measurements, cumulated night after night ---------- */

/** Levels of the wind roses: [key of the forecast variables (speed u…, direction d…), label]. */
const ROSE_LEVELS: [string, string][] = [
  ["10", "10 m au-dessus du sol"],
  ["100", "100 m au-dessus du sol"],
  ["500", "500 m au-dessus du sol"],
  ["700h", "700 hPa (~3 km)"],
  ["500h", "500 hPa (~5,5 km)"],
  ["250h", "250 hPa (jet stream)"],
];
type RoseColour = "mes" | "err" | "prev";

function WindRoses({ place, data }: { place: Place; data: LieuData }) {
  const slug = place.slug ?? "";
  // same query as the site history (cached): every main run stitched, with the model variables of each hour
  const fq = useQuery({
    queryKey: queryKeys.forecast(slug, "latest", "all"),
    queryFn: () => api.forecast(slug, "latest", "all"),
    enabled: !!slug,
    retry: false,
    staleTime: 10 * 60 * 1000,
  });
  const [levels, setLevels] = useState(["10", "700h", "250h"]);
  const [colour, setColour] = useState<RoseColour>("mes");
  // night hours with a measured median and the AROME wind of that hour
  const hours = useMemo(() => {
    const vars = new Map((fq.data?.points ?? []).map((p) => [Date.parse(p.valid_time), p.variables ?? null]));
    return data.paires
      .filter((q): q is [string, number, number, boolean] => q[3] && q[1] != null && q[2] != null)
      .map(([t, prev, mes]) => ({ t: Date.parse(t.length <= 16 ? t + ":00Z" : t), prev, mes, v: vars.get(Date.parse(t.length <= 16 ? t + ":00Z" : t)) }))
      .filter((h): h is { t: number; prev: number; mes: number; v: Record<string, number | null> } => !!h.v);
  }, [data, fq.data]);
  const valOf = (h: (typeof hours)[number]) =>
    colour === "mes" ? h.mes : colour === "prev" ? h.prev : 100 * (Math.exp(Math.abs(Math.log(h.prev / h.mes))) - 1);
  const vals = hours.map(valOf).sort((a, b) => a - b);
  const lo = vals.length ? vals[Math.floor(vals.length * 0.05)]! : 0,
    hi = vals.length ? vals[Math.min(vals.length - 1, Math.floor(vals.length * 0.95))]! : 1;
  const unit = colour === "err" ? " %" : "″";
  const nights = new Set(hours.map((h) => new Date(h.t - 12 * 3600000).toISOString().slice(0, 10))).size;

  return (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <h2>{tr("Vent AROME et seeing")}</h2>
        <span className="small muted mono">
          {hours.length
            ? tr(`${hours.length} h de nuit · ${nights} nuit(s) cumulée(s) · du ${ddmm(new Date(hours[0]!.t))} au ${ddmm(new Date(hours[hours.length - 1]!.t))}`)
            : ""}
        </span>
      </div>
      <p className="small muted" style={{ margin: "0 0 6px" }}>
        {tr(
          "Chaque point = une heure de nuit avec mesure : direction d'où vient le vent AROME, distance au centre = sa force. Les nuits s'ajoutent au fil des runs.",
        )}
      </p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", margin: "0 0 8px" }}>
        <span className="small muted">{tr("Couleur :")}</span>
        <Seg<RoseColour>
          value={colour}
          onChange={setColour}
          options={[
            ["mes", tr("seeing mesuré")],
            ["err", tr("erreur de la prévision")],
            ["prev", tr("seeing prévu")],
          ]}
        />
      </div>
      {fq.isLoading ? (
        <Spinner />
      ) : !hours.length ? (
        <p className="muted" style={{ textAlign: "center", padding: "30px 0" }}>
          {tr("Pas encore d'heure de nuit avec mesure et vent AROME pour ce lieu : les données s'accumulent à chaque nuit.")}
        </p>
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(230px,1fr))", gap: 12 }}>
            {levels.map((lv, k) => {
              const pts: RosePt[] = hours
                .map((h) => ({ dir: h.v[`d${lv}`] ?? NaN, speed: h.v[`u${lv}`] ?? NaN, val: valOf(h) }))
                .filter((q) => isFinite(q.dir) && isFinite(q.speed) && isFinite(q.val));
              const best = roseBest(pts);
              return (
                <div key={k} style={{ minWidth: 0 }}>
                  <select
                    aria-label={tr("Niveau du vent")}
                    value={lv}
                    onChange={(e) => setLevels(levels.map((x, i) => (i === k ? e.target.value : x)))}
                    style={{ width: "100%" }}
                  >
                    {ROSE_LEVELS.map(([v, lab]) => (
                      <option key={v} value={v}>
                        {tr(lab)}
                      </option>
                    ))}
                  </select>
                  <p className="small mono" style={{ margin: "4px 0 0", textAlign: "center", color: "#e6ebf6" }}>
                    {best ? `${tr("meilleur secteur :")} ${tr(best.sect)} (${best.med.toFixed(colour === "err" ? 0 : 2)}${unit}, ${best.n} h)` : tr("pas de secteur avec 5 h")}
                  </p>
                  {pts.length ? (
                    <SvgChart html={windRoseSvg(pts, lo, hi)} viewBox="0 0 300 300" label={`Rose des vents ${levelLabel(lv)}`} />
                  ) : (
                    <p className="muted small" style={{ textAlign: "center", padding: "60px 0" }}>
                      {tr("Pas de vent AROME à ce niveau.")}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
          <ColorBar
            left={`${lo.toFixed(colour === "err" ? 0 : 2)}${unit}`}
            right={`${hi.toFixed(colour === "err" ? 0 : 2)}${unit}`}
            gradient={turboGradient()}
          />
          <p className="small muted" style={{ margin: "4px 0 0", textAlign: "center" }}>
            {tr(colour === "mes" ? "seeing mesuré (médiane horaire)" : colour === "prev" ? "seeing prévu AROME V2bd" : "erreur |prévu / mesuré|")} ·{" "}
            {tr("couleurs entre les centiles 5 et 95 · meilleur secteur = médiane la plus basse sur au moins 5 h")}
          </p>
        </>
      )}
    </div>
  );
}

const levelLabel = (lv: string) => ROSE_LEVELS.find((q) => q[0] === lv)?.[1] ?? lv;
