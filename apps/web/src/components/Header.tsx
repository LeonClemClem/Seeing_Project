import { Link, NavLink, useLocation } from "react-router-dom";

import { useMe, useSyncRole } from "../data/auth";
import { kHidden, selectPlace, useCurrentPlace, usePlaces } from "../data/places";
import { tr } from "../i18n";
import { useLatestRunTime } from "../lib/hooks";
import { fmt, pad2, runLabel } from "../lib/util";
import { setState, useUi } from "../store";

const TABS: [path: string, label: string][] = [
  ["/carte", "Carte"],
  ["/prevision", "Prévision"],
  ["/fisheye", "Fisheye"],
  ["/calibrer", "Calibrer"],
  ["/lieux", "Mes lieux"],
  ["/compte", "Compte"],
  ["/tutoriel", "Tutoriel"],
  ["/a-propos", "À propos"],
  ["/seeing-monitor", "Besoin d'un seeing monitor ?"],
];

/** Two letters from a display name ("Ada Lovelace" → "AL") or an e-mail ("ada.l@x" → "AL"). */
const initials = (name: string | null | undefined, email: string | null | undefined) => {
  const parts = (name?.trim() ? name.trim().split(/\s+/) : (email ?? "").split("@")[0]!.split(/[._-]+/)).filter(Boolean);
  if (!parts.length) return "–";
  return ((parts[0]![0] ?? "") + (parts[1]?.[0] ?? parts[0]![1] ?? "")).toUpperCase();
};

export default function Header() {
  const lang = useUi((s) => s.lang);
  const role = useUi((s) => s.role);
  const K = useUi((s) => s.K);
  const kmode = useUi((s) => s.kmode);
  const { pub, sh, mine, all } = usePlaces();
  const place = useCurrentPlace();
  const me = useMe();
  useSyncRole();
  const user = me.data?.user ?? null;
  const { runTime } = useLatestRunTime();
  const loc = useLocation();

  const runMs = runTime ? Date.parse(runTime) : null;
  const realView = loc.pathname.startsWith("/prevision") && place.real;
  const hid = kHidden(place, role);

  return (
    <header>
      <div className="bar">
        <div className="brand">
          <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="10" fill="none" stroke="#4f9be8" strokeWidth="1.6" />
            <path d="M4 14c3-2 5 2 8 0s5 2 8 0" fill="none" stroke="#f2a23a" strokeWidth="1.6" />
            <circle cx="12" cy="8" r="1.6" fill="#e6ebf6" />
          </svg>
          Seeing AROME
        </div>
        <nav role="tablist" aria-label={tr("Pages")}>
          {TABS.map(([path, label]) => (
            <NavLink key={path} to={path} className="tab" role="tab">
              {tr(label)}
            </NavLink>
          ))}
        </nav>
        <div className="who">
          <select
            aria-label={tr("Lieu affiché")}
            value={place.id}
            onChange={(e) => {
              const p = all.find((q) => q.id === e.target.value);
              if (p) setState(selectPlace(p));
            }}
          >
            {pub.length > 0 && (
              <optgroup label={tr("Lieux publics")}>
                {pub.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nom}
                  </option>
                ))}
              </optgroup>
            )}
            {sh.length > 0 && (
              <optgroup label={tr("Partagés par la communauté")}>
                {sh.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nom}
                  </option>
                ))}
              </optgroup>
            )}
            <optgroup label={tr("Mes lieux")}>
              {mine.map((p) => (
                <option key={p.id} value={p.id}>
                  {tr(p.nom)}
                </option>
              ))}
            </optgroup>
          </select>
          <button
            aria-label={lang === "en" ? "Passer en français" : "Switch to English"}
            style={{ padding: "4px 9px", fontWeight: 600 }}
            onClick={() => setState({ lang: lang === "en" ? "fr" : "en" })}
          >
            {lang === "en" ? "FR" : "EN"}
          </button>
          <Link
            to="/compte"
            className="av"
            style={{ color: "inherit", textDecoration: "none", ...(user ? { borderColor: "var(--arome)" } : {}) }}
            title={user ? `${user.display_name ?? user.email} · ${tr("Compte")}` : tr("Se connecter")}
          >
            {user ? initials(user.display_name, user.email) : initials(null, me.data?.email)}
          </Link>
        </div>
      </div>
      <div className="strip">
        <span>
          {tr("Modèle")} <b>AROME V2bd</b> <span className="muted">{tr("(autres modèles à venir)")}</span>
        </span>
        <span>
          Run <b className="mono">{runMs ? runLabel(runMs) : "–"}</b>
          {tr(" · run principal")}
        </span>
        <span>
          {tr("Prochain run principal")} <b className="mono">{runMs ? pad2(new Date(runMs + 6 * 3600000).getUTCHours()) + "Z" : "–"}</b>
        </span>
        <span>
          {tr("K du lieu")}{" "}
          <b className="mono">
            {tr(hid ? "confidentiels" : `${fmt(K[0])} / ${fmt(K[1])} / ${fmt(K[2])} · ${kmode === "A" ? "calés" : "manuels"}`)}
          </b>
        </span>
        {realView ? (
          <span className="pill p-ok">{tr("Données réelles")} · AROME</span>
        ) : (
          <span className="pill p-warn">{tr("Maquette : données fictives")}</span>
        )}
      </div>
    </header>
  );
}
