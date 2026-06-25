import { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell, ReferenceLine,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, RecusalProfile, DeclarationDetail } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";
import { DrillDown, SourceQuote } from "./DrillDown";

const TYPE_LABEL: Record<string, string> = {
  financial: "Financial", proximity: "Proximity",
  impartiality: "Impartiality", other: "Other",
};

function DeclarationRow({ d }: { d: DeclarationDetail }) {
  const t = d.interest_type ?? "other";
  return (
    <div className={`decl-row${d.must_leave ? " decl-mustleave" : ""}`}>
      <div className="decl-row-head">
        <span className={`decl-type decl-type-${t}`}>
          {TYPE_LABEL[t] ?? "Declared"}
          {d.must_leave && <span className="decl-mustleave-tag"> · must leave</span>}
        </span>
        <span className="decl-date">{d.date}{d.item ? ` · item ${d.item}` : ""}</span>
        <span className="decl-action">{d.action}</span>
      </div>
      {d.title && <div className="decl-title">{d.title}</div>}
      <div className="decl-what">{d.what || <em>no description recorded</em>}</div>
      <SourceQuote quote={d.quote} />
    </div>
  );
}

// Green = steps out most of the time, red = stays and votes most of the time.
function recusalColor(p: RecusalProfile): string {
  const r = p.recusal_rate;
  if (r >= 0.6) return "#22c55e";
  if (r >= 0.3) return "#84cc16";
  if (r >= 0.1) return "#f59e0b";
  return "#f87171";
}

const CustomTooltip = ({ active, payload }: {
  active?: boolean;
  payload?: { payload: RecusalProfile & { pct: number } }[];
}) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const stayed = d.declared_votes - d.recused;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{d.name}{d.is_active ? " ●" : ""}</p>
      <p style={{ color: "#f1f5f9" }}>
        Stepped out on <strong>{d.pct}%</strong> of declared items
      </p>
      <p style={{ color: "#94a3b8" }}>
        Recused {d.recused} · stayed and voted {stayed} · {d.declared_votes} declared in total
      </p>
    </div>
  );
};

export function ConflictRecusalPanel() {
  const { data, loading, error } = useData(() => api.declared());
  const [selected, setSelected] = useState<string | null>(null);

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const selectedProfile = selected
    ? data.profiles.find((p) => p.name === selected) ?? null
    : null;

  const chartData = data.profiles
    .map((p) => ({
      ...p,
      shortName: p.name.split(" ").slice(-1)[0] || p.name,
      pct: +(p.recusal_rate * 100).toFixed(0),
    }));

  const chartHeight = Math.max(320, chartData.length * 30);

  // How much more likely is a recusal once an interest is declared?
  const factor = data.baseline_recusal_pct > 0
    ? Math.round(data.declared_recusal_pct / data.baseline_recusal_pct)
    : null;

  return (
    <Card
      title="Declaring a Conflict — Do Councillors Step Out, or Vote Anyway?"
      subtitle="Behaviour on votes where the councillor declared an interest · 1995–2026"
      valence="critical"
      backTo="sc-declared"
    >
      <div className="planning-hero-row">
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-recent">{data.baseline_recusal_pct}%</span>
          <span className="planning-stat-label">step out on a normal vote</span>
        </div>
        <div className="planning-stat-arrow">→</div>
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-peak">{data.declared_recusal_pct}%</span>
          <span className="planning-stat-label">step out when they declare a conflict</span>
        </div>
        <div className="planning-stat-divider" />
        <div className="planning-stat">
          <span className="planning-stat-num">{data.declared_total.toLocaleString()}</span>
          <span className="planning-stat-label">declared-interest votes on record</span>
        </div>
      </div>

      <div className="objection-callout">
        <span className="objection-callout-diff">{factor ? `${factor}×` : "—"}</span>
        <span className="objection-callout-text">
          Declaring an interest makes a councillor about <strong>{factor}× more likely</strong> to
          recuse — yet they still stay in the chamber and vote roughly{" "}
          <strong>three times out of four</strong>. And when they do vote, they side against the
          motion <em>less</em> often than usual ({data.declared_against_pct}% vs{" "}
          {data.baseline_against_pct}%): a declared-interest vote leans toward letting the matter through.
        </span>
      </div>

      <p className="section-heading">
        Who steps out, and who stays — councillors with ≥8 declared votes
        <span className="section-hint"> · click a bar to see the actual interests they declared</span>
      </p>
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 4, right: 48, bottom: 4, left: 92 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
          <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="shortName" tick={{ fontSize: 11 }} width={88} />
          <ReferenceLine
            x={data.declared_recusal_pct}
            stroke="#475569"
            strokeDasharray="4 4"
            label={{ value: "chamber avg", position: "top", fontSize: 10, fill: "#64748b" }}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "#1e293b55" }} />
          <Bar
            dataKey="pct"
            name="Recusal %"
            radius={[0, 3, 3, 0]}
            cursor="pointer"
            onClick={(entry: { name?: string }) => entry?.name && setSelected(entry.name)}
          >
            {chartData.map((entry, i) => (
              <Cell key={i} fill={recusalColor(entry)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {selectedProfile && (
        <DrillDown
          title={`${selectedProfile.name} — declared interests`}
          subtitle={`${selectedProfile.declarations.length} on record · stepped out of ${selectedProfile.recused} of ${selectedProfile.declared_votes} (${Math.round(selectedProfile.recusal_rate * 100)}%)`}
          onClose={() => setSelected(null)}
        >
          {selectedProfile.declarations.length === 0 && (
            <p className="chart-note">No itemised declarations extracted for this councillor.</p>
          )}
          {selectedProfile.declarations.map((d, i) => (
            <DeclarationRow key={i} d={d} />
          ))}
        </DrillDown>
      )}

      <p className="chart-note">
        "Recusal" = recorded ABSENT on an item where the councillor declared an interest — i.e. they
        left the room rather than vote. Green = usually steps out; red = usually stays and votes.
        The spread is stark: some councillors recuse on the clear majority of their declared items,
        others have declared a conflict dozens of times and never once left the chamber.
      </p>
      <p className="chart-note">
        <strong>In the council's defence:</strong> the first limb of the safeguard plainly works —
        declaring an interest lifts recusal about {factor}×, so disclosure is real, not cosmetic, and
        many of these declarations are lawful "impartiality" interests the member is *entitled* to stay
        and vote on. The data concedes that. What it still raises is the *manage* limb: staying and
        voting three times out of four leaves the identify–disclose–<strong>manage</strong> chain
        breaking at the last link. Severity: Governance-concern · Nolan Integrity, Objectivity.
      </p>
    </Card>
  );
}
