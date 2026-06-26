import { useState } from "react";
import {
  ComposedChart, Area, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceArea, ReferenceLine,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, TransparencyYear, ConfidentialItem } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";
import { DrillDown, SourceQuote } from "./DrillDown";

const KIND_LABELS: Record<string, string> = {
  tender: "Tender",
  other_item: "Item",
  delegated_decision: "Delegated decision",
  budget_item: "Budget item",
};

const CustomTooltip = ({ active, payload, label }: {
  active?: boolean;
  payload?: { payload: TransparencyYear }[];
  label?: number;
}) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{label}</p>
      <p style={{ color: "var(--stat-r)" }}>Behind closed doors: <strong>{d.confidential_pct}%</strong></p>
      <p style={{ color: "var(--text-muted)" }}>{d.confidential} of {d.total} items confidential</p>
      {d.confidential > 0 && (
        <p style={{ color: "var(--link)", fontSize: "0.75rem" }}>Click to inspect</p>
      )}
    </div>
  );
};

function ConfItemRow({ item }: { item: ConfidentialItem }) {
  return (
    <div className="conf-item">
      <div className="conf-item-head">
        <span className="conf-kind">{KIND_LABELS[item.kind] ?? item.kind}</span>
        {item.amount != null && (
          <span className="conf-amount">${item.amount.toLocaleString()}</span>
        )}
        {item.date && <span className="conf-date">{item.date}</span>}
      </div>
      {item.description && (
        <p className="conf-desc">{item.description}</p>
      )}
      <SourceQuote quote={item.quote ?? null} />
    </div>
  );
}

export function TransparencyTrendPanel() {
  const { data, loading, error } = useData(() => api.transparency());
  const [selected, setSelected] = useState<number | null>(null);

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const chartData = data.years.filter((y) => y.total >= 50);

  function handleChartClick(chartState: { activeLabel?: number | string | null }) {
    if (chartState?.activeLabel == null) return;
    const year = Number(chartState.activeLabel);
    const yr = data!.years.find((y) => y.year === year);
    if (yr && yr.confidential > 0) {
      setSelected(selected === year ? null : year);
    }
  }

  const selYear = selected != null ? data.years.find((y) => y.year === selected) : null;

  return (
    <Card
      title="Did the Council Go Dark?"
      subtitle="Share of decided items recorded as confidential, 1995–2026"
      valence="critical"
      backTo="sc-transparency"
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

      <p className="section-heading" style={{ marginTop: 0 }}>
        Confidential share per year
        <span className="section-hint"> — click a year to inspect items</span>
      </p>

      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart
          data={chartData}
          margin={{ top: 8, right: 24, bottom: 4, left: 0 }}
          onClick={handleChartClick}
          style={{ cursor: "pointer" }}
        >
          <defs>
            <linearGradient id="confFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f87171" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#f87171" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} interval={3} />
          <YAxis unit="%" tick={{ fontSize: 11 }} width={40} />
          <ReferenceArea x1={2018} x2={2021} fill="#f59e0b" fillOpacity={0.08}
            label={{ value: "Authorised Inquiry era", position: "insideTop", fontSize: 10, fill: "#f59e0b" }} />
          <ReferenceLine y={data.pre_era_pct} stroke="var(--text-faint)" strokeDasharray="4 4"
            label={{ value: "two-decade norm", position: "insideBottomLeft", fontSize: 10, fill: "var(--text-dim)" }} />
          <Tooltip content={<CustomTooltip />} />
          <Area type="monotone" dataKey="confidential_pct" stroke="#f87171" strokeWidth={2.5}
            fill="url(#confFill)" name="Confidential %" />
          <Line type="monotone" dataKey="confidential_pct" stroke="#f87171" strokeWidth={0}
            dot={{ r: 2.5, fill: "#f87171" }}
            activeDot={{ r: 6, fill: "#f87171", cursor: "pointer" }}
            legendType="none" />
        </ComposedChart>
      </ResponsiveContainer>

      {selYear && (
        <DrillDown
          title={`${selYear.year} — confidential items`}
          subtitle={`${selYear.confidential} of ${selYear.total} items (${selYear.confidential_pct}%)${selYear.n_shown < selYear.confidential ? ` · showing ${selYear.n_shown}` : ""}`}
          onClose={() => setSelected(null)}
        >
          {selYear.items.length === 0
            ? <p className="chart-note">No item details available for this year.</p>
            : selYear.items.map((item, i) => <ConfItemRow key={i} item={item} />)
          }
        </DrillDown>
      )}

      <p className="chart-note">
        Pools four item types that carry a confidentiality flag — tenders, "other items", delegated
        decisions and budget items — across meeting minutes. After holding at 1–4% for two decades,
        the confidential share quadrupled to a {data.peak_pct}% peak in {data.peak_year}, coinciding
        with the state-appointed Authorised Inquiry into the City of Cambridge. Years with fewer than
        50 recorded items excluded as too small to read.
      </p>
      <p className="chart-note">
        <strong>In the council's defence:</strong> the {data.pre_era_pct}% two-decade baseline is a
        genuinely <em>open</em> record, and an Authorised Inquiry legitimately generates confidential
        business — legal advice and personnel matters under active investigation — so a spike in those
        exact years is partly expected, and it <em>reverted</em> afterward. The data concedes that; what
        it still raises is the <em>scale</em> (one in six decisions closed at the peak, 62% of that year's
        tenders) and the timing. Read in the round: a transparent council that went unusually quiet during
        its own inquiry, not a habitually secretive one. Severity: Governance-concern against a strong
        baseline · Nolan Openness, CIPFA principle B.
      </p>
    </Card>
  );
}
