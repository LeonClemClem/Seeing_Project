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
export const PL: [string, string, string][] = [
  ["Mercure", "☿", "#B4B2A9"],
  ["Vénus", "♀", "#FAC775"],
  ["Mars", "♂", "#E24B4A"],
  ["Jupiter", "♃", "#F0997B"],
  ["Saturne", "♄", "#EF9F27"],
  ["Uranus", "⛢", "#5DCAA5"],
  ["Neptune", "♆", "#85B7EB"],
];

/* Keplerian elements of the planets and their rates per century, J2000 ecliptic (JPL "Approximate
   Positions of the Planets", table 1, valid 1800-2050): a [au], e, I, L, long. perihelion, node [deg]. */
type Elements = [number, number, number, number, number, number];
const KEPLER: Record<string, [Elements, Elements]> = {
  Mercure: [[0.38709927, 0.20563593, 7.00497902, 252.2503235, 77.45779628, 48.33076593], [0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081]],
  Vénus: [[0.72333566, 0.00677672, 3.39467605, 181.9790995, 131.60246718, 76.67984255], [0.0000039, -0.00004107, -0.0007889, 58517.81538729, 0.00268329, -0.27769418]],
  Terre: [[1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0], [0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0]],
  Mars: [[1.52371034, 0.0933941, 1.84969142, -4.55343205, -23.94362959, 49.55953891], [0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343]],
  Jupiter: [[5.202887, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909], [-0.00011607, -0.00013253, -0.00183714, 3034.74612775, 0.21252668, 0.20469106]],
  Saturne: [[9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448], [-0.0012506, -0.00050991, 0.00193609, 1222.49362201, -0.41897216, -0.28867794]],
  Uranus: [[19.18916464, 0.04725744, 0.77263783, 313.23810451, 170.9542763, 74.01692503], [-0.00196176, -0.00004397, -0.00242939, 428.48202785, 0.40805281, 0.04240589]],
  Neptune: [[30.06992276, 0.00859048, 1.77004347, -55.12002969, 44.96476227, 131.78422574], [0.00026291, 0.00005105, 0.00035372, 218.45945325, -0.32241464, -0.00508664]],
};

/** Heliocentric ecliptic position [au] of a body of KEPLER at time t [ms]. */
function helio(name: string, t: number): [number, number, number] {
  const [e0, r] = KEPLER[name]!,
    T = (t / 86400000 + 2440587.5 - 2451545) / 36525,
    [a, e, I, L, wp, O] = e0.map((v, k) => v + r[k]! * T) as Elements;
  const w = (wp - O) * D2R,
    om = O * D2R,
    inc = I * D2R;
  let M = (((L - wp) % 360) + 540) % 360 - 180;
  M *= D2R;
  let E = M + e * Math.sin(M);
  for (let k = 0; k < 8; k++) E -= (E - e * Math.sin(E) - M) / (1 - e * Math.cos(E));
  const xp = a * (Math.cos(E) - e),
    yp = a * Math.sqrt(1 - e * e) * Math.sin(E);
  const cw = Math.cos(w), sw = Math.sin(w), co = Math.cos(om), so = Math.sin(om), ci = Math.cos(inc), si = Math.sin(inc);
  return [
    (cw * co - sw * so * ci) * xp + (-sw * co - cw * so * ci) * yp,
    (cw * so + sw * co * ci) * xp + (-sw * so + cw * co * ci) * yp,
    sw * si * xp + cw * si * yp,
  ];
}

/** Geocentric right ascension [h] and declination [deg] of a planet of PL at time t [ms] (about 1'). */
export function planetRaDec(name: string, t: number): [number, number] {
  const p = helio(name, t),
    g = helio("Terre", t),
    x = p[0] - g[0],
    y = p[1] - g[1],
    z = p[2] - g[2],
    eps = 23.43928 * D2R,
    ye = y * Math.cos(eps) - z * Math.sin(eps),
    ze = y * Math.sin(eps) + z * Math.cos(eps);
  return [((Math.atan2(ye, x) / D2R / 15) % 24 + 24) % 24, Math.atan2(ze, Math.hypot(x, ye)) / D2R];
}
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
