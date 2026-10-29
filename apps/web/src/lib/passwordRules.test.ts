import { describe, expect, it } from "vitest";

import { checkRules, kinds, strength } from "./passwordRules";

describe("password rules", () => {
  it("counts the character kinds", () => {
    expect(kinds("abc")).toBe(1);
    expect(kinds("Abc1")).toBe(3);
    expect(kinds("Abc1 ")).toBe(4);
    expect(kinds("Étoile-9")).toBe(4);
  });
  it("checks length, kinds and the e-mail name", () => {
    expect(checkRules("Correct horse battery 7", "ada@example.org")).toEqual({ length: true, kinds: true, email: true });
    expect(checkRules("short1A", "ada@example.org").length).toBe(false);
    expect(checkRules("only lower case words", "ada@example.org").kinds).toBe(false);
    expect(checkRules("Ada-is-my-name-42", "ada@example.org").email).toBe(false);
  });
  it("gives a strength for the meter", () => {
    expect(strength("", "a@b.fr")).toBe(0);
    expect(strength("weak", "a@b.fr")).toBe(1);
    expect(strength("Brume_matinale_9", "a@b.fr")).toBe(4);
    expect(strength("Brumematinale9", "a@b.fr")).toBe(2);
  });
});
