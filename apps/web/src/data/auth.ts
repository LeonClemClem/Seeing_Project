/** Current app account and the login / sign-up / logout actions (react-query on /api/me). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { api, queryKeys, type User } from "../api";
import { setState } from "../store";

export function useMe() {
  return useQuery({ queryKey: queryKeys.me, queryFn: api.me, staleTime: 60_000 });
}

/** Logged-in user (null when logged out or while loading). */
export function useUser(): User | null {
  return useMe().data?.user ?? null;
}

/** Keep the UI role (K visibility rules) in step with the logged-in account. */
export function useSyncRole() {
  const role = useUser()?.role;
  useEffect(() => {
    if (role) setState({ role });
  }, [role]);
}

export function useAuthActions() {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: queryKeys.me });
  const login = useMutation({ mutationFn: api.login, onSuccess: refresh });
  const signup = useMutation({ mutationFn: api.signup, onSuccess: refresh });
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      setState({ role: "user" });
      return refresh();
    },
  });
  return { login, signup, logout };
}
