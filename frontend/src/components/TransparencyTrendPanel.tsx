import {
  ComposedChart, Area, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceArea, ReferenceLine,
} from "recharts";
import { useData } from "../hooks/useData";
import { api } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

const CustomTooltip = ({ active, payload, label }: {
  active?: boolean;
  payload?: { payload: { total: number; confidential: number; confidential_pct: number } }[];
  label?: number;
}) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{label}</p>
      <p style={{ color: "#f87171" }}>Behind closed doors: <strong>{d.confidential_pct}%</strong></p>
      <p style={{ color: "#94a3b8" }}>{d.confidential} of {d.total} items confidential</p>
    </div>
  );
};

export function TransparencyTrendPanel() {
  const { data, loading, error } = useData(() => api.transparency());

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  // Drop years with tiny samples (< 50 items) — they swing wildly and mislead.
  const chartData = data.years.filter((y) => y.total >= 50);

  return (
    <Card
      title="Did the Council Go Dark?"
      subtitle="Share of decided items recorded as confidential, 1995–2026"
    >
      <div className="planning-hero-row">
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-recent">{data.pre_era_pct}%</span>
          <span className="planning-stat-label">confidential, 1995–2017 average</span>
        </div>
        <div className="planning-stat-arrow">→</div>
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-peak">{data.peak_pct}%</span>
          <span className="planning-stat-label">at the {data.peak_year} peak</span>
        </div>
        <div className="planning-stat-divider" />
        <div className="planning-stat">
          <span className="planning-stat-num">
            {data.category_totals.tenders
              ? `${Math.round(100 * data.category_totals.tenders.confidential / data.category_totals.tenders.total)}%`
              : "—"}
          </span>
          <span className="planning-stat-label">of all tenders ever, confidential</span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={chartData} margin={{ top: 8, right: 24, bottom: 4, left: 0 }}>
          <defs>
            <linearGradient id="confFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f87171" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#f87171" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} interval={3} />
          <YAxis unit="%" tick={{ fontSize: 11 }} width={40} />
          {/* The state-appointed Authorised Inquiry era */}
          <ReferenceArea x1={2018} x2={2021} fill="#f59e0b" fillOpacity={0.08}
            label={{ value: "Authorised Inquiry era", position: "insideTop", fontSize: 10, fill: "#f59e0b" }} />
          <ReferenceLine y={data.pre_era_pct} stroke="#475569" strokeDasharray="4 4"
            label={{ value: "two-decade norm", position: "insideBottomLeft", fontSize: 10, fill: "#64748b" }} />
          <Tooltip content={<CustomTooltip />} />
          <Area type="monotone" dataKey="confidential_pct" stroke="#f87171" strokeWidth={2.5}
            fill="url(#confFill)" name="Confidential %" />
          <Line type="monotone" dataKey="confidential_pct" stroke="#f87171" strokeWidth={0}
            dot={{ r: 2.5, fill: "#f87171" }} activeDot={{ r: 5 }} legendType="none" />
        </ComposedChart>
      </ResponsiveContainer>

      <p className="chart-note">
        Pools four item types that carry a confidentiality flag — tenders, "other items", delegated
        decisions and budget items — across meeting minutes. After holding at 1–4% for two decades,
        the confidential share quadrupled to a {data.peak_pct}% peak in {data.peak_year}, coinciding
        with the state-appointed Authorised Inquiry into the City of Cambridge. Years with fewer than
        50 recorded items excluded as too small to read.
      </p>
    </Card>
  );
}
