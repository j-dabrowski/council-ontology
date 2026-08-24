import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend
} from "recharts";
import { useData } from "../hooks/useData";
import { api } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";
import { Reveal } from "./DrillDown";

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
    <Card title="Contestation Rate by Year" subtitle="% of carried motions with ≥1 dissenting vote" valence="neutral">
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData} margin={{ top: 8, right: 24, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="year" tick={{ fontSize: 12 }} />
          <YAxis yAxisId="left" unit="%" tick={{ fontSize: 12 }} domain={[0, 20]} />
          <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12 }} />
          <Tooltip
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6 }}
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
      <Reveal label="see the most contested motion per year">
        <h3 className="section-heading" style={{ marginTop: 12 }}>Most contested motion per year</h3>
        <div className="contested-list">
          {data.contestation.map((r) => (
            <div key={r.year} className="contested-row">
              <span className="contested-year">{r.year}</span>
              <span className="contested-title">
                {r.most_contested[0] ?? "—"}
                {r.most_contested[0] && (
                  <span style={{ color: "var(--text-muted)" }}>
                    {" "}({r.total_with_dissent} of {r.total_carried} motions had any dissent that year)
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
      </Reveal>
    </Card>
  );
}
