import { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell, LabelList,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, ObjectionDoseBucket, DoseApp } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";
import { DrillDown, SourceQuote } from "./DrillDown";

const LABELS: Record<string, string> = {
  "0": "No objectors",
  "1": "1 objector",
  "2-4": "2–4 objectors",
  "5+": "5 or more",
};

function doseColor(label: string): string {
  return { "0": "#475569", "1": "#f59e0b", "2-4": "#fb923c", "5+": "#f87171" }[label] ?? "#475569";
}

const CustomTooltip = ({ active, payload }: {
  active?: boolean;
  payload?: { payload: ObjectionDoseBucket & { name: string } }[];
}) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{d.name}</p>
      <p style={{ color: "var(--stat-r)" }}>Refused: <strong>{d.refusal_pct}%</strong></p>
      <p style={{ color: "var(--text-muted)" }}>{d.refused} refused of {d.n} decided</p>
      {d.n_shown > 0 && <p style={{ color: "var(--link)", fontSize: "0.75rem" }}>Click to inspect</p>}
    </div>
  );
};

function AppRow({ app }: { app: DoseApp }) {
  return (
    <div className="dose-app">
      <div className="dose-app-head">
        {app.reference && <span className="dose-app-ref">{app.reference}</span>}
        <span className="dose-app-obj">{app.n_objectors} objector{app.n_objectors !== 1 ? "s" : ""}</span>
        {app.outcome === "refused"
          ? <span className="dose-outcome-refused">Refused</span>
          : <span className="dose-outcome-approved">Approved</span>}
      </div>
      {app.address && <p className="dose-app-addr">{app.address}</p>}
      {app.description && <p className="dose-app-desc">{app.description}</p>}
      <SourceQuote quote={app.quote ?? null} />
    </div>
  );
}

export function ObjectionDosePanel() {
  const { data, loading, error } = useData(() => api.dose());
  const [selected, setSelected] = useState<string | null>(null);

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const chartData = data.buckets.map((b) => ({
    ...b,
    name: LABELS[b.label] ?? b.label,
  }));

  const lone = data.buckets.find((b) => b.label === "1");
  const many = data.buckets.find((b) => b.label === "5+");
  const none = data.buckets.find((b) => b.label === "0");

  function handleBarClick(entry: ObjectionDoseBucket) {
    if (!entry.n_shown) return;
    setSelected(selected === entry.label ? null : entry.label);
  }

  const selBucket = selected != null ? data.buckets.find((b) => b.label === selected) : null;

  return (
    <Card
      title="How Many Objectors Does It Take to Sink a Development?"
      subtitle="Refusal rate by number of community objections · decided applications, 1995–2026"
      valence="supportive"
      backTo="sc-dose"
    >
      <div className="planning-hero-row">
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-recent">{lone?.refusal_pct}%</span>
          <span className="planning-stat-label">refused with a single objector</span>
        </div>
        <div className="planning-stat-arrow">→</div>
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-peak">{many?.refusal_pct}%</span>
          <span className="planning-stat-label">refused once 5+ object</span>
        </div>
        <div className="planning-stat-divider" />
        <div className="planning-stat">
          <span className="planning-stat-num">{data.total_decided.toLocaleString()}</span>
          <span className="planning-stat-label">decided applications</span>
        </div>
      </div>

      <div className="objection-callout">
        <span className="objection-callout-diff">
          {many && none ? `${(many.refusal_pct / none.refusal_pct).toFixed(1)}×` : "—"}
        </span>
        <span className="objection-callout-text">
          A lone objection barely registers — refusal rises only from{" "}
          <strong>{none?.refusal_pct}%</strong> to <strong>{lone?.refusal_pct}%</strong>. But once{" "}
          <strong>five or more</strong> neighbours object, the refusal rate jumps to{" "}
          <strong>{many?.refusal_pct}%</strong>. It isn't the act of objecting that moves council —
          it's the <em>numbers</em>.
        </span>
      </div>

      <p className="section-heading" style={{ marginTop: 0 }}>
        Refusal rate by objection count
        <span className="section-hint"> — click a bar to inspect applications</span>
      </p>

      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData} margin={{ top: 24, right: 24, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 12 }} />
          <YAxis unit="%" domain={[0, 60]} tick={{ fontSize: 11 }} width={40} />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "var(--cursor)" }} />
          <Bar dataKey="refusal_pct" name="Refusal %" radius={[4, 4, 0, 0]}
            style={{ cursor: "pointer" }}
            onClick={(entry) => handleBarClick(entry as ObjectionDoseBucket)}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={doseColor(entry.label)} />
            ))}
            <LabelList dataKey="refusal_pct" position="top" formatter={(v) => `${v}%`}
              style={{ fill: "#cbd5e1", fontSize: 12 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {selBucket && (
        <DrillDown
          title={`${LABELS[selBucket.label] ?? selBucket.label} — applications`}
          subtitle={`${selBucket.n} decided · ${selBucket.refusal_pct}% refused${selBucket.n_shown < selBucket.n ? ` · showing ${selBucket.n_shown}` : ""}`}
          onClose={() => setSelected(null)}
        >
          {selBucket.apps.length === 0
            ? <p className="chart-note">No application details available.</p>
            : selBucket.apps.map((app, i) => <AppRow key={i} app={app} />)
          }
        </DrillDown>
      )}

      <p className="chart-note">
        Objections = community submissions recorded with position "object". Decided applications only
        (approved or refused). The high-objection bucket is small (n={many?.n}) so read it as
        directional, but the climb is monotonic. The most-opposed case on record — a proposed betting
        agency drawing 22 objectors — was refused.
      </p>
    </Card>
  );
}
