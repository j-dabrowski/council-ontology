import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell, LabelList, ReferenceLine,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, MayorContest } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

const MayorTooltip = ({ active, payload }: {
  active?: boolean;
  payload?: { payload: MayorContest }[];
}) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{d.name}</p>
      <p style={{ color: "#f87171" }}><strong>{d.contest_pct}%</strong> of their motions drew dissent</p>
      <p style={{ color: "#94a3b8" }}>{d.contested} contested of {d.carried} carried</p>
    </div>
  );
};

export function MayoralAgendaPanel() {
  const { data, loading, error } = useData(() => api.mayoral());

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const chartData = data.per_mayor.map((m) => ({
    ...m,
    shortName: m.name,
  }));
  const height = Math.max(220, chartData.length * 42);

  return (
    <Card
      title="Does the Council Fall in Line Behind the Mayor?"
      subtitle="Dissent on motions moved by the sitting Mayor vs everyone else · 1999–2026"
    >
      <div className="planning-hero-row">
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-recent">{data.other_contest_pct}%</span>
          <span className="planning-stat-label">backbench motions drew dissent</span>
        </div>
        <div className="planning-stat-arrow">→</div>
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-peak">{data.mayor_contest_pct}%</span>
          <span className="planning-stat-label">mayoral motions drew dissent</span>
        </div>
        <div className="planning-stat-divider" />
        <div className="planning-stat">
          <span className="planning-stat-num">{data.mayor_carried_pct}%</span>
          <span className="planning-stat-label">of mayoral motions carried (vs {data.other_carried_pct}%)</span>
        </div>
      </div>

      <div className="objection-callout">
        <span className="objection-callout-diff">{data.contest_factor}×</span>
        <span className="objection-callout-text">
          The opposite of a rubber stamp. When the Mayor personally moves a motion it is about{" "}
          <strong>{data.contest_factor}× more likely to split the chamber</strong> than a backbench
          motion — and slightly <em>less</em> likely to pass. The Mayor's gavel is a lightning rod,
          not a guarantee.
        </span>
      </div>

      <p className="section-heading">Share of each Mayor's carried motions that drew dissent</p>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 56, bottom: 4, left: 92 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
          <XAxis type="number" unit="%" domain={[0, 30]} tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="shortName" tick={{ fontSize: 11 }} width={120} />
          <ReferenceLine x={data.other_contest_pct} stroke="#475569" strokeDasharray="4 4"
            label={{ value: "backbench avg", position: "top", fontSize: 10, fill: "#64748b" }} />
          <Tooltip content={<MayorTooltip />} cursor={{ fill: "#1e293b55" }} />
          <Bar dataKey="contest_pct" name="Contested %" radius={[0, 3, 3, 0]}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.contest_pct >= data.mayor_contest_pct ? "#f87171" : "#fb923c"} />
            ))}
            <LabelList dataKey="contest_pct" position="right" formatter={(v) => `${v}%`}
              style={{ fill: "#94a3b8", fontSize: 11 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <p className="chart-note">
        "Contested" = a carried motion that drew at least one AGAINST vote. The mayoral effect is far
        from uniform: it is concentrated in the Anderton and Shannon mayoralties (the latter spanning
        the turbulent 2015–2023 era), while Simon Withers's motions passed almost as quietly as the
        backbench. Only mayors with dated terms (1999 onward) and ≥10 carried motions are shown;
        earlier mayors fall into the backbench comparison.
      </p>
    </Card>
  );
}
