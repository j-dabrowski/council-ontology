// Which snapshot set every panel reads from — "publish" (frontend/public/data/,
// what's actually live) or "draft" (the latest `council draft` run, served by
// vite.config.ts's draftOverlay() plugin at /data/draft/). Dev-server only:
// getMode() always returns "publish" in a production build, so this can never
// affect what Vercel serves.
export type SnapshotMode = "publish" | "draft";

const KEY = "co_snapshot_mode";

export function getMode(): SnapshotMode {
  if (!import.meta.env.DEV) return "publish";
  try {
    return localStorage.getItem(KEY) === "draft" ? "draft" : "publish";
  } catch {
    return "publish";
  }
}

export function setMode(mode: SnapshotMode): void {
  try {
    localStorage.setItem(KEY, mode);
  } catch {
    // ignore — worst case the toggle doesn't persist across a reload
  }
  window.location.reload();
}
