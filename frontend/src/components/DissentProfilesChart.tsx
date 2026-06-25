import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell, ReferenceLine,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, DissenterProfile } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

function dissenterColor(profile: DissenterProfile): string {
  const r = profile.dissent_rate;
  if (profile.is_active) {
    // Active councillors: vivid palette
    if (r >= 0.30) return "#ef4444";
    if (r >= 0.20) return "#f59e0b";
    if (r >= 0.12) return "#3b82f6";
    return "#22c55e";
  }
  // Historical: muted
  if (r >= 0.30) return "#7f1d1d";
  if (r >= 0.20) return "#78350f";
  if (r >= 0.12) return "#1e3a5f";
  return "#14532d";
}

const CustomTooltip = ({ active, payload }: {
  active?: boolean;
  payload?: { payload: DissenterProfile & { pct: number } }[];
}) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{d.name}{d.is_active ? " ●" : ""}</p>
      <p style={{ color: "#f1f5f9" }}>
        Dissent rate: <strong>{d.pct}%</strong>
      </p>
      <p style={{ color: "#94a3b8" }}>
        {d.against_count} against / {d.total_votes_on_carried} votes on carried motions
      </p>
      {d.top_dissent_tags.length > 0 && (
        <p style={{ color: "#64748b", marginTop: 4 }}>
          Top topics: {d.top_dissent_tags.slice(0, 3).join(", ")}
        </p>
      )}
    </div>
  );
};

export function DissentProfilesChart() {
  const { data, loading, error } = useData(() => api.dissent());

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const chartData = data.profiles
    .filter((p) => p.total_votes_on_carried >= 50)
    .map((p) => ({
      ...p,
      shortName: p.name.split(" ").slice(-1)[0],
      pct: +(p.dissent_rate * 100).toFixed(1),
    }))
    // Show top 20 by dissent rate to keep the chart readable
    .slice(0, 20);

  const maxActive = chartData.filter((d) => d.is_active).reduce((m, d) => Math.max(m, d.dissent_rate), 0);
  const activeHighlight = chartData.find((d) => d.is_active && d.dissent_rate === maxActive);

  const chartHeight = Math.max(320, chartData.length * 30);

  return (
    <Card
      title="Councillor Independence: Dissent on Carried Motions"
      subtitle="% of votes cast against motions that still passed · ≥50 qualifying votes · ● = currently serving"
      valence="neutral"
    >
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 4, right: 48, bottom: 4, left: 88 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
          <XAxis type="number" domain={[0, 55]} unit="%" tick={{ fontSize: 11 }} />
          <YAxis
            type="category"
            dataKey="shortName"
            tick={{ fontSize: 11 }}
            width={84}
          />
          <ReferenceLine
            x={10}
            stroke="#334155"
            strokeDasharray="4 4"
            label={{ value: "10%", position: "top", fontSize: 10, fill: "#475569" }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Bar dataKey="pct" name="Dissent %" radius={[0, 3, 3, 0]}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={dissenterColor(entry)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {activeHighlight && (
        <div className="dissent-active-note">
          <span className="badge badge-blue">Current council</span>
          <span>
            {activeHighlight.name} is the current chamber's most independent voice at{" "}
            <strong>{(activeHighlight.dissent_rate * 100).toFixed(1)}%</strong> — mild by
            historical standards. David Berry (49%) and Kerry Smith (45%) in the early 2000s
            were far more willing to go against the tide.
          </span>
        </div>
      )}

      <p className="chart-note">
        "Dissent" = voted AGAINST a motion that the majority still CARRIED. Muted colours =
        historical (no longer serving). Bright colours = currently serving. Shows top 20 by
        dissent rate among those with ≥50 qualifying votes.
      </p>
    </Card>
  );
}
