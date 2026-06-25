import { useData } from "../hooks/useData";
import { api } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

function CompareBar({ pct, color }: { pct: number; color: string }) {
  return (
    <div className="objection-bar-track">
      <div className="objection-bar-fill" style={{ width: `${pct}%`, background: color }} />
      <div className="objection-bar-refused" style={{ width: `${100 - pct}%` }} />
    </div>
  );
}

export function PlanningObjectionsPanel() {
  const { data, loading, error } = useData(() => api.planning());

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const { with_objection: w, no_objection: n } = data.objections;
  const diff = (n.approval_pct - w.approval_pct).toFixed(1);

  return (
    <Card
      title="Does Public Objection Change Outcomes?"
      subtitle="Community submissions vs planning decisions, 1995–2026"
      valence="neutral"
    >
      <div className="objection-grid">
        <div className="objection-box objection-box--opposed">
          <div className="objection-box-label">With community objections</div>
          <div className="objection-box-n">{w.n.toLocaleString()} applications</div>
          <div className="objection-box-pct">{w.approval_pct}%</div>
          <div className="objection-box-outcome">approved</div>
          <CompareBar pct={w.approval_pct} color="#f59e0b" />
          <div className="objection-bar-labels">
            <span style={{ color: "#f59e0b" }}>{w.approved} approved</span>
            <span style={{ color: "#64748b" }}>{w.refused} refused</span>
          </div>
        </div>

        <div className="objection-box objection-box--unopposed">
          <div className="objection-box-label">Without objections</div>
          <div className="objection-box-n">{n.n.toLocaleString()} applications</div>
          <div className="objection-box-pct">{n.approval_pct}%</div>
          <div className="objection-box-outcome">approved</div>
          <CompareBar pct={n.approval_pct} color="#22c55e" />
          <div className="objection-bar-labels">
            <span style={{ color: "#22c55e" }}>{n.approved} approved</span>
            <span style={{ color: "#64748b" }}>{n.refused} refused</span>
          </div>
        </div>
      </div>

      <div className="objection-callout">
        <span className="objection-callout-diff">{diff} pp</span>
        <span className="objection-callout-text">
          difference. Lodging a formal objection shifts the approval rate by only {diff} percentage
          points — council approves applications at nearly the same rate regardless of community opposition.
        </span>
      </div>

      <p className="chart-note">
        An application "has objections" if at least one community submission with position=object was
        recorded. Decided applications only (approved or refused).
      </p>
    </Card>
  );
}
