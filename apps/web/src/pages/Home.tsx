import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { Link } from "react-router-dom";

import { api, queryKeys } from "../api";
import { SeeingLegend, SeeingValue } from "../components/SeeingBadge";
import { useLatestRunTime, useSiteSummaries, type SiteSummary } from "../lib/hooks";
import { formatDay, formatHour } from "../lib/time";
import { useTimeZone } from "../lib/timezone";

const SiteMap = lazy(() => import("../components/SiteMap"));

export default function Home() {
  const sites = useQuery({ queryKey: queryKeys.sites, queryFn: api.sites });
  const { runTime, query: run } = useLatestRunTime();
  const summaries = useSiteSummaries(sites.data, runTime);
  const sorted = [...summaries].sort(
    (a, b) => (a.tonight?.window?.mean ?? Infinity) - (b.tonight?.window?.mean ?? Infinity),
  );

  return (
    <div className="home">
      <section className="hero">
        <h1>Where will the sky be steady tonight?</h1>
        <p className="muted">
          Forecast astronomical seeing for French observing sites, hour by hour for the next two days.
        </p>
      </section>
      {sites.isError && <div className="panel error">Could not load sites: {String(sites.error)}</div>}
      {run.isError && (
        <div className="panel notice">No successful model run is available yet. Check back after the next AROME cycle.</div>
      )}
      <div className="home-grid">
        <div className="map-panel panel">
          <Suspense fallback={<div className="map-placeholder">Loading map…</div>}>
            <SiteMap summaries={summaries} />
          </Suspense>
          <SeeingLegend />
        </div>
        <ul className="site-list" aria-label="Sites ranked by tonight's best 3-hour window">
          {sites.isLoading && <li className="loading">Loading sites…</li>}
          {sorted.map((s) => (
            <SiteCard key={s.site.slug} summary={s} />
          ))}
        </ul>
      </div>
    </div>
  );
}

function SiteCard({ summary }: { summary: SiteSummary }) {
  const { tz } = useTimeZone();
  const { site, tonight: night, isLoading } = summary;
  const w = night?.window;
  return (
    <li>
      <Link to={`/sites/${site.slug}`} className="site-card panel">
        <div className="site-card-head">
          <h2>{site.name}</h2>
          {site.altitude_m != null && <span className="muted small">{Math.round(site.altitude_m)} m</span>}
        </div>
        {isLoading ? (
          <div className="muted small">Loading forecast…</div>
        ) : night ? (
          <div className="site-card-body">
            <div>
              <div className="label">Best 3 h tonight</div>
              <SeeingValue value={w?.mean} size="lg" />
              {w && (
                <div className="small">
                  {formatDay(w.start, tz)} {formatHour(w.start, tz)}–{formatHour(w.end, tz)}
                </div>
              )}
            </div>
            <div className="site-card-stats">
              <div>
                <div className="label">Best hour</div>
                <strong>{night.best != null ? `${night.best.toFixed(1)}″` : "–"}</strong>
              </div>
              <div>
                <div className="label">Night median</div>
                <strong>{night.median != null ? `${night.median.toFixed(1)}″` : "–"}</strong>
              </div>
            </div>
          </div>
        ) : (
          <div className="muted small">No night-time forecast available.</div>
        )}
      </Link>
    </li>
  );
}
