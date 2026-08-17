import { useState } from "react";
import { useData } from "../hooks/useData";
import { api } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";
import { SourceQuote } from "./DrillDown";

export function DivergencePanel() {
  const { data, loading, error } = useData(() => api.divergence());
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

  return (
    <Card title="Officer Recommendation Compliance" subtitle={yearRange} valence="critical" backTo="sc-divergence">
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

      {data.exceptions.length > 0 && (
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
          <p className="chart-note">
            A hostile reader would say: if officers get their way {pct} of the time, "debate" is
            theatre and the substantive decision is made upstream, in who writes the recommendation.
            In the council's defence: exceptions are a genuine minority, not an absent check — this
            council departed from an officer recommendation {data.diverged_count} times across{" "}
            {data.total_matched} matched items, and every one of those departures is listed and
            inspectable above, not buried inside an otherwise-unanimous-looking vote. Divergence is
            rare, but real.
          </p>
        </>
      )}
    </Card>
  );
}
