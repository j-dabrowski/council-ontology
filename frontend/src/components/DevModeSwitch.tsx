import { useEffect, useState } from "react";
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
  const [runId, setRunId] = useState<string | null>(null);

  useEffect(() => {
    if (mode !== "draft") return;
    let cancelled = false;
    fetch("/data/draft/manifest.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((m) => { if (!cancelled) setRunId(m?.run_id ?? null); })
      .catch(() => { if (!cancelled) setRunId(null); });
    return () => { cancelled = true; };
  }, [mode]);

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
