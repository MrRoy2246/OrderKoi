import { useEffect, useState } from "react";

/**
 * Reactive CSS media query for conditional rendering (e.g. the mobile
 * order-card list vs the desktop table). Re-renders on resize.
 */
export default function useMediaQuery(query) {
  const [matches, setMatches] = useState(
    () => typeof window !== "undefined" && window.matchMedia(query).matches
  );

  useEffect(() => {
    const mql = window.matchMedia(query);
    function onChange(event) {
      setMatches(event.matches);
    }
    mql.addEventListener("change", onChange);
    setMatches(mql.matches);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}
