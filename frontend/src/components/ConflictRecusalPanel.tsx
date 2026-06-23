import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell, ReferenceLine,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, RecusalProfile } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

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

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

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

      <p className="section-heading">Who steps out, and who stays — councillors with ≥8 declared votes</p>
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
          <Bar dataKey="pct" name="Recusal %" radius={[0, 3, 3, 0]}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={recusalColor(entry)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <p className="chart-note">
        "Recusal" = recorded ABSENT on an item where the councillor declared an interest — i.e. they
        left the room rather than vote. Green = usually steps out; red = usually stays and votes.
        The spread is stark: some councillors recuse on the clear majority of their declared items,
        others have declared a conflict dozens of times and never once left the chamber.
      </p>
    </Card>
  );
}
