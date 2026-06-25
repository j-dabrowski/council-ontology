import { useData } from "../hooks/useData";
import { api, ScorecardData, ScorecardTest, Valence } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";
import { ValenceChip } from "./ValenceChip";

// Map a test's detail_panel snapshot name to the on-page anchor we scroll to.
// (Panels aren't individually anchored yet, so this is a best-effort scroll.)
const VALENCE_ORDER: Record<Valence, number> = { critical: 0, neutral: 1, supportive: 2 };

function TestRow({ t }: { t: ScorecardTest }) {
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
        <div className="sc-row-headline">{t.headline}</div>
        <div className="sc-row-verdict">{t.verdict}</div>
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
  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;
  const s = data.summary;

  // Assign each test to exactly one genre family (first match wins), then sort
  // each family critical → neutral → supportive.
  const order: [string, (g: string) => boolean][] = [
    ["Integrity & procurement", (g) => /procurement|conflict|integrity/i.test(g)],
    ["Governance & culture", (g) => /governance|culture/i.test(g)],
    ["Planning & fairness", (g) => /planning|fairness/i.test(g)],
    ["Transparency & engagement", (g) => /transparency|engagement/i.test(g)],
    ["Financial", (g) => /financial/i.test(g)],
  ];
  const buckets = new Map<string, ScorecardTest[]>(order.map(([name]) => [name, []]));
  const other: ScorecardTest[] = [];
  for (const t of data.tests) {
    const hit = order.find(([, match]) => match(t.genre));
    (hit ? buckets.get(hit[0])! : other).push(t);
  }
  const groups = order
    .map(([name]) => ({
      name,
      tests: buckets.get(name)!.sort((a, b) => VALENCE_ORDER[a.valence] - VALENCE_ORDER[b.valence]),
    }))
    .filter((g) => g.tests.length);
  if (other.length) groups.push({ name: "Other", tests: other });

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
          {g.tests.map((t) => <TestRow key={t.test_id} t={t} />)}
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
