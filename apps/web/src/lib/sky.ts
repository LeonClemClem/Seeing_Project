/** Sky helpers for the fisheye: alt/az of fixed objects, constellations, catalogue (from the mockup). */
import SunCalc from "suncalc";

import { D2R } from "./util";

/** Altitude and azimuth (degrees, azimuth from north through east) of RA (hours) / Dec (degrees) at time t. */
export function altaz(ra: number, dec: number, t: number, lat: number, lon: number): [number, number] {
  const jd = t / 86400000 + 2440587.5,
    g = (18.697374558 + 24.06570982441908 * (jd - 2451545)) % 24,
    lst = (((g + lon / 15) % 24) + 24) % 24,
    H = (lst - ra) * 15 * D2R,
    d = dec * D2R,
    p = lat * D2R;
  const alt = Math.asin(Math.sin(p) * Math.sin(d) + Math.cos(p) * Math.cos(d) * Math.cos(H)) / D2R;
  const az = (Math.atan2(Math.sin(H), Math.cos(H) * Math.sin(p) - Math.tan(d) * Math.cos(p)) / D2R + 180 + 360) % 360;
  return [alt, az];
}

/** suncalc azimuth is measured from south towards west; convert to degrees from north towards east. */
const fromSuncalc = (p: { altitude: number; azimuth: number }): [number, number] => [
  p.altitude / D2R,
  (p.azimuth / D2R + 180 + 360) % 360,
];
export const sunAltAz = (t: number, lat: number, lon: number) => fromSuncalc(SunCalc.getPosition(new Date(t), lat, lon));
export const moonAltAz = (t: number, lat: number, lon: number) => fromSuncalc(SunCalc.getMoonPosition(new Date(t), lat, lon));

const PHASES = [
  "Nouvelle lune",
  "Premier croissant",
  "Premier quartier",
  "Gibbeuse croissante",
  "Pleine lune",
  "Gibbeuse décroissante",
  "Dernier quartier",
  "Dernier croissant",
];
export function moonPhase(t: number): { name: string; pct: number; waxing: boolean } {
  const m = SunCalc.getMoonIllumination(new Date(t));
  return { name: PHASES[Math.round(m.phase * 8) % 8]!, pct: Math.round(m.fraction * 100), waxing: m.phase < 0.5 };
}

/** Fictitious horizon profile (degrees) by azimuth. */
export const horizon = (a: number) =>
  Math.max(
    0,
    2 +
      4 * Math.exp(-((((a - 95 + 540) % 360) - 180) ** 2) / 700) +
      2.5 * Math.exp(-((((a - 220 + 540) % 360) - 180) ** 2) / 1500) +
      0.6 * Math.sin(a * D2R * 5),
  );
export const airmass = (alt: number) => 1 / (Math.sin(alt * D2R) + 0.50572 * Math.pow(alt + 6.07995, -1.6364));

/** Constellation stars [RA h, Dec °] and their stick-figure lines. */
export const ST: Record<string, [number, number][]> = {
  "Grande Ourse": [[11.062, 61.75], [11.031, 56.38], [11.897, 53.69], [12.257, 57.03], [12.9, 55.96], [13.399, 54.93], [13.792, 49.31]],
  Cassiopée: [[0.153, 59.15], [0.675, 56.54], [0.945, 60.72], [1.43, 60.24], [1.907, 63.67]],
  Cygne: [[20.69, 45.28], [20.37, 40.26], [19.512, 27.96], [20.77, 33.97], [19.75, 45.13]],
  Pégase: [[23.079, 15.21], [23.063, 28.08], [0.14, 29.09], [0.22, 15.18]],
  Orion: [[5.919, 7.41], [5.418, 6.35], [5.679, -1.94], [5.603, -1.2], [5.533, -0.3], [5.242, -8.2], [5.796, -9.67]],
  Lyre: [[18.616, 38.78], [18.835, 33.36], [18.982, 32.69], [18.746, 37.6]],
  "Petite Ourse": [[2.53, 89.26], [17.536, 86.59], [16.766, 82.04], [15.734, 77.79], [14.845, 74.16]],
};
export const LN: Record<string, [number, number][]> = {
  "Grande Ourse": [[0, 1], [1, 2], [2, 3], [3, 0], [3, 4], [4, 5], [5, 6]],
  Cassiopée: [[0, 1], [1, 2], [2, 3], [3, 4]],
  Cygne: [[0, 1], [1, 2], [4, 1], [1, 3]],
  Pégase: [[0, 1], [1, 2], [2, 3], [3, 0]],
  Orion: [[0, 1], [0, 2], [1, 4], [2, 3], [3, 4], [2, 6], [4, 5]],
  Lyre: [[0, 3], [3, 1], [1, 2], [2, 3]],
  "Petite Ourse": [[0, 1], [1, 2], [2, 3], [3, 4]],
};

