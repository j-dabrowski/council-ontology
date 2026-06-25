import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell, LabelList,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, TenureProfile } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

const HIST_ORDER = ["<2y", "2-5y", "5-10y", "10-15y", "15y+"];

const LeaderTooltip = ({ active, payload }: {
  active?: boolean;
  payload?: { payload: TenureProfile }[];
}) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{d.name}{d.is_active ? " ●" : ""}</p>
      <p style={{ color: "#60a5fa" }}><strong>{d.years}</strong> years on record</p>
      <p style={{ color: "#94a3b8" }}>{d.first} → {d.last} · {d.n_votes} votes cast</p>
    </div>
  );
};

export function TenurePanel() {
  const { data, loading, error } = useData(() => api.tenure());

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const leaders = data.profiles.slice(0, 12).map((p) => ({
    ...p,
    shortName: p.name,
  }));
  const leaderHeight = Math.max(300, leaders.length * 28);

  const longServers = data.histogram["15y+"] ?? 0;
  const top = data.profiles[0];

  const hist = HIST_ORDER.map((k) => ({ bucket: k, count: data.histogram[k] ?? 0 }));

  return (
    <Card
      title="Lifers and Blow-ins — How Long Do Councillors Last?"
      subtitle="Length of service from first to last recorded vote · councillors with ≥20 votes"
      valence="neutral"
      backTo="sc-tenure"
    >
      <div className="planning-hero-row">
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-peak">{top?.years}y</span>
          <span className="planning-stat-label">longest serving ({top?.name})</span>
        </div>
        <div className="planning-stat-divider" />
        <div className="planning-stat">
          <span className="planning-stat-num">{longServers}</span>
          <span className="planning-stat-label">have served 15+ years</span>
        </div>
        <div className="planning-stat-divider" />
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-recent">{data.median_years}y</span>
          <span className="planning-stat-label">median tenure</span>
        </div>
      </div>

      <div className="objection-callout">
        <span className="objection-callout-diff">{longServers}/{data.n_councillors}</span>
        <span className="objection-callout-text">
          of councillors with a real voting record have sat for <strong>15 years or more</strong> —
          the chamber is dominated by long-servers, not newcomers. {top?.name} has been voting on
          Cambridge matters for over <strong>{Math.floor(top?.years ?? 0)} years</strong>.
        </span>
      </div>

      <p className="section-heading">Longest-serving councillors</p>
      <ResponsiveContainer width="100%" height={leaderHeight}>
        <BarChart data={leaders} layout="vertical" margin={{ top: 4, right: 48, bottom: 4, left: 92 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
          <XAxis type="number" unit="y" tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="shortName" tick={{ fontSize: 11 }} width={120} />
          <Tooltip content={<LeaderTooltip />} cursor={{ fill: "#1e293b55" }} />
          <Bar dataKey="years" name="Years" radius={[0, 3, 3, 0]}>
            {leaders.map((entry, i) => (
              <Cell key={i} fill={entry.is_active ? "#60a5fa" : "#475569"} />
            ))}
            <LabelList dataKey="years" position="right" formatter={(v) => `${v}y`}
              style={{ fill: "#94a3b8", fontSize: 11 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <p className="section-heading">Distribution of service length</p>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={hist} margin={{ top: 16, right: 24, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
          <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} width={28} allowDecimals={false} />
          <Tooltip cursor={{ fill: "#1e293b55" }}
            contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 6 }} />
          <Bar dataKey="count" name="Councillors" fill="#8b5cf6" radius={[3, 3, 0, 0]}>
            <LabelList dataKey="count" position="top" style={{ fill: "#cbd5e1", fontSize: 11 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <p className="chart-note">
        Tenure approximated by the span between a councillor's first and last recorded vote (the
        councillor-terms table is too sparse to use directly), so it slightly understates anyone
        whose service predates 1995. Blue = still active (voted in the last 18 months); grey = past
        member. Based on {data.n_councillors} councillors with at least 20 recorded votes.
      </p>
    </Card>
  );
}
