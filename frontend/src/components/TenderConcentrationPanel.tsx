import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, ContractorTotal } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

const fmtM = (n: number) => `$${(n / 1e6).toFixed(1)}M`;

// Strip company suffixes for a cleaner axis label.
function shortName(name: string): string {
  return name
    .replace(/\b(Pty\.?|Ltd\.?|P\/L|Limited|Proprietary)\b/gi, "")
    .replace(/\s+/g, " ")
    .trim();
}

const CustomTooltip = ({ active, payload }: {
  active?: boolean;
  payload?: { payload: ContractorTotal }[];
}) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{d.name}</p>
      <p style={{ color: "#f59e0b" }}>{fmtM(d.total_amount)} awarded</p>
      <p style={{ color: "#94a3b8" }}>
        across {d.n_awards} tender{d.n_awards === 1 ? "" : "s"}
      </p>
    </div>
  );
};

export function TenderConcentrationPanel() {
  const { data, loading, error } = useData(() => api.tenders());

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const chartData = data.contractors.map((c) => ({
    ...c,
    label: shortName(c.name),
  }));

  const chartHeight = Math.max(320, chartData.length * 30);
  const top = chartData[0];
  const redactedPct = Math.round((data.redacted_amount / data.total_amount) * 100);

  return (
    <Card
      title="Where Cambridge's Tender Money Went"
      subtitle="Awarded contracts with a disclosed value · 1995–2026"
      valence="neutral"
      backTo="sc-tenders"
    >
      <div className="planning-hero-row">
        <div className="planning-stat">
          <span className="planning-stat-num">{fmtM(data.total_amount)}</span>
          <span className="planning-stat-label">tendered across {data.total_awards} awards</span>
        </div>
        <div className="planning-stat-divider" />
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-peak">{fmtM(data.named_amount)}</span>
          <span className="planning-stat-label">to {data.distinct_named} named contractors</span>
        </div>
        <div className="planning-stat-divider" />
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-recent">{fmtM(data.redacted_amount)}</span>
          <span className="planning-stat-label">recipient redacted / unnamed</span>
        </div>
      </div>

      <div className="objection-callout">
        <span className="objection-callout-diff">{Math.round(data.top10_share * 100)}%</span>
        <span className="objection-callout-text">
          Just <strong>ten firms</strong> captured {Math.round(data.top10_share * 100)}% of the{" "}
          {fmtM(data.named_amount)} that went to named contractors — led by{" "}
          <strong>{top?.name}</strong> at {fmtM(top?.total_amount ?? 0)}. A further{" "}
          <strong>{redactedPct}%</strong> of all tendered dollars ({fmtM(data.redacted_amount)})
          was awarded under confidential "Respondent" reports where the winner is not named in the minutes.
        </span>
      </div>

      <p className="section-heading">Top {chartData.length} named contractors by total awarded value</p>
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 4, right: 64, bottom: 4, left: 132 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
          <XAxis
            type="number"
            tick={{ fontSize: 11 }}
            tickFormatter={(v) => `$${(v / 1e6).toFixed(0)}M`}
          />
          <YAxis type="category" dataKey="label" tick={{ fontSize: 10.5 }} width={128} />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "#1e293b55" }} />
          <Bar dataKey="total_amount" name="Awarded" radius={[0, 3, 3, 0]}>
            {chartData.map((_, i) => (
              <Cell key={i} fill={i === 0 ? "#f59e0b" : i < 5 ? "#fbbf24" : "#60a5fa"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <p className="chart-note">
        Spelling and punctuation variants of the same firm are merged (e.g. "R J Vincent" and
        "RJ Vincent"). Amounts are the contract values recorded in the minutes; some large works
        span multiple awards. Roughly a third of all tendered dollars sit behind confidential
        tender reports and so cannot be attributed to a named contractor here.
      </p>
      <p className="chart-note">
        <strong>The credit, stated plainly:</strong> concentration is the nature of big civil
        contracts, not evidence of capture. The {fmtM(data.named_amount)} of named work is spread
        across <strong>{data.distinct_named} contractors</strong>, and on three independent integrity
        tests — threshold-gaming, entrenched incumbents, repeat-player advantage — this record comes
        back <strong>clean</strong>. The redaction share is a transparency issue worth watching, but
        the procurement record itself reads as a <strong>good-governance strength</strong>. Severity:
        a demonstrated strength on integrity, with a transparency Observation on redaction · CIPFA
        principles F, G.
      </p>
    </Card>
  );
}
