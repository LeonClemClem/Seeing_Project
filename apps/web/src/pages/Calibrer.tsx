/**
 * Calibrate K with your own seeing measurements. CSV parsing and the K fit run in the browser on the
 * fictitious model until measurement upload and calibration exist on the backend.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";

import { api } from "../api";

import { corrChart } from "../charts/lieuCharts";
import { cn2Svg, corrMock } from "../charts/mockCharts";
import { Cn2RealPanel, DataChips, HistPanel } from "../components/panels";
import { Cn2Legend, LegMed, LegMes, Seg, Sw, SvgChart } from "../components/ui";
import { useUser } from "../data/auth";
import { useSiteHistory } from "../data/forecast";
import { useNavigate } from "react-router-dom";

import { kHidden, selectPlace, TEAM_SITE, useCurrentPlace, usePlaceActions, usePlaces, type Place } from "../data/places";
import { tr } from "../i18n";
import { parseCsv, type CsvOpts, type DateFmt, type NightPt } from "../lib/csv";
import { C_AR, C_DAY, C_LINE, C_OBS, C_OBSD, C_TXT, dnText, fmt, pl, yaxis } from "../lib/util";
import { calib, chourly, comp, cstats, exampleCsv, hourKey, NO_FILTER, seeC, type CalFilters, type CalPair } from "../mock/calibration";
import { nightPointsToIso, nightsFromTimes, seeTerms, termsModel, type Terms } from "../lib/realCalib";
import { KDEF, lieuData } from "../mock/engine";
import { getState, setK, setState, useLangMemo, useUi, type K3 } from "../store";

const OFFSETS = [-12, -11, -10, -9, -8, -7, -6, -5, -4, -3.5, -3, -2, -1, 0, 1, 2, 3, 3.5, 4, 4.5, 5, 5.5, 5.75, 6, 6.5, 7, 8, 9, 9.5, 10, 10.5, 11, 12, 12.75, 13, 14];
const offLabel = (o: number) => {
  const h = Math.trunc(Math.abs(o)),
    m = Math.round((Math.abs(o) - h) * 60);
  return `UTC${o < 0 ? "−" : "+"}${h}${m ? ":" + String(m).padStart(2, "0") : ""}`;
};
const FMTS: [DateFmt, string][] = [
  ["auto", "Détection auto"],
  ["ymd", "AAAA-MM-JJ hh:mm (ISO 8601)"],
  ["dmy", "JJ/MM/AAAA hh:mm"],
  ["mdy", "MM/JJ/AAAA hh:mm (US)"],
  ["ymd2", "AAAA/MM/JJ hh:mm"],
  ["dmyp", "JJ.MM.AAAA hh:mm"],
  ["dmyd", "JJ-MM-AAAA hh:mm"],
  ["dmy2", "JJ/MM/AA hh:mm"],
  ["unix", "Horodatage Unix (secondes)"],
  ["excel", "Date Excel (nombre de jours)"],
];

/* Imported nights survive tab switches, like in the mockup (they add up, without weighting). */
let STORE: { nights: Map<string, NightPt[]>; sel: string | null; ne: number } | null = null;
/* Calibration filters and the nights left out: saved with the place on the server (places the account may
 * calibrate, remembered on every device and login); in this browser only for the example CSV nights. */
const filterKey = (id: string) => `seeing-calib:${id}`;
function loadFilters(id: string): CalFilters {
  try {
    const v = JSON.parse(localStorage.getItem(filterKey(id)) ?? "null") as Partial<CalFilters> | null;
    return v ? { ...NO_FILTER, ...v, out: Array.isArray(v.out) ? v.out.filter((x) => typeof x === "string") : [] } : NO_FILTER;
  } catch {
    return NO_FILTER;
  }
}
function saveFilters(id: string, f: CalFilters) {
  try {
    localStorage.setItem(filterKey(id), JSON.stringify(f));
  } catch {
    /* storage unavailable */
  }
}
const C_RM = "#ff4d4d"; // hours left out of the fit
function initialStore() {
  if (!STORE) {
    STORE = { nights: new Map(), sel: null, ne: 0 };
    for (let k = 0; k < 2; k++) addTo(STORE, exampleCsv(STORE.ne++), { tz: "TU", off: "paris", fmt: "auto" });
  }
  return STORE;
}
function addTo(st: NonNullable<typeof STORE>, txt: string, o: CsvOpts) {
  const r = parseCsv(txt, o);
  if (r.n < 3) return false;
  r.nights.forEach((pts, k) => st.nights.set(k, [...(st.nights.get(k) ?? []), ...pts]));
  st.sel = r.last;
  return true;
}

