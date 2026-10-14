import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, ApiError, queryKeys, type ForecastPoint } from "../api";
import Cn2Heatmap from "../components/Cn2Heatmap";
import { SeeingLegend, SeeingValue } from "../components/SeeingBadge";
import SeeingChart from "../components/SeeingChart";
import { useLatestRunTime, useNow } from "../lib/hooks";
import { nightIntervals, r0cm, seeingColor, tonight } from "../lib/seeing";
import { formatDay, formatHour, tzLabel } from "../lib/time";
import { useTimeZone } from "../lib/timezone";

function useCompact(query = "(max-width: 640px)") {
  const [match, setMatch] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMatch(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);
  return match;
}

export default function SitePage() {
  const { slug = "" } = useParams();
  const { tz } = useTimeZone();
  const now = useNow();
  const compact = useCompact();
  const [fullHeight, setFullHeight] = useState(false);
  const { runTime, query: run } = useLatestRunTime();
  const runKey = runTime ?? "latest";

  const forecast = useQuery({
    queryKey: queryKeys.forecast(slug, runKey),
    queryFn: () => api.forecast(slug, runKey),
    enabled: !!runTime,
  });
  const cn2 = useQuery({
    queryKey: queryKeys.cn2(slug, runKey),
    queryFn: () => api.cn2(slug, runKey),
    enabled: !!runTime,
  });

  const site = forecast.data?.site;
  const points = useMemo(() => forecast.data?.points ?? [], [forecast.data]);
  const nights = useMemo(() => {
    if (!site || points.length === 0) return [];
    const ts = points.map((p) => Date.parse(p.valid_time));
    return nightIntervals(site.lat, site.lon, Math.min(...ts), Math.max(...ts) + 3_600_000);
  }, [site, points]);
  const nowTick = Math.floor(now / 600_000) * 600_000;
  const night = useMemo(
    () => (site ? tonight(points, site.lat, site.lon, nowTick) : null),
    [site, points, nowTick],
  );

  useEffect(() => {
    document.title = site ? `${site.name} · Seeing the Sky` : "Seeing the Sky";
  }, [site]);

  if (run.isError) {
    return <div className="panel notice">No successful model run is available yet.</div>;
  }
  if (forecast.error instanceof ApiError && forecast.error.status === 404) {
    return (
      <div className="panel empty">
        <h1>Unknown site</h1>
        <p className="muted">No site called “{slug}”.</p>
        <Link to="/">Back to the map</Link>
      </div>
    );
  }
  if (forecast.isError) return <div className="panel error">Could not load the forecast: {String(forecast.error)}</div>;
  if (!forecast.data || !site) return <div className="loading">Loading forecast…</div>;

  const w = night?.window;
  const wPoints = w?.points ?? [];
  const avg = (vals: (number | null)[]) => {
    const v = vals.filter((x): x is number => x != null);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  };
  const wR0 = r0cm(avg(wPoints.map((p) => p.r0_m)));
  const wBl = avg(wPoints.map((p) => p.h_coulim_m));

  return (
    <div className="site-page">
      <div className="site-head">
        <Link to="/" className="back">
          ← All sites
        </Link>
        <h1>{site.name}</h1>
        <p className="muted">
          {site.lat.toFixed(3)}°N, {site.lon.toFixed(3)}°E
          {site.altitude_m != null && <> · {Math.round(site.altitude_m)} m</>} · times in {tzLabel(tz)}
        </p>
      </div>

      <section className="panel summary" aria-label="Tonight">
        <div className="summary-main">
          <div className="label">Best 3 h tonight</div>
          <SeeingValue value={w?.mean} size="lg" />
          <div>{w ? `${formatDay(w.start, tz)} ${formatHour(w.start, tz)}–${formatHour(w.end, tz)}` : "No complete window"}</div>
        </div>
        <dl className="summary-stats">
          <div>
            <dt>r0 (best window)</dt>
            <dd>{wR0 != null ? `${wR0.toFixed(1)} cm` : "–"}</dd>
          </div>
          <div>
            <dt>Boundary layer</dt>
            <dd>{wBl != null ? `${Math.round(wBl)} m` : "–"}</dd>
          </div>
          <div>
            <dt>Night best / median</dt>
            <dd>
              {night?.best != null ? `${night.best.toFixed(1)}″` : "–"} / {night?.median != null ? `${night.median.toFixed(1)}″` : "–"}
            </dd>
          </div>
          <div>
            <dt>Astronomical night</dt>
            <dd>{night ? `${formatHour(night.night.start, tz)}–${formatHour(night.night.end, tz)}` : "–"}</dd>
          </div>
        </dl>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Seeing forecast</h2>
          <SeeingLegend />
        </div>
        {points.length ? (
          <SeeingChart points={points} nights={nights} now={now} tz={tz} best={w ?? null} compact={compact} />
        ) : (
          <div className="empty muted">No forecast for this site in the latest run.</div>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>
            Turbulence profile <span className="muted">(Cn²)</span>
          </h2>
          <div className="seg" role="group" aria-label="Height range">
            <button aria-pressed={!fullHeight} onClick={() => setFullHeight(false)}>
              0–4 km
            </button>
            <button aria-pressed={fullHeight} onClick={() => setFullHeight(true)}>
              Full
            </button>
          </div>
        </div>
        <p className="muted small">
          Dark is calm air, bright is turbulent. The dashed line is the boundary-layer height. Turbulence near the ground
          and around the jet stream (≈9–12 km) degrades the image.
        </p>
        {cn2.data && cn2.data.valid_times.length ? (
          <Cn2Heatmap cn2={cn2.data} points={points} full={fullHeight} now={now} tz={tz} compact={compact} />
        ) : cn2.isLoading ? (
          <div className="loading">Loading profile…</div>
        ) : (
          <div className="empty muted">No turbulence profile available.</div>
        )}
      </section>

      {night && night.points.length > 0 && <NightTable points={night.points} bestStart={w?.start} />}
    </div>
  );
}

function NightTable({ points, bestStart }: { points: ForecastPoint[]; bestStart?: number }) {
  const { tz } = useTimeZone();
  const bestEnd = bestStart != null ? bestStart + 3 * 3_600_000 : undefined;
  return (
    <section className="panel">
      <h2>Tonight, hour by hour</h2>
      <div className="table-wrap">
        <table className="hours">
          <thead>
            <tr>
              <th scope="col">Time</th>
              <th scope="col">Seeing</th>
              <th scope="col">r0</th>
              <th scope="col">Boundary layer</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => {
              const t = Date.parse(p.valid_time);
              const inBest = bestStart != null && bestEnd != null && t >= bestStart && t < bestEnd;
              const r0 = r0cm(p.r0_m);
              return (
                <tr key={p.lead_hour} className={inBest ? "best" : undefined}>
                  <td>
                    {formatDay(t, tz)} {formatHour(t, tz)}
                  </td>
                  <td>
                    <span className="dot" style={{ background: seeingColor(p.seeing_arcsec) }} aria-hidden />
                    {p.seeing_arcsec != null ? `${p.seeing_arcsec.toFixed(2)}″` : "–"}
                  </td>
                  <td>{r0 != null ? `${r0.toFixed(1)} cm` : "–"}</td>
                  <td>{p.h_coulim_m != null ? `${Math.round(p.h_coulim_m)} m` : "–"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
