import { useEffect, useState } from "react";
import { getMode } from "./devMode";

// Last-resort default only: used for the very first paint before App's
// route-level redirect (bare "/" -> "/c/<a real council>/") has run, and as
// a safe fallback for anything rendered outside the "/c/:council" route
// tree (DevModeSwitch, which sits above <Routes> so it can show on every
// page including /about and /contact). Every real page read goes through
// that route — see App.tsx and CouncilHeader — never this constant
// directly.
export const FALLBACK_COUNCIL = "cambridge";

// The active council, read straight from the current route (HashRouter puts
// it in location.hash: "#/c/<council>/..."), not from any state kept here
// or in api.ts — SECOND_COUNCIL_PLAN.md Phase 3.2's "keep the selected
// council in the route, not component state" applies to the data layer too.
// A plain hash parse (rather than react-router's useParams()) so this works
// identically from api.ts (no React context at all) and from components
// that sit above the matched "/c/:council" route tree (DevModeSwitch).
export function currentCouncil(): string {
  const hash = window.location.hash.replace(/^#\/?/, "");
  const parts = hash.split("/");
  return parts[0] === "c" && parts[1] ? parts[1] : FALLBACK_COUNCIL;
}

// The mode-dependent council list (SECOND_COUNCIL_PLAN.md Phase 2.5):
// CouncilHeader's selector, the page footers, and MapPage all read this —
// never a hardcoded council literal. Publish mode (the only mode a
// production build can take — devMode.ts's getMode()) reads the committed,
// git-tracked frontend/public/data/councils.json (Phase 2.2), which only
// ever lists councils council publish has actually shipped: a synthetic
// fixture council can never appear there, since src/publish_gate.py's
// check_not_synthetic refuses it before it can reach that file. Draft mode
// (dev server only) instead reads a listing vite.config.ts's draftOverlay()
// plugin serves live from data/draft/*/ — every council with a
// gate-passing draft run, the synthetic fixture included, so a developer
// can select it like any other council.
export interface CouncilListEntry {
  key: string;
  display_name: string;
  source_url: string | null;
  corpus_span: string | null;
  published_at: string;
  draft_run_id: string;
}

// Vite's dev server SPA-falls-back to index.html (200, text/html) for any
// unmatched path rather than a real 404 — same gotcha getSnapshot() (api.ts)
// already guards against. A freshly-cloned repo with nothing published yet
// hits this on every load (no frontend/public/data/councils.json committed
// until a first real publish), so this must degrade to an empty list, not
// throw on `res.json()` parsing HTML.
function isRealJson(res: Response): boolean {
  return res.ok && (res.headers.get("content-type")?.includes("json") ?? false);
}

export async function fetchCouncilList(): Promise<CouncilListEntry[]> {
  if (getMode() === "draft") {
    const res = await fetch("/data/draft/councils.json");
    if (!isRealJson(res)) return [];
    const rows: {
      key: string; run_id: string; generated_at: string;
      display_name?: string; source_url?: string | null;
    }[] = await res.json();
    // display_name/source_url come from the draft's own manifest.json
    // (src/cli.py's cmd_draft, sourced from the COUNCILS registry) via
    // vite.config.ts's draftOverlay() plugin — falls back to the raw key
    // only for a manifest written before that field existed.
    return rows.map((r) => ({
      key: r.key,
      display_name: r.display_name ?? r.key,
      source_url: r.source_url ?? null,
      corpus_span: null,
      published_at: r.generated_at,
      draft_run_id: r.run_id,
    }));
  }
  const res = await fetch("/data/councils.json");
  if (!isRealJson(res)) return [];
  return res.json();
}

// This council's own corpus_span, straight from councils.json's entry for
// it — the shared source every chart/panel that used to hardcode a fixed
// year range now reads instead (SECOND_COUNCIL_PLAN.md Phase 3.3). Null
// while the list is loading or if this council has no entry yet (e.g. Draft
// mode, which carries no corpus_span at all — see fetchCouncilList()).
export function useCorpusSpan(): string | null {
  const { list } = useCouncilList();
  const council = currentCouncil();
  return list.find((c) => c.key === council)?.corpus_span ?? null;
}

// Shared loading state for the two places that need to know the whole list
// before rendering anything useful: the bare-"/" / invalid-council redirect
// in App.tsx, and CouncilHeader's selector (which also needs `loading` to
// avoid flashing a one-entry-then-two-entries dropdown).
export function useCouncilList(): { list: CouncilListEntry[]; loading: boolean } {
  const [list, setList] = useState<CouncilListEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchCouncilList()
      .then((rows) => { if (!cancelled) { setList(rows); setLoading(false); } })
      .catch(() => { if (!cancelled) { setList([]); setLoading(false); } });
    return () => { cancelled = true; };
  }, []);

  return { list, loading };
}