/** pred(K, i): model seeing at hour index i (0 = 12h UTC) for K, NaN when unknown; K0 = dashed curve. */
function nightSvg(key: string, pts: NightPt[], K: K3, rm: Set<string>, pred: (K: K3, i: number) => number, K0: K3) {
  const idx = [...Array(25).keys()],
    H = chourly(pts),
    P0 = idx.map((i) => pred(K0, i)),
    P1 = idx.map((i) => pred(K, i));
  const W = 700,
    Hh = 220,
    L = 36,
    R = 10,
    T = 8,
    B = 30,
    pw = W - L - R,
    ph = Hh - T - B;
  const ymax = Math.max(3, Math.ceil(Math.max(...[...P0, ...P1].filter((v) => !isNaN(v)), ...H.map((p) => p.m)) * 1.2));
  const X = (x: number) => L + (x * pw) / 24,
    Y = (v: number) => T + ph - (Math.min(v, ymax) / ymax) * ph;
  let g = `<rect x="${X(0)}" y="${T}" width="${X(5.5) - X(0)}" height="${ph}" fill="${C_DAY}"/><rect x="${X(18)}" y="${T}" width="${X(24) - X(18)}" height="${ph}" fill="${C_DAY}"/>`;
  g += yaxis(Y, L, W - R, ymax, ymax > 8 ? 2 : 1) + dnText(X(2.75), T + 13, false) + dnText((X(5.5) + X(18)) / 2, T + 13, true) + dnText(X(21), T + 13, false);
  const nd = new Date(key + "T00:00:00Z");
  nd.setUTCDate(nd.getUTCDate() + 1);
  const lb = String(nd.getUTCDate()).padStart(2, "0") + "/" + String(nd.getUTCMonth() + 1).padStart(2, "0");
  for (let i = 0; i <= 24; i++) {
    const hh = (12 + i) % 24;
    g += `<line x1="${X(i)}" x2="${X(i)}" y1="${T + ph}" y2="${T + ph + 4}" stroke="${C_LINE}"/>`;
    if (hh % 2 === 0)
      g += `<text x="${X(i)}" y="${T + ph + 16}" text-anchor="middle" font-size="11" fill="${hh === 0 ? "#e6ebf6" : C_TXT}" ${hh === 0 ? 'font-weight="500"' : ""}>${hh === 0 ? lb : hh}</text>`;
  }
  const line = (P: number[]) => idx.filter((i) => !isNaN(P[i]!)).map((i) => [X(i), Y(P[i]!)] as [number, number]);
  g += pl(line(P0), `stroke="${C_AR}" stroke-width="1.5" stroke-dasharray="5 4"`);
  g += pl(line(P1), `stroke="${C_AR}" stroke-width="2.2"`);
  pts.forEach((p) => (g += `<circle cx="${X(p.x)}" cy="${Y(p.v)}" r="1.9" fill="${C_OBS}"/>`));
  H.forEach((p) => (g += `<rect x="${X(p.h) - 3.5}" y="${Y(p.m) - 3.5}" width="7" height="7" fill="${rm.has(hourKey(key, p.h)) ? C_RM : C_OBSD}"/>`));
  g += `<text x="${W - R}" y="${Hh - 2}" text-anchor="end" font-size="11" fill="${C_TXT}">${tr("heure TU")}</text>`;
  return g;
}

