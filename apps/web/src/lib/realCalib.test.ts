import { describe, expect, it } from "vitest";

import { calib } from "../mock/calibration";
import { nightHourIso, nightPointsToIso, nightsFromTimes, seeTerms, termsModel } from "./realCalib";

describe("real calibration", () => {
  it("seeing from the terms follows the seeing_core formula", () => {
    const J = 1e-13,
      r0 = (0.423 * (2 * Math.PI / 500e-9) ** 2 * J) ** (-3 / 5);
    expect(seeTerms([1, 1, 1], { t: J, c: 0, s: 0 })).toBeCloseTo((0.98 * 500e-9 / r0) * 206265, 6);
    expect(seeTerms([2, 0, 0], { t: J / 2, c: 0, s: 0 })).toBeCloseTo(seeTerms([1, 0, 0], { t: J, c: 0, s: 0 }), 9);
    expect(Number.isNaN(seeTerms([1, 1, 1], { t: 0, c: 0, s: 0 }))).toBe(true);
  });
  it("groups measurements by night and back", () => {
    const n = nightsFromTimes(["2026-10-13T21:30:00Z", "2026-10-14T03:00:00Z", "2026-10-14T13:00:00Z"], [1, 2, 3]);
    expect([...n.keys()]).toEqual(["2026-10-13", "2026-10-14"]);
    expect(n.get("2026-10-13")!.map((p) => p.x)).toEqual([9.5, 15]);
    expect(nightPointsToIso(n)[0]).toEqual(["2026-10-13T21:30:00.000Z", 1]);
    expect(nightHourIso("2026-10-13", 13)).toBe("2026-10-14T01");
  });
  it("fits the K that generated the measurements", () => {
    const times: string[] = [],
      vals: number[] = [],
      t: { valid_times: string[]; lead_hours: number[]; i_tke: number[]; i_conv: number[]; i_cis: number[] } = {
        valid_times: [], lead_hours: [], i_tke: [], i_conv: [], i_cis: [],
      };
    for (let d = 13; d < 16; d++)
      for (const h of [18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29]) {
        const ms = Date.UTC(2026, 9, d, h),
          x = { t: 1e-14 * (1 + ((h * 7 + d) % 5)), c: 0, s: 2e-15 * (1 + ((h * 3 + d) % 4)) };
        t.valid_times.push(new Date(ms).toISOString());
        t.lead_hours.push(h);
        t.i_tke.push(x.t);
        t.i_conv.push(0);
        t.i_cis.push(x.s);
        times.push(new Date(ms).toISOString());
        vals.push(seeTerms([3, 40, 0.1], x));
      }
    const model = termsModel(t, [2, 57, 0.1]);
    const { K, P } = calib(nightsFromTimes(times, vals), undefined, model);
    expect(P.length).toBeGreaterThan(20);
    expect(K[0]).toBeGreaterThan(2);
    expect(K[0]).toBeLessThan(4.5);
    expect(K[1]).toBeGreaterThan(30);
    expect(K[1]).toBeLessThan(55);
  });
});
