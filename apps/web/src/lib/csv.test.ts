import { describe, expect, it } from "vitest";

import { csvDate, csvUTC, parisOffset, parseCsv, type CsvOpts } from "./csv";

const UTC: CsvOpts = { tz: "TU", off: "paris", fmt: "auto" };

describe("csvDate", () => {
  it("detects ISO, European and US dates", () => {
    expect(csvDate("2026-10-12 21:05", "auto")).toEqual({ loc: Date.UTC(2026, 9, 12, 21, 5) });
    expect(csvDate("12/10/2026 21:05", "auto")).toEqual({ loc: Date.UTC(2026, 9, 12, 21, 5) });
    expect(csvDate("10/13/2026 21:05", "auto")).toEqual({ loc: Date.UTC(2026, 9, 13, 21, 5) });
    expect(csvDate("10/12/2026 21:05", "mdy")).toEqual({ loc: Date.UTC(2026, 9, 12, 21, 5) });
    expect(csvDate("12.10.26 21h05", "auto")).toEqual({ loc: Date.UTC(2026, 9, 12, 21, 5) });
  });
  it("uses an explicit zone or a Unix timestamp as UTC", () => {
    expect(csvDate("2026-10-12T21:05:00Z", "auto")).toBe(Date.UTC(2026, 9, 12, 21, 5));
    expect(csvDate("2026-10-12T23:05+02:00", "auto")).toBe(Date.UTC(2026, 9, 12, 21, 5));
    expect(csvDate("1791839100", "auto")).toBe(1791839100 * 1000);
  });
  it("reads Excel serial dates", () => {
    expect(csvDate("46307.5", "auto")).toEqual({ loc: Date.UTC(2026, 9, 12, 12) });
  });
  it("rejects what it cannot read", () => {
    expect(csvDate("hello", "auto")).toBeNull();
    expect(csvDate("2026-13-01 10:00", "auto")).toBeNull();
    expect(csvDate("12/10/2026 21:05", "ymd")).toBeNull();
  });
});

describe("csvUTC", () => {
  const loc = { loc: Date.UTC(2026, 6, 1, 23, 0) };
  it("keeps UTC files as they are", () => expect(csvUTC(loc, UTC)).toBe(loc.loc));
  it("applies a fixed offset", () => expect(csvUTC(loc, { ...UTC, tz: "L", off: 5.5 })).toBe(loc.loc - 5.5 * 3600000));
  it("follows Europe/Paris summer and winter time", () => {
    expect(parisOffset(Date.UTC(2026, 6, 1))).toBe(2);
    expect(parisOffset(Date.UTC(2026, 0, 1))).toBe(1);
    expect(csvUTC(loc, { ...UTC, tz: "L" })).toBe(Date.UTC(2026, 6, 1, 21, 0));
    expect(csvUTC({ loc: Date.UTC(2026, 0, 1, 23, 0) }, { ...UTC, tz: "L" })).toBe(Date.UTC(2026, 0, 1, 22, 0));
  });
});

describe("parseCsv", () => {
  it("groups points by night (evening date) and takes seeing from the last column", () => {
    const r = parseCsv("date;time;seeing\n2026-10-12;22:00;1.2\n2026-10-13;02:30;0,9\n2026-10-13;13:00;2\nbad;line\n", UTC);
    expect(r.n).toBe(3);
    expect([...r.nights.keys()]).toEqual(["2026-10-12", "2026-10-13"]);
    expect(r.nights.get("2026-10-12")).toEqual([
      { x: 10, v: 1.2 },
      { x: 14.5, v: 0.9 },
    ]);
  });
  it("drops implausible seeing values", () => {
    expect(parseCsv("2026-10-12 22:00;0\n2026-10-12 22:05;45\n", UTC).n).toBe(0);
  });
});
