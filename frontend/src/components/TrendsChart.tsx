import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend
} from "recharts";
import { useData } from "../hooks/useData";
import { api } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

export function ContestationChart() {
  const { data, loading, error } = useData(() => api.trends());

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const chartData = data.contestation.map((r) => ({
    year: r.year,
    "Contestation %": +(r.contestation_rate * 100).toFixed(1),
    "Total motions": r.total_carried,
  }));

  return (
    <Card title="Contestation Rate by Year" subtitle="% of carried motions with ≥1 dissenting vote">
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData} margin={{ top: 8, right: 24, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="year" tick={{ fontSize: 12 }} />
          <YAxis yAxisId="left" unit="%" tick={{ fontSize: 12 }} domain={[0, 20]} />
          <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12 }} />
          <Tooltip
            contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 6 }}
            labelStyle={{ color: "#f1f5f9" }}
          />
          <Legend />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="Contestation %"
            stroke="#f59e0b"
            strokeWidth={2}
            dot={{ r: 5 }}
          />
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="Total motions"
            stroke="#64748b"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Contestation rate across the full 30-year corpus (1995–2026).
      </p>
      <h3 className="section-heading">Most contested motion per year</h3>
      <div className="contested-list">
        {data.contestation.map((r) => (
          <div key={r.year} className="contested-row">
            <span className="contested-year">{r.year}</span>
            <span className="contested-title">{r.most_contested[0] ?? "—"}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
