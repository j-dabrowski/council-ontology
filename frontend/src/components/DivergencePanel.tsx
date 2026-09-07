import { useState } from "react";
import { useData } from "../hooks/useData";
import { api, type OfficerRatificationPair } from "../api";
import { LoadingCard, ErrorCard } from "./InterestsChart";
import { SourceQuote } from "./DrillDown";
import { CATEGORY_LABEL, type ResolvedTest } from "../registry/types";

export function DivergencePanel({ test }: { test: ResolvedTest }) {
  const { data, loading, error } = useData(() => api.divergence());
  // The evidence chain (docs/frontend/EVIDENCE_CHAIN_PLAN.md Step 3), loaded
  // separately from the figures above: a missing/unpublished evidence file
  // (it's full-tier, so not every environment has it) degrades to the
  // 6-exception-only table below rather than blanking the whole panel.
  const { data: evidence } = useData(() => api.evidenceOfficerRatification());
  const [expanded, setExpanded] = useState<number | null>(null);

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const pct = data.compliance_rate != null
    ? `${(data.compliance_rate * 100).toFixed(0)}%`
    : "—";

  const yearRange = data.year_min && data.year_max
    ? `${data.year_min}–${data.year_max}`
    : "years unknown";

  function toggle(i: number) {
    setExpanded(expanded === i ? null : i);
  }

  // All 203 matched pairs, departures first — they are the finding; the
  // rest is the evidence the finding was tested against (EVIDENCE_CHAIN_
  // PLAN.md Step 5). undefined while evidence.json is still loading or
  // unavailable, in which case the fallback below renders instead.
  const pairs: OfficerRatificationPair[] | undefined = evidence
    ? [...evidence.pairs].sort((a, b) => Number(b.diverged) - Number(a.diverged))
    : undefined;

  return (
    <>
      <div className="divergence-hero">
        <span className="hero-number">{pct}</span>
        <span className="hero-label">
          of council motions followed officer recommendations
          <br />
          <span className="hero-sub">
            ({data.total_matched} agenda–minutes pairs matched · {yearRange} only — requires both agenda and minutes for same meeting)
          </span>
        </span>
      </div>

      {pairs ? (
        pairs.length > 0 && (
          <>
            <h3 className="section-heading">
              All matched pairs ({pairs.length})
              <span className="section-hint"> — click a row to expand; departures listed first</span>
            </h3>
            <table className="exception-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Motion</th>
                  <th>Outcome</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {pairs.map((p, i) => (
                  <>
                    <tr key={`row-${i}`}
                      style={{ cursor: "pointer" }}
                      onClick={() => toggle(i)}
                    >
                      <td className="date-cell">{p.meeting_date ?? "—"}</td>
                      <td>{p.title}</td>
                      <td>
                        <span className={`badge ${p.diverged ? "badge-red" : "badge-neutral"}`}>
                          {p.council_outcome ?? "—"}
                        </span>
                      </td>
                      <td>
                        <button className="exception-row-expand" onClick={(e) => { e.stopPropagation(); toggle(i); }}>
                          {expanded === i ? "▾" : "▸"}
                        </button>
                      </td>
                    </tr>
                    {expanded === i && (
                      <tr key={`detail-${i}`}>
                        <td colSpan={4} className="exception-detail">
                          <p className="exception-detail-label">Agenda motion (officer recommendation)</p>
                          <SourceQuote entry={p.agenda_motion} />
                          <p className="exception-detail-label">Minutes motion (council outcome)</p>
                          <SourceQuote entry={p.minutes_motion} />
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
            <p className="chart-note">
              The {data.diverged_count} departures (motions where council DEFERRED or LOST something
              officers had recommended) are listed first. The remaining {pairs.length - data.diverged_count}{" "}
              rows are every other matched pair — the population the {data.diverged_count} departures
              were found in, each inspectable down to its own verbatim minute quotes rather than taken
              on trust. Motion-text amendments (where council carried a modified version) are not yet
              detected.
            </p>
          </>
        )
      ) : (
        data.exceptions.length > 0 && (
          <>
            <h3 className="section-heading">
              Exceptions ({data.exceptions.length})
              <span className="section-hint"> — click a row to expand</span>
            </h3>
            <table className="exception-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Motion</th>
                  <th>Outcome</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.exceptions.map((ex, i) => (
                  <>
                    <tr key={`row-${i}`}
                      style={{ cursor: "pointer" }}
                      onClick={() => toggle(i)}
                    >
                      <td className="date-cell">{ex.meeting_date}</td>
                      <td>{ex.title}</td>
                      <td>
                        <span className="badge badge-red">{ex.council_outcome ?? "—"}</span>
                      </td>
                      <td>
                        <button className="exception-row-expand" onClick={(e) => { e.stopPropagation(); toggle(i); }}>
                          {expanded === i ? "▾" : "▸"}
                        </button>
                      </td>
                    </tr>
                    {expanded === i && (
                      <tr key={`detail-${i}`}>
                        <td colSpan={4} className="exception-detail">
                          {ex.officer_recommendation && (
                            <>
                              <p className="exception-detail-label">Officer recommendation</p>
                              <p className="exception-detail-text">{ex.officer_recommendation}</p>
                            </>
                          )}
                          {ex.motion_text && (
                            <>
                              <p className="exception-detail-label">Motion text (council outcome)</p>
                              <p className="exception-detail-text">{ex.motion_text}</p>
                            </>
                          )}
                          <SourceQuote quote={ex.quote ?? null} />
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
            <p className="chart-note">
              Exceptions are motions where council DEFERRED or LOST something officers had recommended.
              Motion-text amendments (where council carried a modified version) are not yet detected.
            </p>
          </>
        )
      )}
      <p className="chart-note bt-meta">
        <span className="sc-genre">{CATEGORY_LABEL[test.category]}</span>
        {" · "}{test.principles.join(" · ")}
        {" · "}{test.question_technical}
      </p>
    </>
  );
}
