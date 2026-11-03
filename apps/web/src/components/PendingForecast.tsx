/** Notice of a panel of a place created since the latest run: its forecasts come with the next computed run. */
import { tr } from "../i18n";
import { useRunUpdates } from "../lib/hooks";
import { hhmm } from "../lib/util";

export function PendingForecast({ pad = 40 }: { pad?: number }) {
  const { next } = useRunUpdates();
  const h = next != null ? Math.round((next - Date.now()) / 3600000) : null;
  return (
    <div className="pending" style={{ margin: `${pad}px auto` }}>
      {tr("Prévisions pas encore calculées pour ce lieu : elles le seront au prochain run AROME")}
      {next != null
        ? `, ${tr("vers")} ${hhmm(next)} TU (${h! < 1 ? tr("dans moins d'une heure") : `${tr("dans environ")} ${h} h`}).`
        : `, ${tr("dès que Météo-France l'aura publié.")}`}
      <div className="small">{tr("Une amélioration à venir donnera les prévisions dès la création du lieu.")}</div>
    </div>
  );
}
