import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell, ReferenceLine, LabelList,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, ScorecardData, ScorecardTest, TestChart } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

const VALENCE_FILL: Record<string, string> = {
  supportive: "#4ade80", neutral: "#60a5fa", critical: "#f87171",
};
const HIGHLIGHT_FILL = "#fbbf24";

function ChartView({ chart, valence }: { chart: TestChart; valence: string }) {
  const base = VALENCE_FILL[valence] ?? "#60a5fa";
  const unit = chart.unit ?? "";

  if (chart.kind === "line") {
    const pts = chart.points ?? [];
    return (
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={pts} margin={{ top: 8, right: 24, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
          <XAxis dataKey="x" tick={{ fontSize: 12 }} />
          <YAxis unit={unit} tick={{ fontSize: 12 }} width={44} />
          <Tooltip
            contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 6 }}
            formatter={(v: number) => [`${v}${unit}`, ""]}
          />
          <Line type="monotone" dataKey="y" stroke={base} strokeWidth={2.5}
            dot={{ r: 2.5, fill: base }} activeDot={{ r: 5 }} />
        </LineChart>
      </ResponsiveContainer>
    );
  }

  const bars = chart.bars ?? [];
  const height = Math.max(260, bars.length * 30);
  const refAfter = chart.refline?.after;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={bars} layout="vertical" margin={{ top: 4, right: 56, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
        <XAxis type="number" unit={unit} tick={{ fontSize: 12 }} />
        <YAxis type="category" dataKey="label" tick={{ fontSize: 12 }} width={130} />
        <Tooltip
          cursor={{ fill: "#1e293b55" }}
          contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 6 }}
          formatter={(v: number) => [`${v}${unit}`, ""]}
        />
        {refAfter && (
          <ReferenceLine
            y={refAfter}
            stroke="#f87171"
            strokeDasharray="4 4"
            label={{ value: chart.refline?.label, position: "right", fontSize: 10, fill: "#f87171" }}
          />
        )}
        <Bar dataKey="value" radius={[0, 3, 3, 0]}>
          {bars.map((b, i) => (
            <Cell key={i} fill={b.highlight ? HIGHLIGHT_FILL : base} />
          ))}
          <LabelList dataKey="value" position="right"
            formatter={(v: number) => `${v}${unit}`} style={{ fill: "#94a3b8", fontSize: 11 }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/**
 * Generic panel for a battery test that has no bespoke component. Reads the
 * already-loaded scorecard snapshot, finds the test by id, and renders its chart
 * + headline + verdict + meta. One component serves every "simple" test, so a
 * new battery test gets a panel for free.
 */
export function BatteryTestPanel({ testId }: { testId: string }) {
  const { data, loading, error } = useData<ScorecardData>(() => api.scorecard());
  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;
  const t: ScorecardTest | undefined = data.tests.find((x) => x.test_id === testId);
  if (!t) return <ErrorCard msg={`test ${testId} not found`} />;

  return (
    <Card
      title={t.title}
      subtitle={t.question}
      valence={t.valence}
      backTo={t.detail_panel ? `sc-${t.detail_panel}` : undefined}
    >
      <div className={`bt-headline bt-${t.valence}`}>
        <span className="bt-grade">{t.grade}</span>
        <span className="bt-headline-text">{t.headline}</span>
      </div>

      {t.data_ok && t.chart ? (
        <ChartView chart={t.chart} valence={t.valence} />
      ) : (
        <div className="bt-nodata">
          <span className="bt-nodata-mark">○</span> Not computable on this corpus.
        </div>
      )}

      <p className="chart-note">{t.verdict}</p>
      <p className="chart-note bt-meta">
        <span className="sc-genre">{t.genre}</span>
        {" · "}{t.principle}
        {t.n != null && <> · n&nbsp;=&nbsp;{t.n.toLocaleString()}</>}
        {t.base_rate && <> · {t.base_rate}</>}
        {t.era && <> · {t.era}</>}
      </p>
    </Card>
  );
}
