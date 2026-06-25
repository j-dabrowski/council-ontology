import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from "recharts";
import { useData } from "../hooks/useData";
import { api } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

export function DissentCoalitionsPanel() {
  const { data, loading, error } = useData(() => api.dissent());

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const topCoalition = data.coalitions[0];

  // Topic chart: top 14 tags by contestation rate, min 25 motions
  // Recharts horizontal bar: data[0] = top row.
  // Backend returns descending order, so slice top 14 and use as-is —
  // highest-rate tag (advocacy 39%) appears at the top of the chart.
  const tagData = data.by_tag
    .filter((t) => t.total_carried >= 25)
    .slice(0, 14)
    .map((t) => ({
      tag: t.tag,
      pct: +(t.contestation_rate * 100).toFixed(1),
      total: t.total_carried,
    }));

  return (
    <Card
      title="Opposition Coalitions & Contested Topics"
      subtitle="Who voted against the same carried motions · what topics split the chamber"
      valence="neutral"
    >
      {topCoalition && (
        <div className="coalition-hero">
          <span className="coalition-count">{topCoalition.shared_dissent}</span>
          <span className="coalition-text">
            times <strong>{topCoalition.name_a.split(" ").slice(-1)[0]}</strong> &amp;{" "}
            <strong>{topCoalition.name_b.split(" ").slice(-1)[0]}</strong> voted against
            the same carried motion — the chamber's tightest opposition bloc
          </span>
        </div>
      )}

      <h3 className="section-heading">Top opposition pairs</h3>
      <table className="exception-table">
        <thead>
          <tr>
            <th>Councillor A</th>
            <th>Councillor B</th>
            <th style={{ textAlign: "right" }}>Shared dissent votes</th>
          </tr>
        </thead>
        <tbody>
          {data.coalitions.slice(0, 10).map((c, i) => (
            <tr key={i}>
              <td>{c.name_a}</td>
              <td>{c.name_b}</td>
              <td style={{ textAlign: "right", color: "#f59e0b", fontWeight: 600 }}>
                {c.shared_dissent}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 className="section-heading" style={{ marginTop: 24 }}>
        Most contested topics
      </h3>
      <p className="chart-note" style={{ marginTop: 0, marginBottom: 8 }}>
        % of carried motions with ≥1 dissenting vote, by topic tag
      </p>
      <ResponsiveContainer width="100%" height={Math.max(200, tagData.length * 22)}>
        <BarChart
          data={tagData}
          layout="vertical"
          margin={{ top: 0, right: 48, bottom: 0, left: 100 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
          <XAxis type="number" domain={[0, 45]} unit="%" tick={{ fontSize: 10 }} />
          <YAxis type="category" dataKey="tag" tick={{ fontSize: 10 }} width={96} />
          <Tooltip
            contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 6, fontSize: 12 }}
            formatter={(v, _name, entry) => [
              `${v}% (${(entry?.payload as { total?: number })?.total ?? "?"} motions)`,
              "Contestation rate",
            ]}
          />
          <Bar dataKey="pct" fill="#8b5cf6" radius={[0, 3, 3, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Advocacy (39%) and confidential/personnel matters (22–27%) are more contested than
        planning, because they involve sensitive decisions without the usual procedural scripts.
        Minutes only.
      </p>
    </Card>
  );
}
