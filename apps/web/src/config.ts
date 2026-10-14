/** Single place for seeing thresholds, colours and display constants. Seeing in arcsec: lower is better. */

export type SeeingClass = "excellent" | "good" | "average" | "poor";

export interface SeeingBand {
  cls: SeeingClass;
  label: string;
  /** Upper bound (exclusive), arcsec. */
  max: number;
  color: string;
}

export const SEEING_BANDS: readonly SeeingBand[] = [
  { cls: "excellent", label: "Excellent", max: 1.0, color: "#2fd6a3" },
  { cls: "good", label: "Good", max: 1.5, color: "#9bd34b" },
  { cls: "average", label: "Average", max: 2.5, color: "#fab219" },
  { cls: "poor", label: "Poor", max: Infinity, color: "#f0605d" },
];

export const NO_DATA_COLOR = "#5b6380";

/** Sun altitude (degrees) below which it is "night" for observing (astronomical twilight). */
export const NIGHT_SUN_ALTITUDE = -18;
/** Fallback when there is no astronomical night (northern France around the June solstice). */
export const NIGHT_SUN_ALTITUDE_FALLBACK = -12;

/** Length of the "best window" (number of consecutive hourly points). */
export const BEST_WINDOW_HOURS = 3;

/** Cn2 colour scale (log10 of m^-2/3), dark = calm. */
export const CN2_LOG_MIN = -18;
export const CN2_LOG_MAX = -13;
export const CN2_COLORS = ["#070b1a", "#132a5c", "#1c5cab", "#3987e5", "#86b6ef", "#e8f1ff", "#ffe08a"];
export const CN2_LOW_MAX_HEIGHT_M = 4000;

export const DEFAULT_TIME_ZONE = "Europe/Paris";

/** France, roughly. */
export const MAP_CENTER: [number, number] = [2.6, 46.4];
export const MAP_STYLE_URL = "https://tiles.openfreemap.org/styles/dark";
