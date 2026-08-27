import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell, ReferenceLine, LabelList,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, ScorecardData, ScorecardTest, TestChart, CouncillorsData } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

const VALENCE_FILL: Record<string, string> = {
  supportive: "#4ade80", neutral: "#60a5fa", critical: "#f87171",
};
const HIGHLIGHT_FILL = "#fbbf24";

// Structural guardrail: a test's headline/verdict must never carry a named
// individual through this always-visible slot unnoticed — any valence, not
// just critical, since a supportive-valence test about the council can still
// contain an unflattering clause about one person (see docs/review, BLOCKING
// flag 4, 2026-08-22 pass 1). A hit is redacted in the rendered output itself
// (not just logged) — a console-only warning is invisible to anyone without
// devtools open, which is exactly the audience this guards.
function findNamedCouncillorsInText(text: string, councillorNames: string[]): string[] {
  return councillorNames.filter((name) => {
    const last = name.trim().split(/\s+/).slice(-1)[0];
    return last.length > 2 && text.includes(last);
  });
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function redactNamedCouncillors(text: string, names: string[]): string {
  if (!names.length) return text;
  const alternatives = names.flatMap((name) => {
    const last = name.trim().split(/\s+/).slice(-1)[0];
    return [escapeRegExp(name), escapeRegExp(last)];
  });
  const pattern = new RegExp(alternatives.join("|"), "g");
  return text.replace(pattern, "[named individual — flagged for review]");
}

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
 * Renders one already-resolved ScorecardTest: chart + headline + verdict +
 * meta, plus the named-individual guardrail. Pure presentational component —
 * where the test came from (the whole-corpus scorecard, a single-meeting
 * digest) is the caller's problem, not this one's, so this is what both
 * BatteryTestPanel (corpus-wide, fetches by testId) and DigestPage
 * (single-meeting, already has the full test list) render through.
 */
export function BatteryTestCard({ test: t, cllrData }: { test: ScorecardTest; cllrData: CouncillorsData | null }) {
  let flaggedNames: string[] = [];
  if (cllrData) {
    flaggedNames = findNamedCouncillorsInText(
      `${t.headline} ${t.verdict}`,
      Object.keys(cllrData.by_name)
    );
    if (flaggedNames.length) {
      console.error(
        `[scorecard guardrail] ${t.valence}-valence test "${t.test_id}" names ` +
        `${flaggedNames.join(", ")} in its headline/verdict — redacted in the rendered output ` +
        `pending review; see docs/review/editor/Editor_prompt.txt`
      );
    }
  }
  const headline = flaggedNames.length ? redactNamedCouncillors(t.headline, flaggedNames) : t.headline;
  const verdict = flaggedNames.length ? redactNamedCouncillors(t.verdict, flaggedNames) : t.verdict;

  return (
    <Card
      title={t.title}
      subtitle={t.question}
      valence={t.valence}
      backTo={t.detail_panel ? `sc-${t.detail_panel}` : undefined}
    >
      {flaggedNames.length > 0 && (
        <div className="sc-row-guardrail">
          ⚠ Named-individual claim flagged for editorial review — redacted pending sign-off
        </div>
      )}
      <div className={`bt-headline bt-${t.valence}`}>
        <span className="bt-grade">{t.grade}</span>
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
        <span className="sc-genre">{t.genre}</span>
        {" · "}{t.principle}
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
  const t: ScorecardTest | undefined = data.tests.find((x) => x.test_id === testId);
  if (!t) return <ErrorCard msg={`test ${testId} not found`} />;

  return <BatteryTestCard test={t} cllrData={cllrData} />;
}
