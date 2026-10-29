import { describe, expect, it } from "vitest";

import { ApiError } from "../api";
import { authErrorMessage } from "./authErrors";

describe("authErrorMessage", () => {
  it("maps API statuses to messages", () => {
    expect(authErrorMessage(new ApiError(401, "x"), "login")).toBe("E-mail ou mot de passe incorrect.");
    expect(authErrorMessage(new ApiError(409, "x"), "signup")).toBe("Un compte existe déjà avec cette adresse.");
    expect(authErrorMessage(new ApiError(422, "x"), "signup")).toMatch(/12 caractères/);
    expect(authErrorMessage(new ApiError(429, "x"), "login")).toMatch(/Trop de tentatives/);
    expect(authErrorMessage(new ApiError(403, "x"), "signup")).toMatch(/fermée/);
    expect(authErrorMessage(new ApiError(500, "x"), "login")).toMatch(/Erreur du serveur/);
  });
  it("uses the server's detail codes", () => {
    expect(authErrorMessage(new ApiError(422, "password_too_common"), "signup")).toMatch(/trop courant/);
    expect(authErrorMessage(new ApiError(403, "email_not_verified"), "login")).toMatch(/Confirme d'abord/);
    expect(authErrorMessage(new ApiError(400, "invalid_or_expired"), "login")).toMatch(/plus valable/);
  });
  it("treats network failures separately", () => {
    expect(authErrorMessage(new TypeError("Failed to fetch"), "login")).toMatch(/injoignable/);
  });
});
