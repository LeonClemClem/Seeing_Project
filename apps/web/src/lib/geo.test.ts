import { describe, expect, it } from "vitest";

import { fuzz, inDomain, parseCoord } from "./geo";

describe("parseCoord", () => {
  it("parses decimal degrees, with comma or dot", () => {
    expect(parseCoord("44.1234", true)).toBeCloseTo(44.1234);
    expect(parseCoord("5,6789", false)).toBeCloseTo(5.6789);
  });
  it("parses degrees minutes seconds with hemisphere", () => {
    expect(parseCoord(`44°07'24" N`, true)).toBeCloseTo(44 + 7 / 60 + 24 / 3600, 6);
    expect(parseCoord(`5°40'44" E`, false)).toBeCloseTo(5 + 40 / 60 + 44 / 3600, 6);
    expect(parseCoord(`1°30' W`, false)).toBeCloseTo(-1.5);
    expect(parseCoord(`1°30' O`, false)).toBeCloseTo(-1.5);
    expect(parseCoord("-3.25", false)).toBeCloseTo(-3.25);
  });
  it("rejects invalid input", () => {
    expect(parseCoord("", true)).toBeNull();
    expect(parseCoord("abc", true)).toBeNull();
    expect(parseCoord("95", true)).toBeNull();
    expect(parseCoord(`44°75'`, true)).toBeNull();
    expect(parseCoord("1 2 3 4", true)).toBeNull();
  });
});

describe("fuzz", () => {
  it("moves a shared place 2 to 4 AROME cells away, always to the same spot", () => {
    const [la, lo] = fuzz(44.3, 5.3);
    expect(fuzz(44.3, 5.3)).toEqual([la, lo]);
    const dkm = Math.hypot((la - 44.3) * 111.2, (lo - 5.3) * 111.32 * Math.cos((44.3 * Math.PI) / 180));
    expect(dkm).toBeGreaterThan(5);
    expect(dkm).toBeLessThan(11.5);
  });
  it("knows the AROME domain", () => {
    expect(inDomain(44.3, 5.3)).toBe(true);
    expect(inDomain(60, 5)).toBe(false);
  });
});
