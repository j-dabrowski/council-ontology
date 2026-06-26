import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid
} from "recharts";
import { useData } from "../hooks/useData";
import { api } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

export function EngagementChart() {
  const { data, loading, error } = useData(() => api.engagement());

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const chartData = data.map((d) => ({
    year: d.year,
    "Public questions": d.public_questions,
    "Deputations": d.deputations,
    "Petitions": d.petitions,
  }));

  return (
    <Card title="Public Engagement by Year" subtitle="Questions, deputations and petitions at meetings" valence="neutral" backTo="sc-engagement">
      <ResponsiveContainer width="100%" height={340}>
        <BarChart data={chartData} margin={{ top: 8, right: 24, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="year" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6 }}
            labelStyle={{ color: "#f1f5f9" }}
          />
          <Legend />
          <Bar dataKey="Public questions" fill="#3b82f6" radius={[3, 3, 0, 0]} />
          <Bar dataKey="Deputations" fill="#8b5cf6" radius={[3, 3, 0, 0]} />
          <Bar dataKey="Petitions" fill="#ec4899" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Public engagement across the full 30-year corpus (1995–2026).
      </p>
    </Card>
  );
}
