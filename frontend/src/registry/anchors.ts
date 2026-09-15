import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { currentCouncil } from "../councils";

// The one place either cross-page deep-link direction is expressed
// (docs/frontend/SURFACE_PROJECTION_PLAN.md B.2). App.tsx uses HashRouter,
// which owns the URL hash for routing — a plain fragment href like
// "#panel-declared" doesn't scroll, it replaces the route with
// "/panel-declared", which matches no <Route> and blanks the page. Deep-link
// through a search param on the hash route instead, which useSearchParams
// reads normally and which stays shareable.
//
// The anchor hook on the target element is `data-test-id={t.id}` — the raw
// registry id, matched with an attribute selector. Do not derive an HTML
// `id` by substituting characters in the test id: ids contain dots,
// `querySelector("#a.b")` parses the dot as a class, and any escaping
// scheme is a second identifier namespace to keep in step with the first.

// Every href here carries the active council (currentCouncil(), read from
// the route the same way api.ts does — App.tsx's Phase 2/3.2 "/c/:council"
// routing means a bare "#/analysis" no longer resolves to anything, it
// falls through to the catch-all redirect and loses the deep link entirely).

export function analysisHref(testId: string): string {
  return `#/c/${currentCouncil()}/analysis?test=${encodeURIComponent(testId)}`;
}

export function scorecardHref(testId: string): string {
  return `#/c/${currentCouncil()}?test=${encodeURIComponent(testId)}`;
}

// docs/frontend/WATCH_FEED_PLAN.md Step 7 — the latest-meeting strip's link
// into its row on /watch. Same query-param-on-the-hash-route shape as the
// test anchors above; `data-meeting-id` is the matching attribute (already
// carried by every WatchPage row for exactly this).
export function watchHref(meetingId: number): string {
  return `#/c/${currentCouncil()}/watch?meeting=${encodeURIComponent(meetingId)}`;
}

const HIGHLIGHT_CLASS = "test-target";
const HIGHLIGHT_MS = 2500;
// The target element may not exist yet on first render — the snapshot is
// still fetching — so this watches the DOM for it to appear rather than
// checking once and giving up. Once found, panels below it can still grow
// the page (a chart measuring itself after paint, a slower-loading panel
// further down) and move the target after the first scroll — so this keeps
// re-snapping to it, instantly rather than smoothly, for the rest of the
// watch window. ("Smoothly" would be wrong here even if only used once: an
// in-flight smooth-scroll animation keeps stepping toward its own
// by-then-stale endpoint and silently overwrites a later correction.)
const WATCH_TIMEOUT_MS = 5000;

// Shared by useScrollToTest/useScrollToMeeting below: reads `param` off the
// current route, watches the DOM for the first element whose `attr` matches
// its value (the target may not exist yet — the snapshot is still
// fetching), scrolls it into view, flags it with a highlight class, and
// calls `onMatch` (if given) once — e.g. WatchPage uses this to expand the
// row a CSS class alone can't open.
function useScrollToMatch(param: string, attr: string, onMatch?: (value: string) => void): void {
  const [searchParams] = useSearchParams();
  const value = searchParams.get(param);
  // Read through refs, not the effect's dependency array: `attr` is a
  // per-call-site constant and `onMatch` is typically a fresh closure every
  // render (WatchPage passes one inline) — depending on either would re-run
  // the scroll/highlight on every unrelated re-render instead of once per
  // `value` change.
  const attrRef = useRef(attr);
  attrRef.current = attr;
  const onMatchRef = useRef(onMatch);
  onMatchRef.current = onMatch;

  useEffect(() => {
    if (!value) return;

    const selector = `[${attrRef.current}="${value}"]`;
    let highlightTimer: number | undefined;
    let giveUpTimer: number | undefined;
    let resizeObserver: ResizeObserver | undefined;
    let mutationObserver: MutationObserver | undefined;

    const watch = (el: Element) => {
      onMatchRef.current?.(value);
      const snap = () => el.scrollIntoView({ behavior: "auto", block: "start" });
      snap();
      el.classList.add(HIGHLIGHT_CLASS);
      highlightTimer = window.setTimeout(() => el.classList.remove(HIGHLIGHT_CLASS), HIGHLIGHT_MS);

      resizeObserver = new ResizeObserver(snap);
      resizeObserver.observe(document.body);
      giveUpTimer = window.setTimeout(() => resizeObserver?.disconnect(), WATCH_TIMEOUT_MS);
    };

    const existing = document.querySelector(selector);
    if (existing) {
      watch(existing);
    } else {
      mutationObserver = new MutationObserver(() => {
        const el = document.querySelector(selector);
        if (el) {
          mutationObserver?.disconnect();
          watch(el);
        }
      });
      mutationObserver.observe(document.body, { childList: true, subtree: true });
      giveUpTimer = window.setTimeout(() => mutationObserver?.disconnect(), WATCH_TIMEOUT_MS);
    }

    return () => {
      mutationObserver?.disconnect();
      resizeObserver?.disconnect();
      window.clearTimeout(giveUpTimer);
      window.clearTimeout(highlightTimer);
    };
  }, [value]);
}

// Reads ?test=<id> off the current route, scrolls the element carrying a
// matching data-test-id into view, and flags it with a highlight class.
export function useScrollToTest(): void {
  useScrollToMatch("test", "data-test-id");
}

// Reads ?meeting=<id> off the current route, scrolls the matching
// data-meeting-id row into view, flags it, and calls `onMatch` with the
// numeric meeting id so the caller can expand it (WatchPage's rows are
// collapsed by default, unlike a scorecard/analysis row).
export function useScrollToMeeting(onMatch: (meetingId: number) => void): void {
  useScrollToMatch("meeting", "data-meeting-id", (v) => onMatch(Number(v)));
}
