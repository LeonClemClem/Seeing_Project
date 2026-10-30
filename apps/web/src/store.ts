/** App-wide UI state shared across views (the mockup's `S`, `MESF`, `CORRF`, role and language). */
import { useMemo, useSyncExternalStore } from "react";

import { setTrLang, type Lang } from "./i18n";

export type K3 = [number, number, number];
export type Role = "user" | "team" | "admin";

export interface UiState {
  lang: Lang;
  role: Role;
  /** Selected place id: `pub:<slug>` (API site) or `mine:<id>` (mock personal place). */
  place: string;
  /** K in use, K fitted for the place, and whether the K in use are the fitted ones ("A") or manual ("M"). */
  K: K3;
  KCAL: K3;
  kmode: "A" | "M";
  showObs: boolean;
  mesf: { brut: boolean; horaire: boolean; courbe: boolean };
  corrf: { horaire: boolean; nuit: boolean; brut: boolean };
  /** Night highlighted in the history and the correlation (date of the evening, UTC), or null. */
  selNight: string | null;
}

function initialLang(): Lang {
  try {
    return localStorage.getItem("seeing-lang") === "en" ? "en" : "fr";
  } catch {
    return "fr";
  }
}

let state: UiState = {
  lang: initialLang(),
  role: "user",
  place: "pub:ohp",
  K: [11.6, 20.8, 0.1],
  KCAL: [11.6, 20.8, 0.1],
  kmode: "A",
  showObs: true,
  mesf: { brut: true, horaire: true, courbe: true },
  corrf: { horaire: true, nuit: true, brut: true },
  selNight: null,
};
setTrLang(state.lang);

const listeners = new Set<() => void>();

export function getState(): UiState {
  return state;
}

export function setState(patch: Partial<UiState> | ((s: UiState) => Partial<UiState>)) {
  const p = typeof patch === "function" ? patch(state) : patch;
  state = { ...state, ...p };
  if (p.lang) {
    setTrLang(p.lang);
    try {
      localStorage.setItem("seeing-lang", p.lang);
    } catch {
      /* storage unavailable */
    }
    document.documentElement.lang = p.lang;
  }
  listeners.forEach((f) => f());
}

function subscribe(f: () => void) {
  listeners.add(f);
  return () => listeners.delete(f);
}

export function useUi<T>(select: (s: UiState) => T): T {
  return useSyncExternalStore(subscribe, () => select(state));
}

/** K bounds used by the mockup's ÷2 / ×2 buttons. */
export const clipK = (v: number) => Math.min(150, Math.max(0.01, v));

export function setK(K: K3, mode?: "A" | "M") {
  setState({ K: [clipK(K[0]), clipK(K[1]), K[2] ?? 0.1], ...(mode ? { kmode: mode } : {}) });
}

/**
 * useMemo that also recomputes when the language changes: chart builders return strings translated with tr().
 * Dependencies are not lint-checked at call sites, so list everything the factory reads.
 */
export function useLangMemo<T>(factory: () => T, deps: unknown[]): T {
  const lang = useUi((s) => s.lang);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(factory, [...deps, lang]);
}
