import { useData } from "../hooks/useData";
import { api, WatchData } from "../api";
import { watchHref } from "../registry/anchors";

// docs/frontend/WATCH_FEED_PLAN.md Step 7 — a strip above the overview
// panel reading the first (newest) record of the published watch.json,
// linking through to its row on /watch. A strip, not a panel: on load
// failure or an empty feed (no `council draft`/`publish` has run yet) this
// renders nothing at all rather than an ErrorCard — a fault here would
// deface the home page above everything else on it.
export function LatestMeetingStrip() {
  const { data } = useData<WatchData>(() => api.watch());
  const latest = data?.meetings[0];
  if (!latest) return null;

  const date = new Date(`${latest.meeting_date}T00:00:00`).toLocaleDateString("en-AU", {
    day: "numeric", month: "long", year: "numeric",
  });

  const facts: string[] = [latest.meeting_type];
  facts.push(`${latest.tests.within_baseline} of ${latest.tests.run} tests within baseline`);
  if (latest.exceptions_withheld > 0) {
    facts.push(`+${latest.exceptions_withheld} withheld from public feed`);
  }
  if (latest.provenance.validation_status) {
    facts.push(latest.provenance.validation_status);
  }

  return (
    <a className="latest-meeting-strip" href={watchHref(latest.meeting_id)}>
      <span className="latest-meeting-label">Latest meeting</span>
      <span className="latest-meeting-date">{date}</span>
      <span className="latest-meeting-stats">
        {latest.counts.items} items, {latest.counts.motions} motions,{" "}
        {latest.tests.exceptions} exception{latest.tests.exceptions === 1 ? "" : "s"}
      </span>
      <span className="latest-meeting-facts">{facts.join(" · ")}</span>
      <span className="latest-meeting-link">View in History →</span>
    </a>
  );
}
