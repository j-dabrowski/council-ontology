import { useParams } from "react-router-dom";
import { useData } from "../hooks/useData";
import { api, RatingData, ScorecardData } from "../api";

// docs/frontend/MAP_PAGE_PLAN.md Phase 2 — the overall governance rating,
// full-width above the fold. Under INTERACTIVITY.md's hard rule, every word
// here except the fixed English scaffolding ("of", "decisive", "tests",
// "critical", the count labels) comes from the `data` prop: band/band_label/
// band_reason are config-sourced strings (config/rating.json) arriving
// through the snapshot, never typed as council-specific prose. No council
// name, era label or corpus span appears in this file.
//
// Decision 3 (settled 2026-09-15): no 0–100 score, no percentage, anywhere
// on this band. `critical_share` stays in the snapshot for an auditor but is
// never rendered as a number here — magnitude is the counts phrased as a
// ratio ("N of M decisive tests critical"), composed from n_critical/
// n_decisive exactly like LatestMeetingStrip already composes "N of M tests
// within baseline" — never a typed sentence.
function reasonText(data: RatingData): string {
  if (data.band_reason !== "base") return data.band_reason;
  const noun = data.n_decisive === 1 ? "test" : "tests";
  return `${data.n_critical} of ${data.n_decisive} decisive ${noun} critical`;
}

// Mirrors ScorecardPanel's deriveSummary() cross-check: rating.json and
// scorecard.json's summary.rating are written by the same compute_rating()
// call to two destinations (src/cli.py) — they must never disagree. Runs
// whenever both snapshots have loaded; harmless (console-only) either way.
function checkAgreesWithScorecard(rating: RatingData, scorecard: ScorecardData | null) {
  if (!scorecard) return;
  const other = scorecard.summary.rating;
  (Object.keys(rating) as (keyof RatingData)[]).forEach((key) => {
    if (rating[key] !== other[key]) {
      console.error(
        `RatingBand: rating.json.${key}=${rating[key]} disagrees with ` +
        `scorecard.json summary.rating.${key}=${other[key]}`
      );
    }
  });
}

export function RatingBand() {
  const { data } = useData<RatingData>(() => api.rating());
  const { data: scorecard } = useData<ScorecardData>(() => api.scorecard());
  const { council } = useParams<{ council: string }>();
  // No LoadingCard/ErrorCard here, same call LatestMeetingStrip makes: a
  // full-width band failing to load shouldn't deface the page above
  // everything else on it — it just doesn't render.
  if (!data) return null;
  checkAgreesWithScorecard(data, scorecard);

  return (
    <div className={`rating-band rating-band-${data.band}`}>
      <div className="rating-band-main">
        <span className="rating-band-swatch" aria-hidden="true" />
        <span className="rating-band-label">{data.band_label}</span>
        <span className="rating-band-reason">{reasonText(data)}</span>
      </div>
      <div className="rating-band-counts">
        <span className="rating-band-count rating-band-count-supportive">
          {data.n_supportive} supportive
        </span>
        <span className="rating-band-count rating-band-count-neutral">
          {data.n_neutral} neutral
        </span>
        <span className="rating-band-count rating-band-count-critical">
          {data.n_critical} critical
        </span>
        <span className="rating-band-count rating-band-count-nodata">
          {data.n_not_computable} not computable
        </span>
      </div>
      <a className="rating-band-link" href={`#/c/${council}/analysis`}>How this is calculated →</a>
    </div>
  );
}
