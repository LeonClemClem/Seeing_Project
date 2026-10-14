import { formatDay, formatHour, hourIn, tzOffsetMs, type TimeZone } from "../lib/time";

/** Keep in sync with the CSS custom properties in styles.css. */
export const chartTheme = {
  font: "Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
  text: "#9aa6c8",
  textStrong: "#eef2ff",
  axis: "#55608a",
  grid: "rgba(140, 160, 220, 0.12)",
  night: "rgba(120, 140, 255, 0.10)",
  now: "#ffd166",
  tooltipBg: "rgba(10, 15, 36, 0.95)",
};

const HOUR = 3_600_000;

/**
 * Charts plot "wall-clock time in the chosen zone, encoded as if it were UTC", so that a plain
 * numeric axis puts its ticks on round local hours. Axis values are formatted back with UTC.
 */
export const toAxis = (t: number, tz: TimeZone) => t + tzOffsetMs(t, tz);

export function timeAxis(x0: number, x1: number, stepHours: number) {
  const step = stepHours * HOUR;
  return {
    type: "value" as const,
    min: Math.floor(x0 / step) * step,
    max: x1,
    interval: step,
    axisLine: { lineStyle: { color: chartTheme.axis } },
    axisTick: { lineStyle: { color: chartTheme.axis } },
    splitLine: { show: false },
    axisLabel: {
      color: chartTheme.text,
      hideOverlap: true,
      formatter: (v: number) => (hourIn(v, "UTC") === 0 ? `{day|${formatDay(v, "UTC")}}` : formatHour(v, "UTC")),
      rich: { day: { color: chartTheme.textStrong, fontWeight: "bold" as const } },
    },
  };
}
