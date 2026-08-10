import { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell, LabelList, ReferenceLine,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, MayorContest, MayoralMotion } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";
import { DrillDown, SourceQuote, Reveal } from "./DrillDown";
import { CouncillorLink, CouncillorTick } from "./CouncillorModal";

const MayorTooltip = ({ active, payload }: {
  active?: boolean;
  payload?: { payload: MayorContest }[];
}) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{d.name}</p>
      <p style={{ color: "var(--stat-r)" }}><strong>{d.contest_pct}%</strong> of their motions drew dissent</p>
      <p style={{ color: "var(--text-muted)" }}>{d.contested} contested of {d.carried} carried</p>
      {d.n_shown > 0 && <p style={{ color: "var(--link)", fontSize: "0.75rem" }}>Click to inspect</p>}
    </div>
  );
};

function MotionRow({ m }: { m: MayoralMotion }) {
  return (
    <div className="mayor-motion">
      <div className="mayor-motion-head">
        <span className="mayor-motion-date">{m.date}</span>
        <span className="mayor-motion-votes">
          {m.votes_for != null ? `${m.votes_for}–${m.votes_against ?? 0}` : ""}
        </span>
      </div>
      {m.title && <p className="mayor-motion-title">{m.title}</p>}
      <SourceQuote quote={m.quote ?? null} />
    </div>
  );
}

export function MayoralAgendaPanel() {
  const { data, loading, error } = useData(() => api.mayoral());
  const [selected, setSelected] = useState<string | null>(null);

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const chartData = data.per_mayor.map((m) => ({ ...m, shortName: m.name }));
  const height = Math.max(220, chartData.length * 42);

  // Highest- and lowest-contested mayoralties, for the worked example below —
  // computed from data, never hardcoded (must hold for any dataset this loads).
  const byContest = [...data.per_mayor].sort((a, b) => b.contest_pct - a.contest_pct);
  const mostContested = byContest[0] ?? null;
  const leastContested = byContest[byContest.length - 1] ?? null;

  function handleBarClick(entry: MayorContest) {
    if (!entry.n_shown) return;
    setSelected(selected === entry.name ? null : entry.name);
  }

  const selMayor = selected != null
    ? data.per_mayor.find((m) => m.name === selected)
    : null;

  return (
    <Card
      title="Does the Council Fall in Line Behind the Mayor?"
      subtitle="Dissent on motions moved by the sitting Mayor vs everyone else · 1999–2026"
      valence="supportive"
      backTo="sc-mayoral"
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

      <p className="section-heading">
        Share of each Mayor's carried motions that drew dissent
        <span className="section-hint"> — click a bar to inspect motions</span>
      </p>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 56, bottom: 4, left: 92 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" horizontal={false} />
          <XAxis type="number" unit="%" domain={[0, 30]} tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="name" width={120}
            tick={({ x, y, payload }: { x: number | string; y: number | string; payload: { value: string } }) => (
              <CouncillorTick x={x} y={y} payload={payload} />
            )} />
          <ReferenceLine x={data.other_contest_pct} stroke="#475569" strokeDasharray="4 4"
            label={{ value: "backbench avg", position: "top", fontSize: 10, fill: "#64748b" }} />
          <Tooltip content={<MayorTooltip />} cursor={{ fill: "var(--cursor)" }} />
          <Bar dataKey="contest_pct" name="Contested %" radius={[0, 3, 3, 0]}
            style={{ cursor: "pointer" }}
            onClick={(entry) => handleBarClick(entry as unknown as MayorContest)}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.contest_pct >= data.mayor_contest_pct ? "#f87171" : "#fb923c"} />
            ))}
            <LabelList dataKey="contest_pct" position="right" formatter={(v) => `${v}%`}
              style={{ fill: "#94a3b8", fontSize: 11 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {selMayor && (
        <DrillDown
          title={<><CouncillorLink name={selMayor.name} /> — contested carried motions</>}
          subtitle={`${selMayor.contested} contested of ${selMayor.carried} carried${selMayor.n_shown < selMayor.contested ? ` · showing ${selMayor.n_shown} most recent` : ""}`}
          onClose={() => setSelected(null)}
        >
          {selMayor.motions.length === 0
            ? <p className="chart-note">No motion details available.</p>
            : selMayor.motions.map((m, i) => <MotionRow key={i} m={m} />)
          }
        </DrillDown>
      )}

      <p className="chart-note">
        "Contested" = a carried motion that drew at least one AGAINST vote. The mayoral effect is far
        from uniform — click a bar above to inspect any individual mayoralty. Only mayors with dated
        terms (1999 onward) and ≥10 carried motions are shown; earlier mayors fall into the backbench
        comparison.
        {mostContested && leastContested && mostContested.name !== leastContested.name && (
          <> <Reveal label="the most- and least-contested mayoralties">
            it is concentrated in <CouncillorLink name={mostContested.name} />'s
            term ({mostContested.contest_pct}% contested), while{" "}
            <CouncillorLink name={leastContested.name} />'s motions passed almost as quietly as the
            backbench ({leastContested.contest_pct}%).
          </Reveal></>
        )}
      </p>
      <p className="chart-note">
        <strong>Read as a strength:</strong> a chamber that votes against its own Mayor <em>more</em>
        than against a backbencher is the opposite of chair capture — dissent is recorded freely and
        the most powerful member earns no deference at the gavel. That is Accountability and
        Objectivity demonstrably upheld. Severity: a good-governance strength (no chair capture) ·
        Nolan Accountability, Objectivity.
      </p>
    </Card>
  );
}
