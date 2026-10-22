/**
 * French is the source language (as in the mockup); English is produced by looking a string up in
 * en_exact.json, then applying the fragment rules. `tr` is a plain function so chart builders can use it;
 * components re-render on a language change because they read `lang` from the store.
 */
import EN_EXACT from "./en_exact.json";
import EN_EXTRA from "./en_extra.json";
import { EN_FRAG } from "./en_frag";

export type Lang = "fr" | "en";

/** en_exact.json is the mockup's dictionary; en_extra.json holds strings added by the React port. */
const EXACT: Record<string, string> = { ...EN_EXACT, ...EN_EXTRA };
let LANG: Lang = "fr";

export function setTrLang(l: Lang) {
  LANG = l;
}

export function tr(s: string): string {
  if (LANG !== "en" || !s) return s;
  const k = s.replace(/\s+/g, " ").trim();
  if (!k) return s;
  const lead = s.match(/^\s*/)?.[0] ?? "";
  const trail = s.match(/\s*$/)?.[0] ?? "";
  const exact = EXACT[k];
  if (exact != null) return lead + exact + trail;
  let o = k;
  for (const [re, by] of EN_FRAG) o = typeof by === "string" ? o.replace(re, by) : o.replace(re, by);
  return o === k ? s : lead + o + trail;
}