/** Planets: name, symbol, colour, RA (h). Positions are fictitious in the mockup (on the ecliptic). */
export const PL: [string, string, string, number][] = [
  ["Mercure", "☿", "#B4B2A9", 13.6],
  ["Vénus", "♀", "#FAC775", 15.1],
  ["Mars", "♂", "#E24B4A", 9.4],
  ["Jupiter", "♃", "#F0997B", 7.9],
  ["Saturne", "♄", "#EF9F27", 0.4],
  ["Uranus", "⛢", "#5DCAA5", 3.9],
  ["Neptune", "♆", "#85B7EB", 23.9],
];
export const eclipticDec = (ra: number) => Math.atan(Math.sin(ra * 15 * D2R) * Math.tan(23.44 * D2R)) / D2R;

/** Catalogue: id, name, catalogue, RA (h), Dec (°). */
export type CatObj = [string, string, string, number, number];
export const CAT: CatObj[] = [
  ["M31", "Galaxie d'Andromède", "Messier", 0.712, 41.27],
  ["M33", "Galaxie du Triangle", "Messier", 1.564, 30.66],
  ["M45", "Pléiades", "Messier", 3.79, 24.12],
  ["M42", "Nébuleuse d'Orion", "Messier", 5.588, -5.39],
  ["M81", "Galaxie de Bode", "Messier", 9.926, 69.07],
  ["M51", "Galaxie du Tourbillon", "Messier", 13.498, 47.2],
  ["M13", "Amas d'Hercule", "Messier", 16.695, 36.46],
  ["M92", "Amas globulaire", "Messier", 17.285, 43.14],
  ["M11", "Amas du Canard sauvage", "Messier", 18.851, -6.27],
  ["M57", "Nébuleuse de la Lyre", "Messier", 18.893, 33.03],
  ["M27", "Nébuleuse de l'Haltère", "Messier", 19.994, 22.72],
  ["M15", "Amas de Pégase", "Messier", 21.5, 12.17],
  ["NGC 869", "Double amas de Persée", "NGC", 2.33, 57.13],
  ["NGC 891", "Galaxie par la tranche", "NGC", 2.376, 42.35],
  ["NGC 7000", "Nébuleuse North America", "NGC", 20.98, 44.3],
  ["NGC 7293", "Nébuleuse de l'Hélice", "NGC", 22.494, -20.84],
  ["NGC 6960", "Dentelles du Cygne", "NGC", 20.76, 30.71],
  ["C4", "Nébuleuse de l'Iris", "Caldwell", 21.02, 68.17],
  ["C9", "Nébuleuse de la Grotte", "Caldwell", 22.95, 62.62],
  ["C14", "Double amas de Persée", "Caldwell", 2.33, 57.13],
  ["Albireo", "β Cygni", "Étoiles doubles", 19.512, 27.96],
  ["Mizar", "ζ UMa", "Étoiles doubles", 13.399, 54.93],
  ["ε Lyrae", "Double-double", "Étoiles doubles", 18.739, 39.67],
  ["Almach", "γ And", "Étoiles doubles", 2.065, 42.33],
];
