import { useData } from "../hooks/useData";
import { api, OverviewData, ScorecardData } from "../api";
import { useCorpusSpan } from "../councils";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";
import { GlossaryText } from "./Glossary";

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
  principle: string;
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
      principle: "Nolan · Accountability, Openness",
    },
    {
      n: 2,
      stat: `${d.win_min_pct}–${d.win_max_pct}%`,
      label: `spread in contested-vote win rates between councillors (${d.n_contested.toLocaleString()} contested votes; ${d.base_carry_pct}% of all motions carry)`,
      principle: "CIPFA · principle B",
    },
    {
      n: 3,
      stat: `${d.declared_stay_pct}%`,
      label: "of declared conflicts, the councillor stays and votes anyway",
      principle: "Nolan · Integrity, Objectivity",
    },
    {
      n: 4,
      stat: `${d.tenure_top_years} yrs`,
      label: `longest-serving councillor (median ${d.tenure_median_years} yrs; ${d.tenure_15plus} served 15+)`,
      principle: "CIPFA · principle A",
    },
    {
      n: 5,
      stat: `${d.officer_compliance_pct}%`,
      label: `of officer recommendations adopted unchanged (${d.officer_matched - d.officer_diverged} of ${d.officer_matched} matched items)`,
      principle: "CIPFA · principle F",
    },
    {
      n: 6,
      stat: `${d.dose_0_refusal_pct}% → ${d.dose_5plus_refusal_pct}%`,
      label: "planning refusal rate: no objectors vs 5+ coordinated objectors",
      principle: "CIPFA · principle B",
    },
    {
      n: 7,
      stat: `$${d.tender_redacted_m}M`,
      label: `of $${d.tender_total_m}M in tenders redacted (${d.tender_top10_share_pct}% to top-10 firms)`,
      principle: "CIPFA · principles F, G",
    },
    {
      n: 8,
      stat: `${d.confidential_pre_pct}%`,
      label: "confidential business before this council's scrutiny window",
      principle: "Nolan · Openness, Accountability · CIPFA · F, G",
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
            <span className="overview-insight-principle"><GlossaryText text={it.principle} /></span>
          </div>
        ))}
      </div>
    </Card>
  );
}
