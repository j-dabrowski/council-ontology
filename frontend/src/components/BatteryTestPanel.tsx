import { useState } from "react";
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell, ReferenceLine, LabelList,
} from "recharts";
import { TestChart, CouncillorsData, evidenceForBatteryTest, type GenericBatteryEvidence } from "../api";
import { Card } from "./InterestsChart";
import { SeverityChip } from "./SeverityChip";
import { ObjectionResponse } from "./ObjectionResponse";
import { DrillDown, SourceQuote } from "./DrillDown";
import { CATEGORY_LABEL, type ResolvedTest } from "../registry/types";
import { RedactedText } from "../guardrail";
import { Principles } from "./Glossary";

const VALENCE_FILL: Record<string, string> = {
  supportive: "#4ade80", neutral: "#60a5fa", critical: "#f87171",
};
const HIGHLIGHT_FILL = "#fbbf24";

// Numeric axis tick labels for the generic battery panel had no
// tickFormatter/interval — recharts' bare `unit` prop just appends the
// unit string to whatever raw number it generates, which collides with
// its neighbours once the range needs many decimal places or a value runs
// into the thousands/millions (docs/uplift/migration/01-known-defects.md
// G-35, affects all 14 generic-fallback tests since they share this one
// component). Compact, unit-aware formatting instead of the raw number.
function formatAxisTick(value: number, unit: string): string {
  const abs = Math.abs(value);
  let num: string;
  if (abs >= 1_000_000) num = `${(value / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  else if (abs >= 1_000) num = `${(value / 1_000).toFixed(1).replace(/\.0$/, "")}k`;
  else if (Number.isInteger(value)) num = String(value);
  else num = value.toFixed(1);
  return `${num}${unit}`;
}

function ChartView({ chart, valence, onLabelClick }: {
  chart: TestChart; valence: string; onLabelClick?: (label: string) => void;
}) {
  const base = VALENCE_FILL[valence] ?? "#60a5fa";
  const unit = chart.unit ?? "";

  if (chart.kind === "line") {
    const pts = chart.points ?? [];
    // Chart-level onClick + activeLabel, not activeDot's own onClick — the
    // proven pattern TransparencyTrendPanel already ships (a documented
    // recharts mechanism), not an inferred activeDot argument shape this
    // recharts version's own types don't actually confirm carries a
    // payload at all.
    function handleChartClick(chartState: { activeLabel?: number | string | null }) {
      if (!onLabelClick || chartState?.activeLabel == null) return;
      onLabelClick(String(chartState.activeLabel));
    }
    return (
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={pts} margin={{ top: 8, right: 24, bottom: 4, left: 0 }}
          onClick={onLabelClick ? handleChartClick : undefined}
          style={onLabelClick ? { cursor: "pointer" } : undefined}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="x" tick={{ fontSize: 12 }} />
          <YAxis
            tick={{ fontSize: 12 }}
            width={52}
            tickFormatter={(v: number) => formatAxisTick(v, unit)}
          />
          <Tooltip
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6 }}
            formatter={(v?: number | string | readonly (number | string)[]) => [`${v ?? 0}${unit}`, ""]}
          />
          <Line type="monotone" dataKey="y" stroke={base} strokeWidth={2.5}
            dot={{ r: 2.5, fill: base }} activeDot={{ r: 6 }} />
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
        <XAxis
          type="number"
          tick={{ fontSize: 12 }}
          tickFormatter={(v: number) => formatAxisTick(v, unit)}
        />
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
        <Bar dataKey="value" radius={[0, 3, 3, 0]}
          style={onLabelClick ? { cursor: "pointer" } : undefined}
          onClick={onLabelClick
            ? (d: unknown) => onLabelClick(String((d as { label: string }).label))
            : undefined}>
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
 * Body-only generic renderer for a battery test with no bespoke component:
 * chart + verdict + meta, plus the named-individual guardrail. No Card, no
 * severity chip, no Objection/Response — the analysis page's shell supplies
 * those uniformly for every registered panel
 * (docs/frontend/SURFACE_PROJECTION_PLAN.md B.3). This is what
 * PANEL_COMPONENTS points the chart-only tests at.
 */
export function BatteryTestBody({ test: t, cllrData }: { test: ResolvedTest; cllrData: CouncillorsData | null }) {
  const councillorNames = cllrData ? Object.keys(cllrData.by_name) : [];

  // Evidence chain drill-down (docs/frontend/EVIDENCE_CHAIN_PLAN.md Step 6,
  // tests.<generator> group): most battery tests have no evidence file yet
  // (only threshold_gaming so far), so a click always attempts the fetch
  // and degrades to doing nothing — never an error state — when there's
  // nothing to show, rather than needing a registry flag to know in
  // advance which tests this works for.
  const [selected, setSelected] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<GenericBatteryEvidence | null>(null);
  const [evidenceTried, setEvidenceTried] = useState(false);

  function handleLabelClick(label: string) {
    setSelected((s) => (s === label ? null : label));
    if (!evidenceTried) {
      setEvidenceTried(true);
      evidenceForBatteryTest(t.id).then(setEvidence).catch(() => setEvidence(null));
    }
  }

  const selBucket = selected != null
    ? evidence?.buckets.find((b) => b.label === selected)
    : null;

  return (
    <>
      {/* "Not computable" reflects data_ok, not chart presence — a real,
          computed result can legitimately have no chart (e.g. a single-
          meeting point stat has nothing to trend), and showing the "not
          computable" message for that case would misreport a real n=0/n=20
          finding as a data gap. */}
      {t.data_ok && t.chart && (
        <ChartView chart={t.chart} valence={t.valence} onLabelClick={handleLabelClick} />
      )}
      {!t.data_ok && (
        <div className="bt-nodata">
          <span className="bt-nodata-mark">○</span> Not computable on this corpus.
        </div>
      )}

      {selBucket && selBucket.entries.length > 0 && (
        <DrillDown
          title={`${selBucket.label} — source records`}
          subtitle={`${selBucket.entries.length} shown`}
          onClose={() => setSelected(null)}
        >
          {selBucket.entries.map((entry, i) => (
            <div key={i} className="bt-evidence-row">
              <SourceQuote entry={entry} />
            </div>
          ))}
        </DrillDown>
      )}

      <p className="chart-note">
        <RedactedText text={t.verdict} names={councillorNames} testId={t.id} field="verdict" />
      </p>
      <p className="chart-note bt-meta">
        <span className="sc-genre">{CATEGORY_LABEL[t.category]}</span>
        <Principles list={t.principles} />
        {" · "}{t.question_technical}
        {t.n != null && <> · n&nbsp;=&nbsp;{t.n.toLocaleString()}</>}
        {t.base_rate && <> · {t.base_rate}</>}
        {t.era && <> · {t.era}</>}
      </p>
    </>
  );
}

/**
 * The card-wrapped form of BatteryTestBody — Card, severity chip and
 * Objection/Response, all in one call. WatchPage renders each meeting's
 * exceptions outside the analysis shell, so it still needs this wrapped
 * variant; the shell itself uses BatteryTestBody directly and supplies its
 * own Card.
 */
export function BatteryTestCard({ test: t, cllrData }: { test: ResolvedTest; cllrData: CouncillorsData | null }) {
  const councillorNames = cllrData ? Object.keys(cllrData.by_name) : [];

  return (
    <Card
      title={t.title_technical}
      finding={<RedactedText text={t.finding} names={councillorNames} testId={t.id} field="finding" />}
      valence={t.valence}
      backTo={t.id}
    >
      <div className={`bt-headline bt-${t.valence}`}>
        <SeverityChip severity={t.severity} />
      </div>
      <BatteryTestBody test={t} cllrData={cllrData} />
      {t.valence === "critical" && <ObjectionResponse test={t} />}
    </Card>
  );
}
