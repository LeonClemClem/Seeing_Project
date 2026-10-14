import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api, queryKeys } from "../api";
import { relativeAge, runLabel } from "../lib/time";
import { useTimeZone } from "../lib/timezone";

export default function Header() {
  const { tz, setTz } = useTimeZone();
  const me = useQuery({ queryKey: queryKeys.me, queryFn: api.me, staleTime: Infinity });
  const run = useQuery({ queryKey: queryKeys.latestRun, queryFn: api.latestRun });

  return (
    <header className="header">
      <Link to="/" className="brand">
        <img src="/favicon.svg" alt="" width={26} height={26} />
        <span>Seeing the Sky</span>
      </Link>
      {me.data && me.data.env !== "prod" && <span className="badge env">{me.data.env}</span>}
      <div className="header-run" title={run.data ? `Run ${run.data.run_time}` : undefined}>
        {run.data ? (
          <>
            AROME run {runLabel(run.data.run_time)}, <span className="muted">{relativeAge(run.data.run_time)}</span>
          </>
        ) : run.isError ? (
          <span className="muted">No forecast yet</span>
        ) : null}
      </div>
      <div className="header-right">
        <div className="seg" role="group" aria-label="Time zone">
          <button aria-pressed={tz === "Europe/Paris"} onClick={() => setTz("Europe/Paris")}>
            Paris
          </button>
          <button aria-pressed={tz === "UTC"} onClick={() => setTz("UTC")}>
            UTC
          </button>
        </div>
        {me.data?.email && (
          <span className="email" title={me.data.email}>
            {me.data.email}
          </span>
        )}
      </div>
    </header>
  );
}
