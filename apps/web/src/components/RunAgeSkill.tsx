/** "Error with the age of the run" panel (Prévision, under the correlation; Calibrer, with the K being set). */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api";
import { skillSvg, type SkillMode } from "../charts/lieuCharts";
import type { Place } from "../data/places";
import { tr } from "../i18n";
import { C_AR } from "../lib/util";
import { useLangMemo, type K3 } from "../store";
import { Seg, Sw, SvgChart } from "./ui";
import { useLoading } from "../lib/useLoading";

/** Panel under the correlation: signed error (forecast - measured) with the age of the run, hourly and/or by night,
 * every run that forecast the hour recomputed with the place's current K (hours with integrals only). Default width:
 * the correlation panel's; the corner handle resizes it. `K` (Calibrer): the K being
 * set, so that the panel follows every new calibration. */
export function RunAgeSkill({ place, K, flush }: { place: Place; K?: K3; flush?: boolean }) {
  const slug = place.slug ?? "";
  const q = useQuery({
    queryKey: ["skill", slug, K ? `${K[0]}|${K[1]}` : "site"],
    queryFn: () => api.skill(slug, K ? [K[0], K[1]] : undefined),
    enabled: place.real && !!slug,
    retry: false,
    staleTime: 30 * 60 * 1000,
    placeholderData: (prev) => prev, // keep the curves while the next K are computed
  });
  const [mode, setMode] = useState<SkillMode>("deux");
  const svg = useLangMemo(() => (q.data?.bins.length ? skillSvg(q.data.bins, q.data.nights, mode) : ""), [q.data, mode]);
  const ld = useLoading(place.real && !!slug && q.isLoading);
  if (ld.show)
    return (
      <div className="panel" style={{ width: "100%", marginTop: flush ? 0 : 12 }}>
        <h2 style={{ fontSize: 14 }}>{tr("Erreur selon l'âge du run (prévu − mesuré)")}</h2>
        {ld.spinner}
      </div>
    );
  if (!svg) return null;
  const hourly = mode !== "nuit",
    nightly = mode !== "horaire";
  return (
    <div className="panel" style={{ width: "100%", minWidth: 220, maxWidth: "100%", marginTop: flush ? 0 : 12, resize: "horizontal", overflow: "hidden" }}>
      <h2 style={{ fontSize: 14 }}>{tr("Erreur selon l'âge du run (prévu − mesuré)")}</h2>
      <Seg<SkillMode>
        value={mode}
        onChange={setMode}
        label={tr("Erreur affichée")}
        style={{ margin: "0 0 6px" }}
        options={[
          ["horaire", tr("horaire")],
          ["nuit", tr("nocturne")],
          ["deux", tr("les deux")],
        ]}
      />
      <div className="legend" style={{ gap: "2px 8px" }}>
        {hourly && (
          <span>
            <Sw style={{ width: 16, borderTop: `2px solid ${C_AR}` }} />
            {tr("horaire : moyenne de chaque heure d'âge")}
          </span>
        )}
        {nightly && (
          <span>
            <Sw style={{ width: 16, borderTop: "2px dashed #f1efe8" }} />
            {tr("nocturne : médianes de la nuit, par classes de 6 h d'âge (à 00h TU)")}
          </span>
        )}
        <span>
          {hourly && <Sw style={{ width: 16, height: 8, background: C_AR, opacity: 0.3 }} />}
          {nightly && <Sw style={{ width: 16, height: 8, background: "#f1efe8", opacity: 0.2 }} />}
          {tr("± 1 écart type")}
        </span>
      </div>
      <SvgChart html={svg} viewBox="0 0 200 200" label="Erreur selon l'âge du run" style={{ width: "100%", display: "block" }} />
    </div>
  );
}
