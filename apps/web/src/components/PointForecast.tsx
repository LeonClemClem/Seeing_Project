/**
 * One-off forecast at coordinates (above the map): the seeing of the global maps of the latest run at that point
 * (nights only, map K). "Voir la prévision" makes the point the place shown in every tab (Prévision, Fisheye) until
 * another place is chosen; it can then be saved as a place.
 */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { api, type Forecast } from "../api";
import { prevRealSvg } from "../charts/realCharts";
import { pointPlace, selectPlace, type Place } from "../data/places";
import { tr } from "../i18n";
import { parseCoord } from "../lib/geo";
import { setState, useLangMemo, useUi } from "../store";
import { SvgChart } from "./ui";
import { useLoading } from "../lib/useLoading";

/** Seeing forecast of the global maps at a point, with its coordinates, AROME ground height and run. */
export function PointSeeing({ lat, lon }: { lat: number; lon: number }) {
  const mesf = useUi((s) => s.mesf);
  const q = useQuery({
    queryKey: ["point", lat.toFixed(4), lon.toFixed(4)],
    queryFn: () => api.point(lat, lon),
    retry: false,
  });
  const svg = useLangMemo(() => {
    if (!q.data) return "";
    // the forecast curve of the sites, fed with the map values of the point
    const fc = {
      run_time: q.data.run_time,
      points: q.data.points.map((p) => ({ ...p, r0_m: null, integral_cn2: null, h_coulim_m: null })),
    } as unknown as Forecast;
    return prevRealSvg(fc, "", undefined, [], mesf);
  }, [q.data, mesf]);
  const ld = useLoading(q.isLoading);
  if (ld.show) return ld.spinner;
  if (q.isError || !q.data)
    return (
      <p className="muted" style={{ textAlign: "center", padding: "20px 0" }}>
        {tr("Pas de prévision ici : point hors du domaine AROME, ou carte du run pas encore calculée.")}
      </p>
    );
  return (
    <>
      <p className="small mono" style={{ margin: "8px 0 2px" }}>
        {lat.toFixed(4)} N · {lon.toFixed(4)} E
        {q.data.ground_m != null ? ` · ${tr("sol AROME")} ${q.data.ground_m} m` : ""} · run {q.data.run_time.slice(0, 13).replace("T", " ")}Z
      </p>
      <SvgChart html={svg} viewBox="0 0 900 220" label="Seeing prévu au point" />
    </>
  );
}

/** Panel above the map: coordinates, "Voir la prévision", the forecast, and "Enregistrer comme lieu". `pick`: the
 * point last clicked on the map, written into the coordinate fields. */
/** `saveForm`: the form to save the point as a place (name, sharing), shown in the panel once asked for. */
export function PointForm({ onSave, pick, saveForm }: { onSave: (lat: number, lon: number) => void; pick?: [number, number] | null; saveForm?: ReactNode }) {
  const point = useUi((s) => s.point);
  const [txt, setTxt] = useState(() => ({ lat: point ? point.lat.toFixed(4) : "", lon: point ? point.lon.toFixed(4) : "" }));
  const [err, setErr] = useState("");
  useEffect(() => {
    if (pick) {
      setTxt({ lat: pick[0].toFixed(4), lon: pick[1].toFixed(4) });
      setErr("");
    }
  }, [pick]);
  const go = (e: FormEvent) => {
    e.preventDefault();
    const la = parseCoord(txt.lat, true),
      lo = parseCoord(txt.lon, false);
    if (la == null || lo == null) return setErr("Coordonnées invalides : par ex. 44.18 et 5.47, ou 44°11'N et 5°28'E.");
    setErr("");
    setState({ point: { lat: la, lon: lo }, ...selectPlace(pointPlace(la, lo)) });
  };
  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <h2 style={{ margin: 0 }}>{tr("Prévision ponctuelle à des coordonnées")}</h2>
      <p className="small muted" style={{ margin: "6px 0" }}>
        {tr(
          "Seeing lu sur la carte globale du dernier run (mailles de ~2,5 km, calibration de la carte, nuits seulement), sans créer de lieu. Le point devient le lieu affiché dans les autres onglets ; pour le Cn², l'historique et la calibration, enregistre-le comme lieu.",
        )}
      </p>
      <form onSubmit={go} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input aria-label={tr("Latitude")} placeholder={tr("latitude (44.18)")} value={txt.lat} onChange={(e) => setTxt({ ...txt, lat: e.target.value })} style={{ width: 150 }} />
        <input aria-label={tr("Longitude")} placeholder={tr("longitude (5.47)")} value={txt.lon} onChange={(e) => setTxt({ ...txt, lon: e.target.value })} style={{ width: 150 }} />
        <button className="primary" type="submit">
          {tr("Voir la prévision")}
        </button>
        {point && (
          <button type="button" className="small" onClick={() => onSave(point.lat, point.lon)}>
            {tr("Enregistrer comme lieu")}
          </button>
        )}
      </form>
      {err && <p className="err">{tr(err)}</p>}
      {saveForm}
      {point && (
        <>
          <PointSeeing lat={point.lat} lon={point.lon} />
          <p className="small muted" style={{ margin: "4px 0 0" }}>
            {tr("Le point est aussi affiché dans")} <Link to="/prevision">{tr("Prévision")}</Link> {tr("et")} <Link to="/fisheye">{tr("Fisheye")}</Link>.
          </p>
        </>
      )}
    </div>
  );
}

/** What a point of the map cannot show (no stored forecast, no measurements, no K to fit). */
export function PointNotice({ place, text }: { place: Place; text: string }) {
  return (
    <p className="muted" style={{ textAlign: "center", padding: "16px 0" }}>
      {tr(text)}{" "}
      <Link to="/carte" state={{ newPlace: true, lat: place.lat, lon: place.lon }}>
        {tr("Enregistrer ce point comme lieu")}
      </Link>
    </p>
  );
}
