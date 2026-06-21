import { useData } from "../hooks/useData";
import { api } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

export function DivergencePanel() {
  const { data, loading, error } = useData(() => api.divergence());

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const pct = data.compliance_rate != null
    ? `${(data.compliance_rate * 100).toFixed(0)}%`
    : "—";

  return (
    <Card title="Officer Recommendation Compliance" subtitle="2024–present">
      <div className="divergence-hero">
        <span className="hero-number">{pct}</span>
        <span className="hero-label">
          of council motions followed officer recommendations
          <br />
          <span className="hero-sub">({data.total_matched} agenda–minutes pairs matched)</span>
        </span>
      </div>

      {data.exceptions.length > 0 && (
        <>
          <h3 className="section-heading">Exceptions ({data.exceptions.length})</h3>
          <table className="exception-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Motion</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {data.exceptions.map((ex, i) => (
                <tr key={i}>
                  <td className="date-cell">{ex.meeting_date}</td>
                  <td>{ex.title}</td>
                  <td>
                    <span className="badge badge-red">{ex.council_outcome ?? "—"}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="chart-note">
            Exceptions are motions where council DEFERRED or LOST something officers had recommended.
            Motion-text amendments (where council carried a modified version) are not yet detected.
          </p>
        </>
      )}
    </Card>
  );
}
