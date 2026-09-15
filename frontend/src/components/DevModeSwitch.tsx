import { useEffect, useState } from "react";
import { currentCouncil } from "../councils";
import { getMode, setMode } from "../devMode";

// Only ever rendered when import.meta.env.DEV is true (see App.tsx) — dead
// code in any production build, so this can never appear on the published
// site. Two parts: a full-width banner (normal document flow, so it pushes
// the page down rather than overlapping it) shown only in Draft mode, and a
// corner pill that's always visible and does the actual toggling. Loud on
// purpose: this repo already has one incident of wrong data staying
// invisible until deploy (see project memory on the hardcoded-names
// incident) — reading draft numbers as live ones is the same class of
// mistake, so Draft mode should be impossible to miss.
export function DevModeSwitch() {
  const mode = getMode();
  // Rendered above <Routes> (so the corner switch and DRAFT banner appear
  // on every page), which puts it above the "/c/:council" route match too
  // — react-router's useParams() would see nothing here. currentCouncil()
  // reads location.hash directly instead (see councils.ts); the hashchange
  // listener keeps the displayed run id in step when the council changes
  // via CouncilHeader's selector without a full page reload.
  const [council, setCouncil] = useState(currentCouncil());
  const [runId, setRunId] = useState<string | null>(null);

  useEffect(() => {
    const onHashChange = () => setCouncil(currentCouncil());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    if (mode !== "draft") return;
    let cancelled = false;
    fetch(`/data/draft/${council}/manifest.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((m) => { if (!cancelled) setRunId(m?.run_id ?? null); })
      .catch(() => { if (!cancelled) setRunId(null); });
    return () => { cancelled = true; };
  }, [mode, council]);

  const tooltip = "Local dev only. Switches every panel between the published snapshots and the latest `council draft` run. Never present in a build.";

  return (
    <>
      {mode === "draft" && (
        <div className="draft-bar" title={tooltip}>
          DRAFT DATA{runId ? ` — ${runId}` : ""} — not what's live
        </div>
      )}
      <button
        type="button"
        className={`dev-mode-switch dev-mode-${mode}`}
        onClick={() => setMode(mode === "draft" ? "publish" : "draft")}
        title={tooltip}
      >
        {mode === "draft" ? "● DRAFT" : "○ PUBLISH"}
      </button>
    </>
  );
}
