import { useData } from "../hooks/useData";
import { api, OverviewData, ScorecardData } from "../api";
import { useCorpusSpan } from "../councils";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";
import { GlossaryText } from "./Glossary";
import { REGISTRY_BY_ID } from "../registry";

// SECOND_COUNCIL_PLAN.md Phase 3.5: this panel used to be a hand-written
// synthesis for this project's first corpus — a thesis paragraph, a
// one-liner, and eight interpretive "insight" bodies asserting conclusions
// that were true of that one council but not computed, and would render
// unchanged and wrong for any other. The plan's preferred fix — rendering a
// real synthesis
// field from the Renderer role (docs/render/synthesis_mode.txt) — isn't
// available yet: Renderer has never been run and has no calibration data,
// so that's a real dependency, not a free win here. This is the plan's
// fallback: reduce to what's actually computable per council — the same
// stat tiles, stripped of the narrative that connected them, plus the
// valence mix scorecard.json already carries.
interface StatTile {
  n: number;
  stat: string;
  label: string;
  // The real test_id this tile's figure comes from — its `principle` is
  // resolved from config/test_registry.json's own `principles` array
  // (docs/uplift/migration/04-jurisdiction.md G-01/Step 1), never typed
  // here as a second, independently-drifting copy of the same citation.
  testId: string;
}

// A registry row's `principles` array is a single source of truth: reading
// it here means this panel's citations can never quietly diverge from the
// same test's citation everywhere else it's shown (ScorecardPanel, the
// deep-dive panels, tests.py's own TestResult.principle — all now sourced
// from this same file, see tests.py's run_test_battery()).
function principleFor(testId: string): string {
  return REGISTRY_BY_ID[testId]?.principles.join(" · ") ?? "";
}

export function OverviewPanel() {
  const { data, loading, error } = useData<OverviewData>(() => api.overview());
  const { data: scorecard } = useData<ScorecardData>(() => api.scorecard());
  const span = useCorpusSpan();
  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;
  const d = data;

  const tiles: StatTile[] = [
    {
      n: 1,
      stat: `${d.recusal_inquiry_pct}% → ${d.recusal_post_pct}%`,
      label: "recusal on serious conflicts, during vs after this council's scrutiny window",
      testId: "conflict.recusal_trend",
    },
    {
      n: 2,
      stat: `${d.win_min_pct}–${d.win_max_pct}%`,
      label: `spread in contested-vote win rates between councillors (${d.n_contested.toLocaleString()} contested votes; ${d.base_carry_pct}% of all motions carry)`,
      testId: "governance.power_spread",
    },
    {
      n: 3,
      stat: `${d.declared_stay_pct}%`,
      label: "of declared conflicts, the councillor stays and votes anyway",
      testId: "conflict.recusal_management",
    },
    {
      n: 4,
      stat: `${d.tenure_top_years} yrs`,
      label: `longest-serving councillor (median ${d.tenure_median_years} yrs; ${d.tenure_15plus} served 15+)`,
      testId: "governance.incumbency",
    },
    {
      n: 5,
      stat: `${d.officer_compliance_pct}%`,
      label: `of officer recommendations adopted unchanged (${d.officer_matched - d.officer_diverged} of ${d.officer_matched} matched items)`,
      testId: "governance.officer_ratification",
    },
    {
      n: 6,
      stat: `${d.dose_0_refusal_pct}% → ${d.dose_5plus_refusal_pct}%`,
      label: "planning refusal rate: no objectors vs 5+ coordinated objectors",
      testId: "planning.objection_responsiveness",
    },
    {
      n: 7,
      stat: `$${d.tender_redacted_m}M`,
      label: `of $${d.tender_total_m}M in tenders redacted (${d.tender_top10_share_pct}% to top-10 firms)`,
      testId: "procurement.concentration",
    },
    {
      n: 8,
      stat: `${d.confidential_pre_pct}%`,
      label: "confidential business before this council's scrutiny window",
      testId: "transparency.confidential_share",
    },
  ];

  const s = scorecard?.summary;

  return (
    <Card
      title="Governance at a Glance"
      subtitle={`Key figures across the battery${span ? ` · ${span}` : ""} · ${d.n_minutes} minutes`}
    >
      {s && (
        <div className="overview-valence-mix">
          <span className="valence-chip valence-supportive">{s.n_supportive} supportive</span>
          <span className="valence-chip valence-neutral">{s.n_neutral} neutral</span>
          <span className="valence-chip valence-critical">{s.n_critical} critical</span>
          {s.n_not_computable > 0 && (
            <span className="valence-chip">{s.n_not_computable} not computable</span>
          )}
          <span className="chart-note" style={{ marginLeft: 8 }}>
            of {s.n_tests} standard governance tests — see the full scorecard below
          </span>
        </div>
      )}

      <div className="overview-grid">
        {tiles.map((it) => (
          <div key={it.n} className="overview-insight">
            <div className="overview-insight-stat">{it.stat}</div>
            <div className="overview-insight-statlabel">{it.label}</div>
            <span className="overview-insight-principle"><GlossaryText text={principleFor(it.testId)} /></span>
          </div>
        ))}
      </div>
    </Card>
  );
}
