/**
 * Personal places (mock), public sites (API) and community places (mock, blurred positions):
 * measurement histogram, AROME cells around the place, history, correlation and Cn².
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { corrChart, histSvg, mailleSvg, seeHist } from "../charts/lieuCharts";
import { cn2Svg } from "../charts/mockCharts";
import { Cn2RealPanel, HistPanel } from "../components/panels";
import { Chip, Cn2Legend, LegBreak, LegDay, LegMed, LegMes, Sw, SvgChart } from "../components/ui";
import { useSiteHistory } from "../data/forecast";
import { kHidden, kTxt, MAX_PLACES, MOCK_PLACES, usePlaceActions, usePlaces, type Place } from "../data/places";
import { tr } from "../i18n";
import { C_TXT, ddmm, fmt, pd } from "../lib/util";
import { lieuData } from "../mock/engine";
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
  const l = sel.t === "lx" ? (all.find((p) => p.id === sel.id) ?? mine[0] ?? pub[0] ?? MOCK_PLACES[0]!) : null;
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

      <PlaceDetail l={l!} />

      <div className="tiles" style={{ marginTop: 16 }}>
        <div className="tile">
          <div className="l">Fisheye</div>
          <div className="v" style={{ fontSize: 15 }}>
            {tr("1 par jour · utilisé")}
          </div>
          <div className="small muted">{tr("remise à zéro à 00h TU")}</div>
        </div>
        <div className="tile">
          <div className="l">{tr("Demandes hors domaine AROME")}</div>
          <div className="v" style={{ fontSize: 15 }}>
            {tr("file d'attente")}
          </div>
          <div className="small muted">{tr("1 en cours")}</div>
        </div>
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
  const data = useLangMemo(() => (l.real ? (real ?? null) : lieuData(l.nom, l.f, l.K, l.K)), [l, real]);
  const histo = useLangMemo(() => {
    const v = data ? seeHist(data) : [];
    return { ...histSvg(v, 460, 220, false), v };
  }, [data]);
  const maille = useLangMemo(() => mailleSvg(tr(l.nom), l.lat, l.lon, l.alt), [l]);
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
              : tr("Pas de mesure de nuit.")}
          </p>
          {histo.n ? <SvgChart html={histo.svg} viewBox="0 0 460 220" label="Histogramme du seeing enregistré" /> : none("Pas de mesure de nuit.", "0 0 460 220", 230, 110)}
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
        {data ? <HistPanel data={data} OB={true} inset={false} /> : none("Pas de période avec prévision et mesures pour ce lieu.", "0 0 1100 240", 550, 120)}
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
          {corr ? <SvgChart html={corr.svg} viewBox="0 0 340 320" label="Corrélation du lieu" /> : none("Pas d'heure de nuit comparée.", "0 0 340 320", 170, 160)}
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
          <Cn2Legend obs={!l.real} convective={!l.real} seeLabel="Seeing prévu (axe droit)" />
          {l.real ? <Cn2RealPanel place={l} profile={false} /> : <SvgChart html={cn2} viewBox="0 0 900 270" label="Panneau Cn2 du lieu" />}
        </div>
      </div>
    </div>
  );
}