/** "28/10" of a night key "2026-10-28". */
const ddmmOf = (n: string) => `${n.slice(8, 10)}/${n.slice(5, 7)}`;

export default function Calibrer() {
  const place = useCurrentPlace();
  const role = useUi((s) => s.role);
  const K = useUi((s) => s.K);
  const KCAL = useUi((s) => s.KCAL);
  const kmode = useUi((s) => s.kmode);
  const showObs = useUi((s) => s.showObs);
  const mesf = useUi((s) => s.mesf);
  const lock = kHidden(place, role);
  const { mine } = usePlaces();
  const nav = useNavigate();
  const user = useUser();
  const qc = useQueryClient();
  // Real place the account may calibrate: measurements and model terms come from the API.
  const editable =
    place.real &&
    !!place.slug &&
    !!user &&
    (place.kind === "mine" || user.role === "admin" || (user.role === "team" && place.slug === TEAM_SITE));
  const slug = place.slug ?? "";
  const mq = useQuery({ queryKey: ["measurements", slug], queryFn: () => api.measurements(slug), enabled: editable });
  const srvNights = useMemo(() => (mq.data ? nightsFromTimes(mq.data.times, mq.data.seeing_arcsec) : new Map<string, NightPt[]>()), [mq.data]);
  const srvKeys = [...srvNights.keys()].sort();
  const tq = useQuery({
    queryKey: ["terms", slug, srvKeys[0], srvKeys[srvKeys.length - 1]],
    queryFn: () => {
      const end = new Date(Date.parse(srvKeys[srvKeys.length - 1]! + "T12:00:00Z") + 86400000).toISOString();
      return api.terms(slug, srvKeys[0]! + "T12:00:00Z", end);
    },
    enabled: editable && srvKeys.length > 0,
  });
  const realModel = useMemo(() => (tq.data ? termsModel(tq.data, place.K) : null), [tq.data, place.K]);
  const [selR, setSelR] = useState<string | null>(null);
  const reloadMeasurements = () => qc.invalidateQueries({ queryKey: ["measurements", slug] });

  const [st, setSt] = useState(initialStore);
  const [, bump] = useState(0);
  const [opts, setOpts] = useState<CsvOpts>({ tz: "TU", off: "paris", fmt: "auto" });
  const [err, setErr] = useState("");
  const [drop, setDrop] = useState(false);
  const [saved, setSaved] = useState("");
  const [filters, setFiltersState] = useState(() => loadFilters(place.id));
  const cq = useQuery({ queryKey: ["calib", slug], queryFn: () => api.calib(slug), enabled: editable, staleTime: 60_000 });
  useEffect(() => {
    if (editable) {
      if (cq.data) setFiltersState({ ...NO_FILTER, ...cq.data });
    } else setFiltersState(loadFilters(place.id));
  }, [place.id, editable, cq.data]);
  const setFilters = (f: CalFilters) => {
    setFiltersState(f);
    if (editable)
      api.saveCalib(slug, f).then(
        () => qc.setQueryData(["calib", slug], f),
        (e: Error) => setErr(e.message),
      );
    else saveFilters(place.id, f);
  };
  const outSet = useMemo(() => new Set(filters.out), [filters.out]);
  const selNight = useUi((s) => s.selNight);
  const toggleOut = (n: string) =>
    setFilters({ ...filters, out: filters.out.includes(n) ? filters.out.filter((x) => x !== n) : [...filters.out, n].sort() });
  const fi = useRef<HTMLInputElement>(null);

  const refresh = () => {
    setSt(STORE!);
    bump((n) => n + 1);
  };
  const add = (txt: string, name: string) => {
    if (editable) {
      const r = parseCsv(txt, opts);
      if (r.n < 3)
        return setErr(`${name}${tr(" : moins de 3 mesures lisibles. Vérifie le séparateur, le format de date et l'heure (TU ou locale).")}`);
      api
        .addMeasurements(slug, nightPointsToIso(r.nights))
        .then(() => {
          setErr("");
          setSelR(r.last);
          return reloadMeasurements();
        })
        .catch((e: Error) => setErr(`${name} : ${e.message}`));
      return;
    }
    if (!addTo(st, txt, opts))
      return setErr(`${name}${tr(" : moins de 3 mesures lisibles. Vérifie le séparateur, le format de date et l'heure (TU ou locale).")}`);
    setErr("");
    refresh();
  };
  const readFiles = (fs: FileList | null) =>
    [...(fs ?? [])].forEach((f) => {
      const r = new FileReader();
      r.onload = () => add(String(r.result), f.name);
      r.readAsText(f);
    });
  const example = () => {
    addTo(st, exampleCsv(st.ne++), { tz: "TU", off: "paris", fmt: "auto" });
    refresh();
  };

  const nights = editable ? srvNights : st.nights;
  const nightsKey = (editable ? "srv" : "") + [...nights.entries()].map(([k, v]) => k + v.length).join();
  const cal = useLangMemo(
    () =>
      editable
        ? realModel
          ? calib(nights, filters, realModel)
          : { P: [] as CalPair<Terms>[], K: place.K, mode: srvKeys.length ? "pas encore de prévision pour ces nuits" : "aucune mesure", F: { pics: 0, courtes: 0, top: 0, out: 0, rm: new Set<string>() } }
        : calib(nights, filters),
    [nightsKey, filters, realModel, editable],
  );
  const fnote = [
    filters.pics ? `${cal.F.pics} h peu fournie(s) retirée(s)` : "",
    filters.courtes ? `${cal.F.courtes} nuit(s) courte(s) retirée(s)` : "",
    filters.top ? `${cal.F.top} h au-dessus du modèle retirée(s), puis recalage` : "",
    filters.out.length ? `${cal.F.out} nuit(s) retirée(s) à la main` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const s = editable ? cstats(cal.P as CalPair<Terms>[], K, seeTerms) : cstats(cal.P as CalPair[], K);
  const selKey = editable ? selR : st.sel;
  const night = selKey && nights.has(selKey) ? selKey : editable ? (srvKeys[srvKeys.length - 1] ?? null) : null;
  const cch = useLangMemo(() => {
    if (!night) return "";
    const pred = editable
      ? (k: K3, i: number) => {
          const c = realModel?.comp(night, i);
          return c ? seeTerms(k, c) : NaN;
        }
      : (k: K3, i: number) => seeC(k, comp(night)[i]!);
    return nightSvg(night, nights.get(night)!, K, cal.F.rm, pred, editable ? place.K : KDEF);
  }, [night, nightsKey, K, cal, realModel, editable]);
  const p2c = useLangMemo(() => (place.real ? "" : cn2Svg(K, KCAL, showObs, { mesf }, place.f)), [place, K, KCAL, showObs, mesf]);
  const realHist = useSiteHistory(place);
  const corr = useLangMemo(() => corrMock(K, KCAL, place.f), [K, KCAL, place.f]);
  const hist = useLangMemo(() => (place.real ? realHist : lieuData(place.nom, place.f, K, KCAL)), [place, K, KCAL, realHist]);
  const corrf = useUi((s) => s.corrf);
  const corrR = useLangMemo(() => (realHist ? corrChart(realHist, corrf, selNight, cal.F.rm) : null), [realHist, corrf, selNight, cal]);
  useEffect(() => setSaved(""), [K]);

  const kb = (k: "L" | 0 | 1, f: number) => {
    const n: K3 = [...K];
    if (k === "L") {
      n[0] *= f;
      n[1] *= f;
    } else n[k] *= f;
    setK(n, "M");
  };
  const bt = (v: number) => (v >= 149.99 || v <= 0.0101 ? <span className="pill p-warn">{tr("butée")}</span> : null);
  const krow = (lab: string, k: "L" | 0 | 1) => (
    <div className="kr" key={lab}>
      <span>{tr(lab)}</span>
      <div className="kb">
        {[
          [0.5, "÷2"],
          [0.833, "−"],
          [1.2, "+"],
          [2, "×2"],
        ].map(([f, l]) => (
          <button key={l} onClick={() => kb(k, f as number)}>
            {l}
          </button>
        ))}
      </div>
      <span className="mono">
        {k === "L" ? "" : lock ? "•••" : <>{fmt(K[k])} {bt(K[k])}</>}
      </span>
    </div>
  );

  return (
    <section>
      <h1>{tr("Calibrer avec tes mesures")}</h1>
      <p className="lead">
        {tr("Dépose tes fichiers CSV de seeing (colonnes")} <span className="mono">date ; seeing_arcsec</span>
        {tr(
          ", en TU ou en heure locale). Ils s'ajoutent les uns aux autres, sans pondération. Le calage se fait sur la nuit (17h30–06h TU) : K_TKE et K_CIS calés indépendamment dès les premières mesures. K_conv reste à 0,1.",
        )}
      </p>
      {lock && (
        <div className="panel" style={{ borderColor: "#f2c14e", marginBottom: 14 }}>
          <b>{tr("Site public : résultats de la calibration seulement.")}</b>
          <p className="small muted" style={{ margin: "4px 0 8px" }}>
            {tr(
              "Ce site est calibré par l'administrateur : tu vois les résultats (courbes, Cn², historique, corrélation, qualité du calage), mais les outils de calibration (import CSV, réglage des K, calibration auto) ne fonctionnent que sur tes lieux personnels.",
            )}
          </p>
          <button className="primary" onClick={() => (mine[0] ? setState(selectPlace(mine[0])) : nav("/carte", { state: { newPlace: true } }))}>
            {tr("Passer à mon lieu")}
          </button>
        </div>
      )}
      <div className="grid2" id="calgrid">
        <div className="stack">
          <div id="copts">
            <DataChips id="copts" />
          </div>
          {(!place.real || editable) && (
            <div className="panel">
              {!lock && (
                <>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", margin: "0 0 8px" }}>
                    <span className="small muted">{tr("Heure du fichier :")}</span>
                    <Seg
                      value={opts.tz}
                      onChange={(tz) => setOpts({ ...opts, tz })}
                      options={[
                        ["TU", tr("TU")],
                        ["L", tr("Locale")],
                      ]}
                    />
                    {opts.tz === "L" && (
                      <select
                        aria-label={tr("Fuseau horaire")}
                        value={String(opts.off)}
                        onChange={(e) => setOpts({ ...opts, off: e.target.value === "paris" ? "paris" : +e.target.value })}
                      >
                        <option value="paris">{tr("Europe/Paris (UTC+1, UTC+2 l'été, auto)")}</option>
                        {OFFSETS.map((o) => (
                          <option key={o} value={String(o)}>
                            {offLabel(o)}
                          </option>
                        ))}
                      </select>
                    )}
                    <span className="small muted" style={{ marginLeft: 6 }}>
                      {tr("Format de date :")}
                    </span>
                    <select aria-label={tr("Format de date")} value={opts.fmt} onChange={(e) => setOpts({ ...opts, fmt: e.target.value as DateFmt })}>
                      {FMTS.map(([v, l]) => (
                        <option key={v} value={v}>
                          {tr(l)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div
                    className={"drop" + (drop ? " on" : "")}
                    tabIndex={0}
                    role="button"
                    aria-label={tr("Ajouter un fichier CSV")}
                    onClick={() => fi.current?.click()}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        fi.current?.click();
                      }
                    }}
                    onDragOver={(e: DragEvent) => {
                      e.preventDefault();
                      setDrop(true);
                    }}
                    onDragLeave={() => setDrop(false)}
                    onDrop={(e: DragEvent) => {
                      e.preventDefault();
                      setDrop(false);
                      readFiles(e.dataTransfer.files);
                    }}
                  >
                    <b>{tr("Ajouter un fichier CSV")}</b>
                    <div className="small muted">
                      {tr(
                        "ou dépose-le ici · date et heure dans la 1re colonne (ou date ; heure dans deux colonnes), seeing dans la dernière · séparateur ; , ou tabulation · secondes facultatives",
                      )}
                    </div>
                    <input
                      ref={fi}
                      type="file"
                      accept=".csv,.txt"
                      multiple
                      hidden
                      onChange={(e) => {
                        readFiles(e.target.files);
                        e.target.value = "";
                      }}
                    />
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }} hidden={editable}>
                    <button onClick={example}>{tr("+ Nuit d'exemple")}</button>
                    <button
                      onClick={() => {
                        for (let i = 0; i < 6; i++) addTo(st, exampleCsv(st.ne++), { tz: "TU", off: "paris", fmt: "auto" });
                        refresh();
                      }}
                    >
                      {tr("+ 6 nuits")}
                    </button>
                    <span className="err">{err}</span>
                  </div>
                </>
              )}
              <div style={{ marginTop: 8 }}>
                {editable && <span className="small muted">{tr(mq.isLoading ? "Chargement des mesures…" : "Mesures enregistrées sur le serveur :")} </span>}
                {[...nights.keys()].sort().map((k) => (
                  <span
                    key={k}
                    className={"chip" + (k === night ? " on" : "")}
                    tabIndex={0}
                    onClick={() => {
                      if (editable) return setSelR(k);
                      st.sel = k;
                      refresh();
                    }}
                  >
                    <span style={outSet.has(k) ? { textDecoration: "line-through", color: "#ff8a7a" } : undefined}>
                      {tr(`Nuit du ${k.slice(8)}/${k.slice(5, 7)}`)} · {nights.get(k)!.length} pts
                    </span>{" "}
                    {/* never a real deletion: the night is only left out of the calibration, and can be put back */}
                    <span
                      role="button"
                      aria-label={tr(outSet.has(k) ? "Remettre cette nuit dans le calage" : "Retirer cette nuit du calage")}
                      title={tr(outSet.has(k) ? "Remettre cette nuit dans le calage" : "Retirer cette nuit du calage (les mesures restent enregistrées)")}
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleOut(k);
                      }}
                    >
                      {outSet.has(k) ? "↺" : "✕"}
                    </span>
                  </span>
                ))}
              </div>
              <div
                id="calfilt"
                style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", borderTop: "1px solid var(--line)", paddingTop: 6, marginTop: 6 }}
              >
                <span className="small muted">{tr("Filtres du calage :")}</span>
                {(
                  [
                    ["pics", "pics peu fournis", "heures dont la médiane repose sur beaucoup moins de mesures que d'habitude"],
                    ["courtes", "nuits < 3 h successives", "nuits sans au moins 3 heures comparées successives"],
                  ] as const
                ).map(([k, lab, title]) => (
                  <span
                    key={k}
                    className={"chip" + (filters[k] ? " on" : "")}
                    role="switch"
                    aria-checked={filters[k]}
                    tabIndex={0}
                    title={tr(title)}
                    onClick={() => setFilters({ ...filters, [k]: !filters[k] })}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setFilters({ ...filters, [k]: !filters[k] });
                      }
                    }}
                  >
                    {tr(lab)}
                  </span>
                ))}
                <span className="small muted" style={{ marginLeft: 4 }}>
                  {tr("heures au-dessus du modèle :")}
                </span>
                <Seg
                  value={filters.top}
                  onChange={(top) => setFilters({ ...filters, top })}
                  options={[
                    [0, "0"],
                    [1, "1 %"],
                    [5, "5 %"],
                    [10, "10 %"],
                  ]}
                />
                <span className="small muted">{tr(fnote)}</span>
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginTop: 6 }}>
                <span className="small muted">{tr("Nuits retirées :")}</span>
                {selNight && (
                  <button className="small" onClick={() => toggleOut(selNight)}>
                    {tr(outSet.has(selNight) ? `remettre la nuit du ${ddmmOf(selNight)}` : `retirer la nuit du ${ddmmOf(selNight)}`)}
                  </button>
                )}
                {filters.out.map((n) => (
                  <span key={n} className="chip on" title={tr("Remettre cette nuit dans le calage")} onClick={() => toggleOut(n)} style={{ cursor: "pointer" }}>
                    {ddmmOf(n)} ✕
                  </span>
                ))}
                {!filters.out.length && !selNight && (
                  <span className="small muted">{tr("aucune · clique sur une nuit de l'historique pour pouvoir la retirer")}</span>
                )}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
                <span>{tr("Mode : " + cal.mode)}</span>
                <span className="mono">{tr(`${cal.P.length} h de nuit comparées`)}</span>
              </div>
              <div className="legend">
                <span>
                  <Sw style={{ width: 16, borderTop: "2px dashed var(--arome)" }} />
                  {tr(editable ? "K en service" : "K par défaut (voisins)")}
                </span>
                <span>
                  <Sw style={{ width: 16, height: 3, background: "var(--arome)" }} />
                  {tr("K du lieu")}
                </span>
                <LegMes />
                <LegMed />
                {cal.F.rm.size > 0 && (
                  <span>
                    <Sw style={{ width: 8, height: 8, background: C_RM }} />
                    {tr("heure retirée du calage")}
                  </span>
                )}
              </div>
              <SvgChart html={cch} viewBox="0 0 700 220" label="Nuit sélectionnée" />
            </div>
          )}
          <div className="panel">
            <h2>{tr("Cn² (altitude × temps)")}</h2>
            <Cn2Legend obs={showObs} />
            {place.real ? <Cn2RealPanel place={place} profile={false} /> : <SvgChart html={p2c} viewBox="0 0 900 270" label="Panneau Cn2 de calibration" />}
          </div>
          <div className="panel">
            <h2>{tr("Historique (prévisions avec les K en service et mesures, nuit)")}</h2>
            {hist ? (
              <HistPanel data={hist} OB={showObs || place.real} inset={false} rm={cal.F.rm} />
            ) : (
              <SvgChart
                html={`<text x="550" y="120" text-anchor="middle" font-size="13" fill="${C_TXT}">${tr("Historique : choisis un lieu avec seeing monitor.")}</text>`}
                viewBox="0 0 1100 240"
                label="Historique du lieu"
              />
            )}
          </div>
          <div className="panel grid2" style={{ gridTemplateColumns: "minmax(0,1.2fr) minmax(0,1fr)" }}>
            <div>
              <h2>{tr("Corrélation prévu / mesuré")}</h2>
              {place.real && corrR ? (
                <>
                  <p className="small muted mono">{corrR.ct}</p>
                  <SvgChart html={corrR.svg} viewBox="0 0 340 320" label="Corrélation" />
                </>
              ) : place.real ? (
                <SvgChart
                  html={`<text x="170" y="150" text-anchor="middle" font-size="12" fill="${C_TXT}">${tr("Corrélation : choisis un lieu avec seeing monitor.")}</text>`}
                  viewBox="0 0 340 300"
                  label="Corrélation"
                />
              ) : (
                <>
                  <p className="small muted mono">{corr.ct}</p>
                  <SvgChart html={corr.svg} viewBox="0 0 340 300" label="Corrélation" />
                </>
              )}
            </div>
            <div className="stack" style={{ alignContent: "start", paddingTop: 26 }}>
              <div className="legend" style={{ flexDirection: "column", gap: 5 }}>
                <span>
                  <Sw style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--night)", border: "1px solid #fff" }} />
                  {tr("médiane horaire (nuit)")}
                </span>
                <span>
                  <Sw style={{ width: 12, height: 12, borderRadius: "50%", border: "2px solid var(--night)" }} />
                  {tr("☾ médiane d'une nuit")}
                </span>
                <span>
                  <Sw style={{ width: 16, borderTop: "1px dashed var(--muted)" }} />
                  {tr("Prévu = mesuré")}
                </span>
              </div>
              <div className="tiles">
                <div className="tile">
                  <div className="l">{tr("r nuit")}</div>
                  <div className="v">{place.real ? (corrR?.tiles.rn ?? "–") : corr.rDayNight}</div>
                </div>
                <div className="tile">
                  <div className="l">{tr("Biais · écart moyen")}</div>
                  <div className="v" style={{ fontSize: 16 }}>
                    {place.real ? (corrR?.tiles.rj ?? "–") : corr.bias}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="stack side">
          <KPanel place={place} lock={lock} autoK={cal.K} stats={s} kmode={kmode} saved={saved} setSaved={setSaved} krow={krow} />
        </div>
      </div>
    </section>
  );
}

