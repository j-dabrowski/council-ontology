import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell, ReferenceLine, LabelList,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, ScorecardData, TestChart, CouncillorsData } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";
import { resolveTests } from "../registry";
import { CATEGORY_LABEL, type ResolvedTest } from "../registry/types";
import { findNamedCouncillorsInText, redactNamedCouncillors } from "../guardrail";

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
          <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="x" tick={{ fontSize: 12 }} />
          <YAxis unit={unit} tick={{ fontSize: 12 }} width={44} />
          <Tooltip
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6 }}
            formatter={(v?: number | string | readonly (number | string)[]) => [`${v ?? 0}${unit}`, ""]}
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
        <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" horizontal={false} />
        <XAxis type="number" unit={unit} tick={{ fontSize: 12 }} />
        <YAxis type="category" dataKey="label" tick={{ fontSize: 12 }} width={130} />
        <Tooltip
          cursor={{ fill: "var(--cursor)" }}
          contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6 }}
          formatter={(v?: number | string | readonly (number | string)[]) => [`${v ?? 0}${unit}`, ""]}
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
            formatter={(v: string | number | boolean | null | undefined) => `${v ?? 0}${unit}`} style={{ fill: "#94a3b8", fontSize: 11 }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/**
 * Renders one already-resolved ResolvedTest: chart + headline + verdict +
 * meta, plus the named-individual guardrail. Pure presentational component —
 * where the test came from (the whole-corpus scorecard, a single-meeting
 * digest) is the caller's problem, not this one's, so this is what both
 * BatteryTestPanel (corpus-wide, fetches by testId) and DigestPage
 * (single-meeting, already has the full test list) render through.
 */
export function BatteryTestCard({ test: t, cllrData }: { test: ResolvedTest; cllrData: CouncillorsData | null }) {
  let flaggedNames: string[] = [];
  if (cllrData) {
    flaggedNames = findNamedCouncillorsInText(
      `${t.finding} ${t.verdict}`,
      Object.keys(cllrData.by_name)
    );
    if (flaggedNames.length) {
      console.error(
        `[scorecard guardrail] ${t.valence}-valence test "${t.id}" names ` +
        `${flaggedNames.join(", ")} in its headline/verdict — redacted in the rendered output ` +
        `pending review; see docs/review/editor/Editor_prompt.txt`
      );
    }
  }
  const headline = flaggedNames.length ? redactNamedCouncillors(t.finding, flaggedNames) : t.finding;
  const verdict = flaggedNames.length ? redactNamedCouncillors(t.verdict, flaggedNames) : t.verdict;

  return (
    <Card
      title={t.title_technical}
      subtitle={t.question_technical}
      valence={t.valence}
      backTo={t.detail_panel ? `sc-${t.detail_panel}` : undefined}
    >
      {flaggedNames.length > 0 && (
        <div className="sc-row-guardrail">
          ⚠ Named-individual claim flagged for editorial review — redacted pending sign-off
        </div>
      )}
      <div className={`bt-headline bt-${t.valence}`}>
        <span className="bt-grade">{t.severity}</span>
        <span className="bt-headline-text">{headline}</span>
      </div>

      {/* "Not computable" reflects data_ok, not chart presence — a real,
          computed result can legitimately have no chart (e.g. a single-
          meeting point stat has nothing to trend), and showing the "not
          computable" message for that case would misreport a real n=0/n=20
          finding as a data gap. */}
      {t.data_ok && t.chart && <ChartView chart={t.chart} valence={t.valence} />}
      {!t.data_ok && (
        <div className="bt-nodata">
          <span className="bt-nodata-mark">○</span> Not computable on this corpus.
        </div>
      )}

      <p className="chart-note">{verdict}</p>
      <p className="chart-note bt-meta">
        <span className="sc-genre">{CATEGORY_LABEL[t.category]}</span>
        {" · "}{t.principles.join(" · ")}
        {t.n != null && <> · n&nbsp;=&nbsp;{t.n.toLocaleString()}</>}
        {t.base_rate && <> · {t.base_rate}</>}
        {t.era && <> · {t.era}</>}
      </p>
    </Card>
  );
}

/**
 * Generic panel for a battery test that has no bespoke component. Reads the
 * already-loaded scorecard snapshot, finds the test by id, and renders it via
 * BatteryTestCard. One component serves every "simple" test, so a new battery
 * test gets a panel for free.
 */
export function BatteryTestPanel({ testId }: { testId: string }) {
  const { data, loading, error } = useData<ScorecardData>(() => api.scorecard());
  const { data: cllrData } = useData<CouncillorsData>(() => api.councillors());
  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;
  const t = resolveTests(data.tests).find((x) => x.id === testId);
  if (!t) return <ErrorCard msg={`test ${testId} not found`} />;

  return <BatteryTestCard test={t} cllrData={cllrData} />;
}
