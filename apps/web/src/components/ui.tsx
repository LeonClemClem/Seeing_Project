/** Small presentational pieces reused across views (chips, segmented buttons, SVG-string charts, legends). */
import type { CSSProperties, KeyboardEvent, ReactNode } from "react";

import { tr } from "../i18n";

export function Chip(props: { on: boolean; onToggle: () => void; children: ReactNode; title?: string; style?: CSSProperties }) {
  const key = (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      props.onToggle();
    }
  };
  return (
    <span
      className={"chip" + (props.on ? " on" : "")}
      role="switch"
      aria-checked={props.on}
      tabIndex={0}
      title={props.title}
      style={props.style}
      onClick={props.onToggle}
      onKeyDown={key}
    >
      {props.children}
    </span>
  );
}

export function Seg<V extends string | number>(props: {
  value: V;
  options: [V, ReactNode][];
  onChange: (v: V) => void;
  label?: string;
  style?: CSSProperties;
}) {
  return (
    <div className="seg" role="group" aria-label={props.label} style={props.style}>
      {props.options.map(([v, lab]) => (
        <button key={String(v)} className={v === props.value ? "on" : undefined} onClick={() => props.onChange(v)}>
          {lab}
        </button>
      ))}
    </div>
  );
}

/** Render an SVG chart built as a string of SVG elements. */
export function SvgChart(props: { html: string; viewBox: string; label: string; style?: CSSProperties; className?: string }) {
  return (
    <svg
      viewBox={props.viewBox}
      role="img"
      aria-label={tr(props.label)}
      style={props.style}
      className={props.className}
      dangerouslySetInnerHTML={{ __html: props.html }}
    />
  );
}

/* ---------- legend swatches ---------- */
/** Turning ring while a panel's data loads. */
export function Spinner({ label = "Chargement…", style }: { label?: string; style?: CSSProperties }) {
  return (
    <div className="spin-wrap" role="status" aria-live="polite" style={style}>
      <span className="spinner" aria-hidden="true" />
      {tr(label)}
    </div>
  );
}

export const Sw = ({ style }: { style: CSSProperties }) => <span className="sw" style={style} />;

export const LegArome = ({ label = "AROME V2bd" }: { label?: string }) => (
  <span>
    <Sw style={{ width: 16, height: 3, background: "var(--arome)" }} />
    {tr(label)}
  </span>
);
export const LegMes = () => (
  <span>
    <Sw style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--obs)" }} />
    {tr("Mesures")}
  </span>
);
export const LegMed = () => (
  <span>
    <Sw style={{ width: 8, height: 8, background: "var(--obs-d)" }} />
    {tr("Médiane horaire")}
  </span>
);
export const LegDay = () => (
  <span>
    <Sw style={{ width: 12, height: 10, background: "#253c6b" }} />
    {tr("Jour 06h–17h30 TU (nuit en sombre)")}
  </span>
);
export const LegBreak = () => (
  <>
    <span className="mono">||</span>
    <span>{tr("coupure entre épisodes")}</span>
  </>
);

export function Cn2Legend({ obs = true, convective = true, hcoulim = false, seeLabel = "Seeing V2bd (axe droit)" }) {
  return (
    <div className="legend">
      <span>
        <Sw style={{ width: 18, height: 4, background: "#1f6bff", outline: "1.5px solid #fff" }} />
        {tr(seeLabel)}
      </span>
      {obs && (
        <span>
          <Sw style={{ width: 5, height: 5, borderRadius: "50%", background: "#fff", border: "1px solid #000" }} />
          {tr("Seeing mesuré")}{" "}
          <Sw style={{ width: 14, height: 2, background: "#fff", outline: "1px solid #000", marginLeft: 4 }} />
          {tr("médiane horaire")}
        </span>
      )}
      <span>
        <Sw style={{ width: 18, height: 3, background: "#ff2bd6", outline: "1.5px solid #000" }} />
        {tr("Couche limite (BL)")}
      </span>
      {convective && (
        <span>
          <svg width="16" height="10" className="sw" style={{ display: "inline-block" }}>
            <rect width="16" height="10" fill="url(#hh)" stroke="#000" />
          </svg>
          {tr("Couche convective")}
        </span>
      )}
      {hcoulim && (
        <span>
          <Sw style={{ width: 16, borderTop: "1.5px dashed #fff" }} />
          H_COULIM
        </span>
      )}
    </div>
  );
}

/** Hatch pattern used by the convective-layer areas, defined once for the whole page. */
export const HatchDefs = () => (
  <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
    <defs>
      <pattern id="hh" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
        <rect width="3" height="6" fill="#fff" />
        <rect x="3" width="3" height="6" fill="#000" />
      </pattern>
    </defs>
  </svg>
);

/** Turbo colour bar with end labels. */
export function ColorBar({ left, right, gradient }: { left: string; right: string; gradient: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
      <span className="small muted">{left}</span>
      <div style={{ flex: 1, height: 9, borderRadius: 2, background: gradient }} />
      <span className="small muted">{right}</span>
    </div>
  );
}
