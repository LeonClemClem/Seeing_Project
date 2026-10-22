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
});
