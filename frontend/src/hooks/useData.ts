import { useState, useEffect } from "react";
import { currentCouncil } from "../councils";

export function useData<T>(fetcher: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Every fetcher here ultimately calls api.ts's getSnapshot(), which reads
  // the active council straight from the route (currentCouncil()) at fetch
  // time. Switching council via CouncilHeader's selector navigates to the
  // same route *position* (still "/c/:council/analysis", say) with just a
  // different param, so React Router re-renders this component in place —
  // it never remounts — and an empty dependency array would fetch once on
  // first mount and then never again, leaving every panel showing whichever
  // council happened to be active on first load. Including `council` here
  // makes the effect re-run exactly when it actually needs to.
  const council = currentCouncil();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetcher()
      .then((d) => { if (!cancelled) { setData(d); setLoading(false); } })
      .catch((e) => { if (!cancelled) { setError(e.message); setLoading(false); } });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [council]);

  return { data, loading, error };
}

// Same as useData(), but the fetch only starts once `trigger()` is called
// (idempotent — later calls are no-ops) — for a snapshot large enough that
// it shouldn't load on every page visit, only once a reader actually
// interacts with whatever feature needs it (e.g. a search box's first
// keystroke/focus).
export function useLazyData<T>(fetcher: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [triggered, setTriggered] = useState(false);
  // Same council-change staleness as useData() above — a lazy fetch,
  // once triggered, must still refetch if the active council changes later.
  const council = currentCouncil();

  useEffect(() => {
    if (!triggered) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetcher()
      .then((d) => { if (!cancelled) { setData(d); setLoading(false); } })
      .catch((e) => { if (!cancelled) { setError(e.message); setLoading(false); } });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [triggered, council]);

  return { data, loading, error, trigger: () => setTriggered(true) };
}
