/** Administrator tab: the K and exact position of every site and the K history; more information will be
 * added here. No e-mail: a member is only "compte n°<id>". */
import { useQuery } from "@tanstack/react-query";

import { api } from "../api";
import { useUser } from "../data/auth";
import { tr } from "../i18n";
import { fmt } from "../lib/util";
import { useLoading } from "../lib/useLoading";
import { Fragment, useState } from "react";

const when = (t: string | null) => (t ? new Date(t).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" }) : "–");

export default function Admin() {
  const user = useUser();
  const isAdmin = user?.role === "admin";
  const q = useQuery({ queryKey: ["admin-overview"], queryFn: () => api.adminOverview(), enabled: isAdmin, retry: false });
  const ld = useLoading(q.isLoading);
  /** Account whose places are unrolled under its row. */
  const [open, setOpen] = useState<string | null>(null);
  if (!isAdmin)
    return (
      <section className="wrap">
        <div className="panel">
          <p className="muted">{tr("Réservé à l'administrateur.")}</p>
        </div>
      </section>
    );
  if (ld.show) return ld.spinner;
  if (!q.data) return <p className="muted">{q.error?.message ?? ""}</p>;
  const name = new Map(q.data.sites.map((s) => [s.slug, s.name]));
  const accounts = q.data.accounts ?? [];
  return (
    <section className="wrap">
      <div className="panel">
        <h2>{tr("Comptes")}</h2>
        <p className="small muted">{tr("Clique sur un compte pour voir ses lieux. Jamais d'e-mail : un membre est un numéro de compte.")}</p>
        <div style={{ overflowX: "auto" }}>
          <table className="list">
            <thead>
              <tr>
                <th>{tr("Compte")}</th>
                <th>{tr("Nom affiché")}</th>
                <th>{tr("Rôle")}</th>
                <th>{tr("Lieux")}</th>
                <th>{tr("Créé le")}</th>
                <th>{tr("Dernière connexion")}</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => {
                const places = q.data!.sites.filter((s) => s.owner === a.label);
                const isOpen = open === a.label;
                return (
                  <Fragment key={a.label}>
                    <tr
                      onClick={() => setOpen(isOpen ? null : a.label)}
                      style={{ cursor: "pointer", ...(a.active ? {} : { opacity: 0.5 }) }}
                      aria-expanded={isOpen}
                    >
                      <td>
                        <span className="mono small" aria-hidden="true">
                          {isOpen ? "▾" : "▸"}{" "}
                        </span>
                        {a.label}
                        {!a.active && <span className="small muted"> ({tr("supprimé")})</span>}
                      </td>
                      <td>{a.display_name ?? "–"}</td>
                      <td className="small">
                        {tr(({ user: "membre", team: "équipe", admin: "administrateur" } as Record<string, string>)[a.role] ?? a.role)}
                        {!a.verified && <span className="muted"> · {tr("e-mail non confirmé")}</span>}
                      </td>
                      <td className="mono">
                        {places.filter((s) => s.active).length}
                        {places.some((s) => !s.active) && <span className="small muted"> (+{places.filter((s) => !s.active).length} {tr("archivé(s)")})</span>}
                      </td>
                      <td className="mono small">{when(a.created_at)}</td>
                      <td className="mono small">{when(a.last_login_at)}</td>
                    </tr>
                    {isOpen && (
                      <tr>
                        <td colSpan={6} style={{ padding: 0 }}>
                          <div className="acc-sites">
                            {places.length ? (
                              <table className="list">
                                <tbody>
                                  {places.map((s) => (
                                    <tr key={s.slug} style={s.active ? undefined : { opacity: 0.5 }}>
                                      <td>
                                        {s.name}
                                        {!s.active && <span className="small muted"> ({tr("archivé")})</span>}
                                      </td>
                                      <td className="mono small">
                                        {s.lat.toFixed(5)}, {s.lon.toFixed(5)}
                                        {s.altitude_m != null && ` · ${Math.round(s.altitude_m)} m`}
                                      </td>
                                      <td className="mono small">
                                        K1 {fmt(s.k_tke)} · K2 {fmt(s.k_cis)}
                                      </td>
                                      <td className="mono small">{when(s.k_saved_at)}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            ) : (
                              <p className="small muted" style={{ margin: 0 }}>
                                {tr("Aucun lieu.")}
                              </p>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      <div className="panel">
        <h2>{tr("Sites : K en service")}</h2>
        <div style={{ overflowX: "auto" }}>
          <table className="list">
            <thead>
              <tr>
                <th>{tr("Lieu")}</th>
                <th>{tr("Propriétaire")}</th>
                <th>{tr("Coordonnées")}</th>
                <th>K1</th>
                <th>K2</th>
                <th>K_conv</th>
                <th>{tr("Enregistrés le")}</th>
              </tr>
            </thead>
            <tbody>
              {q.data.sites.map((s) => (
                <tr key={s.slug} style={s.active ? undefined : { opacity: 0.5 }}>
                  <td>
                    {s.name}
                    {!s.active && <span className="small muted"> ({tr("archivé")})</span>}
                  </td>
                  <td className="small">{s.owner ?? tr("site public")}</td>
                  <td className="mono small">
                    {s.lat.toFixed(5)}, {s.lon.toFixed(5)}
                    {s.altitude_m != null && ` · ${Math.round(s.altitude_m)} m`}
                  </td>
                  <td className="mono">{fmt(s.k_tke)}</td>
                  <td className="mono">{fmt(s.k_cis)}</td>
                  <td className="mono">{fmt(s.k_conv)}</td>
                  <td className="mono small">{when(s.k_saved_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="panel">
        <h2>{tr("Historique des K (tous les sites)")}</h2>
        <p className="small muted">{tr("Chaque enregistrement est gardé ; « Restaurer » se fait dans Calibrer, pour le lieu choisi.")}</p>
        <div style={{ overflowX: "auto" }}>
          <table className="list">
            <thead>
              <tr>
                <th>{tr("Date")}</th>
                <th>{tr("Lieu")}</th>
                <th>K1</th>
                <th>K2</th>
                <th>K_conv</th>
                <th>{tr("Origine")}</th>
                <th>{tr("Par")}</th>
              </tr>
            </thead>
            <tbody>
              {q.data.k_history.map((k) => (
                <tr key={k.id}>
                  <td className="mono small">{when(k.saved_at)}</td>
                  <td>{name.get(k.site) ?? k.site}</td>
                  <td className="mono">{fmt(k.k_tke)}</td>
                  <td className="mono">{fmt(k.k_cis)}</td>
                  <td className="mono">{fmt(k.k_conv)}</td>
                  <td className="small">{tr(k.source)}</td>
                  <td className="small">{k.by ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
