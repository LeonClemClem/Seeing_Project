/**
 * Places shown in the selector: public and shared sites from the API, and the user's personal places
 * (API places of the logged-in account; example places when logged out). All API places have real
 * forecasts, computed by the batch at every run.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";

import { api, queryKeys, type PlaceIn, type PlacePatch, type Site } from "../api";
import { useUser } from "./auth";
import { KDEF } from "../mock/engine";
import { useUi, type K3, type Role, type UiState } from "../store";

export interface Place {
  id: string;
  nom: string;
  lat: number;
  lon: number;
  alt: number | null;
  kind: "pub" | "mine";
  /** API slug for public sites. */
  slug?: string;
  /** API site shared by its team with the community (as opposed to a public observatory). */
  shared?: boolean;
  /** API site computed but not offered (Copernic, Drôme): the API sends it to the administrator only. */
  hidden?: boolean;
  /** Fitted K of the place. For API sites these are placeholders: the batch computes with its own K. */
  K: K3;
  /** Real forecasts from the API (as opposed to the fictitious model). */
  real: boolean;
  /** Measurement factor of the fictitious monitor (mock places). */
  f: number;
  /** Mock table columns of "Mes lieux". */
  vis?: "partagé · position approchée" | "privé";
  mesures?: string;
  kSrc?: "indépendants" | "facteur" | "voisins";
  prev?: "run global 12Z" | "hors France · en file, 2e";
}

export const MOCK_PLACES: Place[] = [
  { id: "mine:jardin", nom: "Jardin", lat: 44.3, lon: 5.3, alt: null, kind: "mine", K: [11.6, 20.8, 0.1], real: false, f: 1.0, vis: "partagé · position approchée", mesures: "3 CSV · 42 h de nuit", kSrc: "facteur", prev: "run global 12Z" },
  { id: "mine:col", nom: "Col de la Croix", lat: 44.612, lon: 5.701, alt: null, kind: "mine", K: [6.1, 33, 0.1], real: false, f: 0.92, vis: "privé", mesures: "8 CSV · 96 h de nuit", kSrc: "indépendants", prev: "run global 12Z" },
  { id: "mine:star", nom: "Star party", lat: 46.912, lon: 10.54, alt: null, kind: "mine", K: [...KDEF], real: false, f: 1.12, vis: "privé", mesures: "", kSrc: "voisins", prev: "hors France · en file, 2e" },
];

export const siteToPlace = (s: Site): Place => ({
  id: (s.owned ? "own:" : "pub:") + s.slug,
  nom: s.name,
  lat: s.lat,
  lon: s.lon,
  alt: s.altitude_m,
  kind: s.owned ? "mine" : "pub",
  slug: s.slug,
  shared: s.visibility === "shared",
  hidden: s.visibility === "hidden",
  K: s.k && s.k.length === 3 ? [s.k[0]!, s.k[1]!, s.k[2]!] : [...KDEF],
  real: true,
  f: 1,
  vis: !s.owned ? undefined : s.visibility === "shared" ? "partagé · position approchée" : "privé",
  mesures: s.owned ? "" : undefined,
});

export function useSites() {
  const user = useUser();
  // keepPreviousData: while the list reloads (login, new place), keep the previous one instead of falling
  // back for an instant to the example places (their fictitious panels).
  return useQuery({ queryKey: [...queryKeys.sites, user?.id ?? 0], queryFn: api.sites, placeholderData: keepPreviousData });
}

export function usePlaces(): { pub: Place[]; sh: Place[]; hid: Place[]; mine: Place[]; all: Place[] } {
  const sites = useSites();
  const user = useUser();
  return useMemo(() => {
    const api = (sites.data ?? []).map(siteToPlace);
    const own = api.filter((p) => p.kind === "mine"),
      others = api.filter((p) => p.kind !== "mine");
    const pub = others.filter((p) => !p.shared && !p.hidden),
      sh = others.filter((p) => p.shared),
      hid = others.filter((p) => p.hidden);
    // Logged out: the example places show what an account gives.
    const mine = user ? own : MOCK_PLACES;
    return { pub, sh, hid, mine, all: [...others, ...mine] };
  }, [sites.data, user]);
}

export const MAX_PLACES = 5;

/** Create / update / delete the account's places; every change reloads the site list. */
export function usePlaceActions() {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: queryKeys.sites });
  return {
    create: useMutation({ mutationFn: (b: PlaceIn) => api.createPlace(b), onSuccess: refresh }),
    update: useMutation({ mutationFn: ({ slug, ...b }: PlacePatch & { slug: string }) => api.updatePlace(slug, b), onSuccess: refresh }),
    remove: useMutation({ mutationFn: (slug: string) => api.deletePlace(slug), onSuccess: refresh }),
  };
}

/** Site of the shared "CosmoDrôme team" account: its team sees and sets its K. */
export const TEAM_SITE = "cosmodrome";

export function useCurrentPlace(): Place {
  const id = useUi((s) => s.place);
  const { all } = usePlaces();
  return all.find((p) => p.id === id) ?? MOCK_PLACES[0]!;
}

/** K of public and shared sites are visible to the administrator only (and to the team for its own site);
 * everyone sees the K of their own places. */
export const kHidden = (p: Place, role: Role) =>
  p.kind === "pub" && role !== "admin" && !(role === "team" && p.slug === TEAM_SITE);

export const kTxt = (K: K3, hid: boolean, f: (v: number) => string | number = (v) => v) =>
  hid ? "K confidentiels" : `K_TKE = ${f(K[0])}  K_CIS = ${f(K[1])}  K_conv = ${f(K[2])}`;

/** Select a place and load its fitted K, like the mockup's applyLieuK(). */
export function selectPlace(p: Place): Partial<UiState> {
  return { place: p.id, KCAL: [...p.K], K: [...p.K], kmode: "A" };
}
