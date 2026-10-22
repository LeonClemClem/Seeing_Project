import { afterEach, describe, expect, it } from "vitest";

import { setTrLang, tr } from ".";

describe("tr", () => {
  afterEach(() => setTrLang("fr"));
  it("returns French unchanged", () => expect(tr("Carte")).toBe("Carte"));
  it("translates exact strings, keeping surrounding spaces", () => {
    setTrLang("en");
    expect(tr("Carte")).toBe("Map");
    expect(tr(" Mes lieux ")).toBe(" My places ");
  });
  it("applies fragment rules to dynamic strings", () => {
    setTrLang("en");
    expect(tr("Nuit du 12 au 13/10")).toBe("Night of 12–13/10");
    expect(tr("mar. 13/10 · 02h TU · +14 h")).toBe("Tue 13/10 · 02h UTC · +14 h");
  });
  it("leaves unknown strings alone", () => {
    setTrLang("en");
    expect(tr("Seeing AROME")).toBe("Seeing AROME");
  });
});
