import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, Cell
} from "recharts";
import { useData } from "../hooks/useData";
import { api } from "../api";
import { ValenceChip } from "./ValenceChip";

const COLORS = {
  financial: "#ef4444",
  impartiality: "#94a3b8",
  proximity: "#f59e0b",
  other: "#cbd5e1",
};

export function InterestsChart() {
  const { data, loading, error } = useData(() => api.interests());

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const chartData = data.map((s) => ({
    name: s.councillor_name.split(" ").slice(-1)[0], // family name only on axis
    fullName: s.councillor_name,
    financial: s.by_type.financial ?? 0,
    impartiality: s.by_type.impartiality ?? 0,
    proximity: s.by_type.proximity ?? 0,
    other: s.by_type.other ?? 0,
    total: s.total,
  }));

  const maxFinancial = Math.max(...chartData.map((d) => d.financial));

  const chartHeight = Math.max(300, chartData.length * 28);

  return (
    <Card title="Interest Declarations by Councillor" subtitle="1995–2026" valence="neutral">
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 4, right: 32, bottom: 4, left: 64 }}
        >
          <XAxis type="number" tick={{ fontSize: 12 }} />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 12 }} width={60} />
          <Tooltip
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const row = chartData.find((d) => d.name === label);
              return (
                <div className="tooltip">
                  <p className="tooltip-title">{row?.fullName}</p>
                  {payload.map((p, i) => (
                    <p key={i} style={{ color: p.fill as string }}>
                      {String(p.dataKey)}: {String(p.value)}
                    </p>
                  ))}
                </div>
              );
            }}
          />
          <Legend />
          <Bar dataKey="impartiality" stackId="a" fill={COLORS.impartiality} name="Impartiality" />
          <Bar dataKey="proximity" stackId="a" fill={COLORS.proximity} name="Proximity" />
          <Bar dataKey="other" stackId="a" fill={COLORS.other} name="Other" />
          <Bar dataKey="financial" stackId="a" fill={COLORS.financial} name="Financial" radius={[0, 2, 2, 0]}>
            {chartData.map((entry, i) => (
              <Cell
                key={i}
                fill={entry.financial === maxFinancial && maxFinancial > 0 ? "#dc2626" : COLORS.financial}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Financial declarations indicate a direct pecuniary interest — a different category to routine impartiality notices.
      </p>
    </Card>
  );
}

// ── Shared primitives ──────────────────────────────────────────────────────────

export function Card({
  title,
  subtitle,
  valence,
  valenceLabel,
  backTo,
  children,
}: {
  title: string;
  subtitle?: string;
  valence?: "supportive" | "neutral" | "critical";
  valenceLabel?: string;
  backTo?: string; // scorecard row anchor id (e.g. "sc-declared") to link back up
  children: React.ReactNode;
}) {
  return (
    <div className="card">
      <div className="card-header">
        <div className="card-header-titles">
          <h2 className="card-title">{title}</h2>
          {subtitle && <span className="card-subtitle">{subtitle}</span>}
        </div>
        <div className="card-header-meta">
          {backTo && (
            <a className="card-back" href={`#${backTo}`} title="Back to this test on the scorecard">
              ↑ Scorecard
            </a>
          )}
          {valence && <ValenceChip valence={valence} label={valenceLabel} />}
        </div>
      </div>
      {children}
    </div>
  );
}

export function LoadingCard() {
  return (
    <div className="card loading-card">
      <div className="spinner" />
    </div>
  );
}

export function ErrorCard({ msg }: { msg: string | null }) {
  return (
    <div className="card error-card">
      <p>Failed to load: {msg ?? "unknown error"}</p>
    </div>
  );
}
