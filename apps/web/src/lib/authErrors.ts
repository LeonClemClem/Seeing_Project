/** French message (translated by tr() in the page) for an auth API failure. */
import { ApiError } from "../api";
import { MIN_LENGTH } from "./passwordRules";

/** Messages of the server's detail codes (password rules, e-mail confirmation). */
const DETAIL: Record<string, string> = {
  password_too_short: `Le mot de passe doit faire au moins ${MIN_LENGTH} caractères.`,
  password_too_simple: "Le mot de passe doit mêler au moins 3 types de caractères : minuscules, majuscules, chiffres, symboles.",
  password_too_common: "Ce mot de passe est trop courant (mot usuel ou suite du clavier). Choisis-en un autre.",
  password_contains_email: "Le mot de passe ne doit pas contenir ton adresse e-mail.",
  email_not_verified: "Confirme d'abord ton adresse : ouvre le lien reçu par e-mail.",
  invalid_or_expired: "Ce lien de confirmation n'est plus valable. Demande un nouvel e-mail.",
};

export function authErrorMessage(err: unknown, mode: "login" | "signup"): string {
  if (!(err instanceof ApiError)) return "Serveur injoignable. Réessaie dans un instant.";
  const known = DETAIL[err.message];
  if (known) return known;
  switch (err.status) {
    case 401:
      return "E-mail ou mot de passe incorrect.";
    case 403:
      return mode === "signup" ? "La création de compte est fermée pour le moment." : "Accès refusé.";
    case 409:
      return "Un compte existe déjà avec cette adresse.";
    case 422:
      return mode === "signup"
        ? `Vérifie l'adresse e-mail ; le mot de passe doit faire au moins ${MIN_LENGTH} caractères.`
        : "Vérifie l'adresse e-mail et le mot de passe.";
    case 429:
      return "Trop de tentatives. Réessaie dans un quart d'heure.";
    default:
      return "Erreur du serveur. Réessaie dans un instant.";
  }
}
