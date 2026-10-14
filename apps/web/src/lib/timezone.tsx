import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { DEFAULT_TIME_ZONE } from "../config";
import type { TimeZone } from "./time";

const STORAGE_KEY = "seeing.tz";

interface TzState {
  tz: TimeZone;
  setTz: (tz: TimeZone) => void;
}

const TzContext = createContext<TzState>({ tz: DEFAULT_TIME_ZONE, setTz: () => {} });

function initialTz(): TimeZone {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "UTC" || saved === "Europe/Paris") return saved;
  } catch {
    /* storage unavailable */
  }
  return DEFAULT_TIME_ZONE;
}

export function TimeZoneProvider({ children }: { children: ReactNode }) {
  const [tz, setTzState] = useState<TimeZone>(initialTz);
  const setTz = useCallback((next: TimeZone) => {
    setTzState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
  }, []);
  const value = useMemo(() => ({ tz, setTz }), [tz, setTz]);
  return <TzContext.Provider value={value}>{children}</TzContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export const useTimeZone = () => useContext(TzContext);
