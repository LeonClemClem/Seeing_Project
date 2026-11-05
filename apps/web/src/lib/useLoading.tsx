import { useEffect, useState, type CSSProperties, type ReactNode } from "react";

import { Spinner } from "../components/ui";

/** Loading state that lets the icon end on its Airy pattern: `show` stays true a little after `loading` turns false
 * (only if the icon was shown: data already in cache shows nothing), `spinner` is the icon to render meanwhile. */
export function useLoading(loading: boolean, style?: CSSProperties, size?: number): { show: boolean; spinner: ReactNode } {
  const [shown, setShown] = useState(loading);
  useEffect(() => {
    if (loading) setShown(true);
  }, [loading]);
  const show = loading || shown;
  return { show, spinner: show ? <Spinner style={style} size={size} done={!loading} onDone={() => setShown(false)} /> : null };
}
