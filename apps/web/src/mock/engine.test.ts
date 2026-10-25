import { describe, expect, it } from "vitest";

import { calib, exampleCsv } from "./calibration";
import { episodes, KDEF, lieuData, see } from "./engine";
import { parseCsv } from "../lib/csv";

describe("mock model", () => {
  it("is deterministic", () => {
    expect(episodes(1.0)).toBe(episodes(1.0));
    expect(see(30, KDEF, KDEF)).toBe(see(30, KDEF, KDEF));
    expect(lieuData("Jardin", 1, KDEF, KDEF).paires).toEqual(lieuData("Jardin", 1, KDEF, KDEF).paires);
  });
  it("scales seeing with K", () => {
    const K2: typeof KDEF = [KDEF[0] * 2, KDEF[1] * 2, 0.1];
    expect(see(22, K2, KDEF)).toBeGreaterThan(see(22, KDEF, KDEF));
  });
  it("fits K close to those used to generate the example nights", () => {
    const nights = new Map();
    for (let n = 0; n < 4; n++) parseCsv(exampleCsv(n), { tz: "TU", off: "paris", fmt: "auto" }).nights.forEach((v, k) => nights.set(k, v));
    const { K, P } = calib(nights);
    expect(P.length).toBeGreaterThan(20);
    expect(K[0]).toBeGreaterThan(3);
    expect(K[0]).toBeLessThan(60);
    expect(K[1]).toBeGreaterThan(5);
    expect(K[1]).toBeLessThan(100);
  });
  it("filters: removes the hours above the model, then refits", () => {
    const nights = new Map();
    for (let n = 0; n < 4; n++) parseCsv(exampleCsv(n), { tz: "TU", off: "paris", fmt: "auto" }).nights.forEach((v, k) => nights.set(k, v));
    const all = calib(nights);
    const f = calib(nights, { pics: false, courtes: false, top: 10 });
    expect(all.F.rm.size).toBe(0);
    expect(f.F.top).toBe(Math.round(all.P.length * 0.1));
    expect(f.P.length).toBe(all.P.length - f.F.top);
    expect(f.F.rm.size).toBe(f.F.top);
  });
  it("filters: drops nights without 3 successive hours and sparse medians", () => {
    const nights = new Map([
      ["2026-09-28", [{ x: 8, v: 1 }, { x: 10, v: 1 }]], // 20h and 22h UTC: no 3 successive hours
      ["2026-09-29", [6, 7, 8, 9, 10].flatMap((x) => (x === 9 ? [{ x, v: 1 }] : [0, 1, 2, 3].map(() => ({ x, v: 1 }))))],
    ]);
    const f = calib(nights, { pics: true, courtes: true, top: 0 });
    expect(f.F.courtes).toBe(1);
    expect(f.F.pics).toBe(1);
    expect(f.P.map((p) => p.key)).toEqual(["2026-09-29|6", "2026-09-29|7", "2026-09-29|8", "2026-09-29|10"]);
  });
});
