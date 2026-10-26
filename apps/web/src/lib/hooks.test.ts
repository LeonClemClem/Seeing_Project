import { describe, expect, it } from "vitest";

import { decodeFrame } from "./hooks";

describe("decodeFrame", () => {
  it("decodes the log-scale codes like seeing_core.grid.decode_seeing", () => {
    const meta = { run_time: "", grid: { ny: 1, nx: 3, lat0: 0, lon0: 0, dlat: 1, dlon: 1 }, see_min: 0.2, see_max: 10, frames: [] };
    const s = decodeFrame(new Uint8Array([0, 254, 255]), meta);
    expect(s[0]).toBeCloseTo(0.2, 5);
    expect(s[1]).toBeCloseTo(10, 4);
    expect(Number.isNaN(s[2])).toBe(true);
  });
});
