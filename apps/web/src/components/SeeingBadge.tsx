import { seeingBand, seeingColor } from "../lib/seeing";

/** Value + class label; colour is never the only carrier of meaning. */
export function SeeingValue({ value, size = "md" }: { value: number | null | undefined; size?: "md" | "lg" }) {
  const band = seeingBand(value);
  return (
    <span className={`seeing-value ${size}`}>
      <span className="dot" style={{ background: seeingColor(value) }} aria-hidden />
      <strong>{value == null ? "–" : `${value.toFixed(1)}″`}</strong>
      <span className="muted">{band?.label ?? "no data"}</span>
    </span>
  );
}

export function SeeingLegend() {
  return (
    <ul className="legend" aria-label="Seeing classes">
      <li>
        <span className="dot" style={{ background: seeingColor(0.8) }} />
        Excellent &lt;1″
      </li>
      <li>
        <span className="dot" style={{ background: seeingColor(1.2) }} />
        Good 1–1.5″
      </li>
      <li>
        <span className="dot" style={{ background: seeingColor(2) }} />
        Average 1.5–2.5″
      </li>
      <li>
        <span className="dot" style={{ background: seeingColor(3) }} />
        Poor &gt;2.5″
      </li>
    </ul>
  );
}
