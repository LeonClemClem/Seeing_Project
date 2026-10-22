/**
 * Seeing CSV import (mockup's csvDate / csvUTC / addCSV): common date formats, UTC or local time
 * (fixed offset or Europe/Paris with DST), date and time in one or two columns, seeing in the last column.
 */

export type DateFmt = "auto" | "ymd" | "dmy" | "mdy" | "ymd2" | "dmyp" | "dmyd" | "dmy2" | "unix" | "excel";
export interface CsvOpts {
  tz: "TU" | "L";
  /** "paris" or a fixed offset in hours. */
  off: "paris" | number;
  fmt: DateFmt;
}
/** A parsed date: epoch ms when the zone is known, or `{ loc }` (wall-clock ms to be shifted by the file's zone). */
export type ParsedDate = number | { loc: number } | null;

/** Offset of Europe/Paris from UTC (hours) at instant ms. */
export function parisOffset(ms: number): number {
  const p = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Paris",
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).formatToParts(new Date(ms));
  const g = (k: string) => +p.find((x) => x.type === k)!.value;
  return (Date.UTC(g("year"), g("month") - 1, g("day"), g("hour"), g("minute")) - ms) / 3600000;
}

export function csvDate(s: string, fmt: DateFmt): ParsedDate {
  s = s.trim().replace(/"/g, "");
  let m: RegExpMatchArray | null, y: number, mo: number, d: number;
  if (fmt === "unix" || (fmt === "auto" && /^\d{9,11}(\.\d+)?$/.test(s))) {
    const v = +s;
    return isNaN(v) ? null : v * 1000;
  }
  if (fmt === "excel" || (fmt === "auto" && /^\d{5}\.\d+$/.test(s))) {
    const v = parseFloat(s.replace(",", "."));
    return isNaN(v) ? null : { loc: Math.round((v - 25569) * 86400000) };
  }
  const tm = s.match(/[ T](\d{1,2})[:h](\d{2})(?::(\d{2})(?:[.,]\d+)?)?\s*(Z|[+-]\d{2}:?\d{2})?\s*$/i);
  if (!tm) return null;
  const H = +tm[1]!,
    M = +tm[2]!,
    S = +(tm[3] || 0);
  let z: number | null = null;
  if (tm[4]) z = tm[4].toUpperCase() === "Z" ? 0 : (tm[4][0] === "-" ? -1 : 1) * (+tm[4].slice(1, 3) + +tm[4].slice(-2) / 60);
  const ds = s.slice(0, tm.index).trim();
  if ((fmt === "auto" || fmt === "ymd" || fmt === "ymd2") && (m = ds.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/)))
    [y, mo, d] = m.slice(1).map(Number) as [number, number, number];
  else if ((m = ds.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})$/))) {
    const [a, b, c0] = m.slice(1).map(Number) as [number, number, number];
    const c = c0 < 100 ? c0 + 2000 : c0;
    const us = fmt === "mdy" || (fmt === "auto" && b > 12 && a <= 12);
    if (fmt === "ymd" || fmt === "ymd2") return null;
    [d, mo, y] = us ? [b, a, c] : [a, b, c];
  } else return null;
  if (mo < 1 || mo > 12 || d < 1 || d > 31 || H > 23 || M > 59) return null;
  const loc = Date.UTC(y, mo - 1, d, H, M, S);
  return z != null ? loc - z * 3600000 : { loc };
}

export function csvUTC(r: ParsedDate, o: CsvOpts): number | null {
  if (r == null) return null;
  if (typeof r === "number") return r; // already UTC (Unix time, or zone written in the date)
  if (o.tz === "TU") return r.loc;
  if (o.off !== "paris") return r.loc - o.off * 3600000;
  const u = r.loc - parisOffset(r.loc) * 3600000;
  return r.loc - parisOffset(u) * 3600000;
}

/** A measured point of a night: x = hours since 12h UTC of the night's first day. */
export interface NightPt {
  x: number;
  v: number;
}

/** Parse a CSV text into points grouped by night (key = date of the evening, YYYY-MM-DD). */
export function parseCsv(txt: string, o: CsvOpts): { nights: Map<string, NightPt[]>; n: number; last: string | null } {
  const nights = new Map<string, NightPt[]>();
  let n = 0,
    last: string | null = null;
  txt.split(/\r?\n/).forEach((l) => {
    // ";" or tab when present, so that a decimal comma ("0,9") is not taken for a separator.
    const c = l.split(/[;\t]/.test(l) ? /[;\t]/ : ",");
    if (c.length < 2) return;
    let r = csvDate(c[0]!, o.fmt);
    if (r == null && c.length > 2) r = csvDate(c[0] + " " + c[1], o.fmt);
    const ms = csvUTC(r, o);
    if (ms == null || isNaN(ms)) return;
    const U = new Date(ms),
      H = U.getUTCHours(),
      M = U.getUTCMinutes();
    const v = parseFloat(c[c.length - 1]!.replace(",", "."));
    if (isNaN(v) || v <= 0 || v > 30) return;
    const dt = new Date(Date.UTC(U.getUTCFullYear(), U.getUTCMonth(), U.getUTCDate()));
    if (H < 12) dt.setUTCDate(dt.getUTCDate() - 1);
    const key = dt.toISOString().slice(0, 10);
    if (!nights.has(key)) nights.set(key, []);
    nights.get(key)!.push({ x: (H + M / 60 - 12 + 24) % 24, v });
    last = key;
    n++;
  });
  return { nights, n, last };
}
