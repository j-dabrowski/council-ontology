import {
  ComposedChart, Bar, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceLine, Legend,
} from "recharts";
import { useData } from "../hooks/useData";
import { api } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

const CustomTooltip = ({ active, payload, label }: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: number;
}) => {
  if (!active || !payload?.length) return null;
  const rate = payload.find((p) => p.name === "Approval %");
  const vol = payload.find((p) => p.name === "Applications");
  return (
    <div className="tooltip">
      <p className="tooltip-title">{label}</p>
      {vol && <p style={{ color: "var(--text-faint)" }}>Applications before council: {vol.value}</p>}
      {rate && <p style={{ color: "var(--note)" }}>Approval rate: {rate.value}%</p>}
    </div>
  );
};

export function PlanningTrendChart() {
  const { data, loading, error } = useData(() => api.planning());

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  // Drop very recent years with tiny samples (< 10 decided) as they're noisy
  const chartData = data.trend
    .filter((r) => r.decided >= 10)
    .map((r) => ({
      year: r.year,
      "Approval %": r.approval_pct,
      "Applications": r.n_applications,
      decided: r.decided,
    }));

  const eligible = data.trend.filter((r) => r.decided >= 10);
  const peak = eligible.reduce((best, r) => r.approval_pct > best.approval_pct ? r : best, eligible[0]);
  const recent = [...eligible].sort((a, b) => b.year - a.year)[0];

  return (
    <Card
      title="Planning Approval Rate, 1995–2026"
      subtitle="Cambridge's shift from permissive to restrictive planning"
      valence="neutral"
    >
      <div className="planning-hero-row">
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-peak">{peak.approval_pct}%</span>
          <span className="planning-stat-label">peak approval ({peak.year})</span>
        </div>
        <div className="planning-stat-arrow">→</div>
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-recent">{recent.approval_pct}%</span>
          <span className="planning-stat-label">recent approval ({recent.year})</span>
        </div>
        <div className="planning-stat-divider" />
        <div className="planning-stat">
          <span className="planning-stat-num">{data.trend.reduce((s, r) => s + r.n_applications, 0).toLocaleString()}</span>
          <span className="planning-stat-label">applications across 30 years</span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={chartData} margin={{ top: 8, right: 48, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} interval={4} />
          <YAxis
            yAxisId="rate"
            domain={[40, 100]}
            unit="%"
            tick={{ fontSize: 11 }}
            width={38}
          />
          <YAxis
            yAxisId="vol"
            orientation="right"
            tick={{ fontSize: 11, fill: "#475569" }}
            width={40}
          />
          <ReferenceLine
            yAxisId="rate"
            y={80}
            stroke="var(--border)"
            strokeDasharray="4 4"
            label={{ value: "80%", position: "insideRight", fontSize: 10, fill: "#475569" }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            formatter={(value) => <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{value}</span>}
          />
          <Bar
            yAxisId="vol"
            dataKey="Applications"
            fill="#1e3a5f"
            radius={[2, 2, 0, 0]}
            name="Applications"
          />
          <Line
            yAxisId="rate"
            type="monotone"
            dataKey="Approval %"
            stroke="#f59e0b"
            strokeWidth={2.5}
            dot={false}
            activeDot={{ r: 5, fill: "#f59e0b" }}
            name="Approval %"
          />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Approval rate = decided applications (approved ÷ approved+refused). The 80% dashed line marks the 2000–2013 norm.
        Years with fewer than 10 decided applications excluded. The 2003–2013 era of 85–93% approval
        contrasts sharply with the post-2018 decline toward 60–72%.
      </p>
    </Card>
  );
}