function KPanel(p: {
  place: Place;
  lock: boolean;
  autoK: K3;
  stats: { r: number; b: number; q: number };
  kmode: "A" | "M";
  saved: string;
  setSaved: (s: string) => void;
  krow: (lab: string, k: "L" | 0 | 1) => JSX.Element;
}) {
  const K = useUi((s) => s.K);
  const { r, b, q } = p.stats;
  const { update } = usePlaceActions();
  const save = () => {
    const done = tr(`Enregistré : K_TKE = ${fmt(K[0])}, K_CIS = ${fmt(K[1])}, K_conv = 0.1.`);
    if (p.place.kind !== "mine" || !p.place.real || !p.place.slug) return p.setSaved(done);
    update.mutate(
      { slug: p.place.slug, k_tke: K[0], k_cis: K[1], k_conv: 0.1 },
      { onSuccess: () => p.setSaved(done + tr(" Utilisés dès le prochain run.")), onError: (e) => p.setSaved(e.message) },
    );
  };
  return (
    <div className="panel" id="kpanel">
      <h2 style={{ margin: "0 0 8px" }}>{tr("Réglage des coefficients")}</h2>
      {!p.lock && (
        <>
          <button
            className="primary"
            style={{ width: "100%", justifyContent: "center", flexDirection: "column", gap: 2, marginBottom: 4 }}
            onClick={() => {
              setState({ KCAL: [...p.autoK] });
              setK(p.autoK, "A");
            }}
          >
            {tr("Calibration auto")}
            <span className="small mono" style={{ fontWeight: 400 }}>
              K_TKE {fmt(p.autoK[0])} · K_CIS {fmt(p.autoK[1])}
            </span>
          </button>
          <Seg
            style={{ marginBottom: 8 }}
            value={p.kmode}
            onChange={(m) => {
              if (m === "A") setK(getState().KCAL, "A");
              else setState({ kmode: "M" });
            }}
            options={[
              ["A", tr("K calés")],
              ["M", tr("Manuel")],
            ]}
          />
          <div id="kbox2">
            <div className="krows">
              {p.krow("Niveau (les deux)", "L")}
              {p.krow("Couche limite · K_TKE", 0)}
              {p.krow("Cisaillement · K_CIS", 1)}
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 8 }}>
              <button onClick={save}>
                {tr("Enregistrer pour ce lieu")}
              </button>
              <span className="small muted">{tr("K_conv figé")}</span>
              <span className="okmsg">{p.saved}</span>
            </div>
          </div>
        </>
      )}
      <div className="res" style={{ borderTop: "1px solid var(--line)", marginTop: 10, paddingTop: 10 }}>
        <h2>{tr("Résultat du calage")}</h2>
        <div className="tiles">
          <div className="tile">
            <div className="l">{tr("r (nuits)")}</div>
            <div className="v">{isNaN(r) || p.place.real ? "–" : r.toFixed(2)}</div>
          </div>
          <div className="tile">
            <div className="l">{tr("Biais")}</div>
            <div className="v">{isNaN(b) || p.place.real ? "–" : (b >= 0 ? "+" : "") + b.toFixed(2) + '"'}</div>
          </div>
          <div className="tile">
            <div className="l">{tr("Précision horaire")}</div>
            <div className="v">{isNaN(q) || p.place.real ? "–" : "± " + q.toFixed(2) + '"'}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
