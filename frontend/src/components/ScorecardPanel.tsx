import { useData } from "../hooks/useData";
import { api, ScorecardData, ScorecardTest, CouncillorsData } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";
import { ValenceChip } from "./ValenceChip";
import { groupTestsByGenre } from "../groupTestsByGenre";

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

function TestRow({ t, flaggedNames }: { t: ScorecardTest; flaggedNames?: string[] }) {
  const headline = flaggedNames ? redactNamedCouncillors(t.headline, flaggedNames) : t.headline;
  const verdict = flaggedNames ? redactNamedCouncillors(t.verdict, flaggedNames) : t.verdict;
  return (
    <div
      className={`sc-row sc-${t.valence}${t.data_ok ? "" : " sc-nodata"}`}
      id={t.detail_panel ? `sc-${t.detail_panel}` : undefined}
    >
      <div className="sc-row-flag">
        <ValenceChip valence={t.valence} notComputable={!t.data_ok} />
      </div>
      <div className="sc-row-main">
        <div className="sc-row-head">
          <span className="sc-row-title">{t.title}</span>
          <span className="sc-row-grade">{t.grade}</span>
        </div>
        {flaggedNames && (
          <div className="sc-row-guardrail">
            ⚠ Named-individual claim flagged for editorial review — redacted pending sign-off
          </div>
        )}
        <div className="sc-row-headline">{headline}</div>
        <div className="sc-row-verdict">{verdict}</div>
        <div className="sc-row-meta">
          <span className="sc-genre">{t.genre}</span>
          <span className="sc-principle">{t.principle}</span>
          {t.n != null && <span className="sc-n">n&nbsp;=&nbsp;{t.n.toLocaleString()}</span>}
          {t.era && <span className="sc-era">{t.era}</span>}
          {t.detail_panel && (
            <a className="sc-detail" href={`#panel-${t.detail_panel}`}>↓ jump to full panel</a>
          )}
        </div>
      </div>
    </div>
  );
}

export function ScorecardPanel() {
  const { data, loading, error } = useData<ScorecardData>(() => api.scorecard());
  const { data: cllrData } = useData<CouncillorsData>(() => api.councillors());
  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;
  const s = data.summary;

  const flagged = new Map<string, string[]>();
  if (cllrData) {
    const names = Object.keys(cllrData.by_name);
    for (const t of data.tests) {
      const hits = findNamedCouncillorsInText(`${t.headline} ${t.verdict}`, names);
      if (hits.length) {
        flagged.set(t.test_id, hits);
        console.error(
          `[scorecard guardrail] ${t.valence}-valence test "${t.test_id}" names ` +
          `${hits.join(", ")} in its headline/verdict — redacted in the rendered output ` +
          `pending review; see docs/review/editor/Editor_prompt.txt`
        );
      }
    }
  }

  const groups = groupTestsByGenre(data.tests);

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
        Unlike the panels below — which earn their place by being <em>surprising</em> — the
        scorecard reports <strong>every</strong> standard test, including the ones the council
        passes. A clean result ("no threshold-gaming found") is shown, not hidden, so the reader
        sees the good and the neutral alongside the concerning. Because every council runs the
        identical battery with stable test IDs, these results are <strong>comparable across
        councils</strong>, not just notes about Cambridge.
      </p>

      {groups.map((g) => (
        <div key={g.name} className="sc-group">
          <p className="section-heading">{g.name}</p>
          {g.tests.map((t) => <TestRow key={t.test_id} t={t} flaggedNames={flagged.get(t.test_id)} />)}
        </div>
      ))}

      <p className="chart-note">
        Valence maps to the severity ladders: <strong>supportive</strong> = a strength or a clean
        integrity test; <strong>neutral</strong> = descriptive; <strong>critical</strong> = a
        Best Value / CIPFA-principle concern. Each test states its n and era; where a panel below
        explores it in depth, the row says so. "Not computable" rows are honest about the corpus's
        data limits — themselves a comparable signal across councils.
      </p>
    </Card>
  );
}
