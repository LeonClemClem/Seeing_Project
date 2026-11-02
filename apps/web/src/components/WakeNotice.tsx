/** Message with the spinner while the server wakes up: Cloud Run stops it when nobody uses the site (no instance kept
 * on), and the first requests then wait for it to start. Shown when a request is still running after WAKE_MS and
 * nothing came back for IDLE_MS (or since the page opened). */
import { useIsFetching } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { tr } from "../i18n";

const WAKE_MS = 2500;
const IDLE_MS = 10 * 60 * 1000;

export default function WakeNotice() {
  const busy = useIsFetching() > 0;
  const lastDone = useRef(0); // 0: the page just opened
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (!busy) {
      lastDone.current = Date.now();
      setShow(false);
      return;
    }
    if (Date.now() - lastDone.current < IDLE_MS) return; // the server answered a moment ago: awake
    const t = setTimeout(() => setShow(true), WAKE_MS);
    return () => clearTimeout(t);
  }, [busy]);
  if (!show) return null;
  return (
    <div className="wake" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {tr("Le serveur se réveille (il s'endort quand personne ne s'en sert) : encore quelques secondes…")}
    </div>
  );
}
