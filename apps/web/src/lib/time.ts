export type TimeZone = "Europe/Paris" | "UTC";

const cache = new Map<string, Intl.DateTimeFormat>();

function fmt(tz: TimeZone, opts: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = tz + JSON.stringify(opts);
  let f = cache.get(key);
  if (!f) {
    f = new Intl.DateTimeFormat("en-GB", { timeZone: tz, hourCycle: "h23", ...opts });
    cache.set(key, f);
  }
  return f;
}

export const formatHour = (t: number | string, tz: TimeZone) =>
  fmt(tz, { hour: "2-digit", minute: "2-digit" }).format(new Date(t));

export const formatDay = (t: number | string, tz: TimeZone) =>
  fmt(tz, { weekday: "short", day: "numeric" }).format(new Date(t));

export const formatDayHour = (t: number | string, tz: TimeZone) =>
  `${formatDay(t, tz)} ${formatHour(t, tz)}`;

/** Hour of day (0-23) in the given zone. */
export function hourIn(t: number, tz: TimeZone): number {
  return Number(fmt(tz, { hour: "2-digit" }).format(new Date(t)));
}

/** Offset of `tz` from UTC at instant `t`, in ms (Paris: +1h or +2h). */
export function tzOffsetMs(t: number, tz: TimeZone): number {
  if (tz === "UTC") return 0;
  const parts = fmt(tz, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(new Date(t));
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  const wall = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"), get("second"));
  return wall - Math.floor(t / 1000) * 1000;
}

export const tzLabel = (tz: TimeZone) => (tz === "UTC" ? "UTC" : "Paris");

export function relativeAge(t: number | string, now: number = Date.now()): string {
  const minutes = Math.round((now - new Date(t).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

/** "12 UTC" for an AROME cycle. */
export function runLabel(runTime: string): string {
  return `${String(new Date(runTime).getUTCHours()).padStart(2, "0")} UTC`;
}
