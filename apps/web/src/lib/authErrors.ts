/** French message (translated by tr() in the page) for an auth API failure. */
import { ApiError } from "../api";

export function authErrorMessage(err: unknown, mode: "login" | "signup"): string {
  if (!(err instanceof ApiError)) return "Serveur injoignable. Réessaie dans un instant.";
  switch (err.status) {
    case 401:
      return "E-mail ou mot de passe incorrect.";
    case 403:
      return mode === "signup" ? "La création de compte est fermée pour le moment." : "Accès refusé.";
    case 409:
      return "Un compte existe déjà avec cette adresse.";
    case 422:
      return mode === "signup"
        ? "Vérifie l'adresse e-mail ; le mot de passe doit faire au moins 10 caractères."
        : "Vérifie l'adresse e-mail et le mot de passe.";
    default:
      return "Erreur du serveur. Réessaie dans un instant.";
  }
}
