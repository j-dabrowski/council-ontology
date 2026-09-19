import { useData } from "../hooks/useData";
import { api, ScorecardData, CouncillorsData } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";
import { ValenceChip } from "./ValenceChip";
import { SeverityChip } from "./SeverityChip";
import { resolveTests } from "../registry";
import { groupByCategory } from "../registry/grouping";
import { CATEGORY_LABEL, type ResolvedTest } from "../registry/types";
import { RedactedText } from "../guardrail";
import { analysisHref, useScrollToTest } from "../registry/anchors";
import { Principles } from "./Glossary";

// Mirrors src/analysis/tests.py's battery_summary(): "not computable" comes
// from data_ok, not valence, since a data_ok:false row's own valence is
// still "neutral" (TEST_REGISTRY_PLAN.md B.6) — bucketing on valence alone
// would double-count it as both neutral and not-computable.
function deriveSummary(tests: ResolvedTest[]) {
  return {
    n_supportive: tests.filter((t) => t.data_ok && t.valence === "supportive").length,
    n_neutral: tests.filter((t) => t.data_ok && t.valence === "neutral").length,
    n_critical: tests.filter((t) => t.data_ok && t.valence === "critical").length,
    n_not_computable: tests.filter((t) => !t.data_ok).length,
  };
}

function TestRow({ t, councillorNames }: { t: ResolvedTest; councillorNames: string[] }) {
  return (
    <div
      className={`sc-row sc-${t.valence}${t.data_ok ? "" : " sc-nodata"}`}
      data-test-id={t.id}
    >
      <div className="sc-row-flag">
        <ValenceChip valence={t.valence} notComputable={!t.data_ok} />
      </div>
      <div className="sc-row-main">
        <div className="sc-row-head">
          <span className="sc-row-title">{t.title_technical}</span>
          <SeverityChip severity={t.severity} />
        </div>
        <div className="sc-row-headline">
          <RedactedText text={t.finding} names={councillorNames} testId={t.id} field="finding" />
        </div>
        <div className="sc-row-verdict">
          <RedactedText text={t.verdict} names={councillorNames} testId={t.id} field="verdict" />
        </div>
        <div className="sc-row-meta">
          <span className="sc-genre">{CATEGORY_LABEL[t.category]}</span>
          <span className="sc-principle"><Principles list={t.principles} /></span>
          {t.n != null && <span className="sc-n">n&nbsp;=&nbsp;{t.n.toLocaleString()}</span>}
          {t.era && <span className="sc-era">{t.era}</span>}
          {t.has_deep_dive && (
            <a className="sc-detail" href={analysisHref(t.id)}>↓ jump to full panel</a>
          )}
        </div>
      </div>
    </div>
  );
}

export function ScorecardPanel() {
  const { data, loading, error } = useData<ScorecardData>(() => api.scorecard());
  const { data: cllrData } = useData<CouncillorsData>(() => api.councillors());
  useScrollToTest();
  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;
  const councillorNames = cllrData ? Object.keys(cllrData.by_name) : [];

  const resolvedTests = resolveTests(data.tests);
  const groups = groupByCategory(resolvedTests);

  const s = deriveSummary(resolvedTests);
  (Object.keys(s) as (keyof typeof s)[]).forEach((key) => {
    if (s[key] !== data.summary[key]) {
      console.error(
        `ScorecardPanel: derived ${key}=${s[key]} disagrees with data.summary.${key}=${data.summary[key]}`
      );
    }
  });

  return (
    <Card
      title="The Council Scorecard — a Standard Test Battery"
      subtitle="Every standard governance test this corpus can run, flagged supportive / neutral / critical · the same battery is meant to run on any council"
    >
      <div className="sc-summary">
        <div className="sc-summary-item sc-supportive">
          <span className="sc-summary-num">{s.n_supportive}</span>
          <span className="sc-summary-label">supportive — the council does well</span>
        </div>
        <div className="sc-summary-item sc-neutral">
          <span className="sc-summary-num">{s.n_neutral}</span>
          <span className="sc-summary-label">neutral — descriptive, no clear direction</span>
        </div>
        <div className="sc-summary-item sc-critical">
          <span className="sc-summary-num">{s.n_critical}</span>
          <span className="sc-summary-label">critical — a governance concern</span>
        </div>
        <div className="sc-summary-item sc-nodata">
          <span className="sc-summary-num">{s.n_not_computable}</span>
          <span className="sc-summary-label">not computable on this corpus</span>
        </div>
      </div>

      <p className="chart-note sc-intro">
        Every standard governance test this corpus can run is reported here, including the ones
        the council passes — a clean result ("no threshold-gaming found") is shown, not hidden.
        The battery is built to run <strong>unmodified on any Western Australian council</strong>{" "}
        whose minutes yield the required schema, with the same test id on every one, so a result
        here lines up <strong>test by test</strong> against any other council's on the platform.
        A "not computable" row is part of that comparison too: it says this corpus's
        records don't carry what the test needs — a statement about record-keeping, not a finding
        about the council's conduct.
      </p>

      {groups.map((g) => (
        <div key={g.name} className="sc-group">
          <p className="section-heading">{g.name}</p>
          {g.tests.map((t) => <TestRow key={t.id} t={t} councillorNames={councillorNames} />)}
        </div>
      ))}

      <p className="chart-note">
        Valence maps to the severity ladders: <strong>supportive</strong> = a strength or a clean
        integrity test; <strong>neutral</strong> = descriptive; <strong>critical</strong> = a
        Best Value / CIPFA-principle concern. Each test states its n and era; a row with a fuller
        writeup links straight to it on <a href="#/analysis">Analysis</a>. "Not computable" rows
        are honest about the corpus's data limits — themselves a comparable signal across
        councils.
      </p>
    </Card>
  );
}
