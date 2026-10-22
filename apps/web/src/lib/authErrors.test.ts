import { describe, expect, it } from "vitest";

import { ApiError } from "../api";
import { authErrorMessage } from "./authErrors";

describe("authErrorMessage", () => {
  it("maps API statuses to messages", () => {
    expect(authErrorMessage(new ApiError(401, "x"), "login")).toBe("E-mail ou mot de passe incorrect.");
    expect(authErrorMessage(new ApiError(409, "x"), "signup")).toBe("Un compte existe déjà avec cette adresse.");
    expect(authErrorMessage(new ApiError(422, "x"), "signup")).toMatch(/10 caractères/);
    expect(authErrorMessage(new ApiError(403, "x"), "signup")).toMatch(/fermée/);
    expect(authErrorMessage(new ApiError(500, "x"), "login")).toMatch(/Erreur du serveur/);
  });
  it("treats network failures separately", () => {
    expect(authErrorMessage(new TypeError("Failed to fetch"), "login")).toMatch(/injoignable/);
  });
});
