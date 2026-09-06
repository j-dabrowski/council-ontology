import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

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

export function analysisHref(testId: string): string {
  return `#/analysis?test=${encodeURIComponent(testId)}`;
}

export function scorecardHref(testId: string): string {
  return `#/?test=${encodeURIComponent(testId)}`;
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

// Reads ?test=<id> off the current route, scrolls the element carrying a
// matching data-test-id into view, and flags it with a highlight class.
export function useScrollToTest(): void {
  const [searchParams] = useSearchParams();
  const testId = searchParams.get("test");

  useEffect(() => {
    if (!testId) return;

    const selector = `[data-test-id="${testId}"]`;
    let highlightTimer: number | undefined;
    let giveUpTimer: number | undefined;
    let resizeObserver: ResizeObserver | undefined;
    let mutationObserver: MutationObserver | undefined;

    const watch = (el: Element) => {
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
  }, [testId]);
}
