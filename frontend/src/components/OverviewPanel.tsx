import { useData } from "../hooks/useData";
import { api, OverviewData } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

interface Insight {
  n: number;
  title: string;
  stat: string;
  statLabel: string;
  body: React.ReactNode;
  principle: string;
}

export function OverviewPanel() {
  const { data, loading, error } = useData<OverviewData>(() => api.overview());
  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;
  const d = data;

  const insights: Insight[] = [
    {
      n: 1,
      title: "The Inquiry is the hinge — and no improvement outlasted it",
      stat: `${d.recusal_inquiry_pct}% → ${d.recusal_post_pct}%`,
      statLabel: "recusal on serious conflicts, during vs after the Inquiry — the clearest reversion",
      body: (
        <>Four independent panels pivot on the 2018–21 Authorised Inquiry. Stepping out
        of serious conflicts rose to {d.recusal_inquiry_pct}% under scrutiny then
        collapsed to {d.recusal_post_pct}% afterwards (financial conflicts:{" "}
        {d.financial_inquiry_pct}% → {d.financial_post_pct}%); confidential business
        spiked from {d.confidential_pre_pct}% to {d.confidential_peak_pct}% in{" "}
        {d.confidential_peak_year} then receded; and public questions "taken on notice"
        rather than answered live tripled from {d.pq_pre_pct}% to {d.pq_inquiry_pct}%,
        only partly easing to {d.pq_post_pct}% — still well above baseline. A systematic
        durable-improvement sweep found <strong>no</strong> domain that tightened under
        scrutiny and held: the one clear improvement (recusal) fully reverted, while the
        defensive habits the Inquiry provoked partly stuck. Conduct changed while someone
        was watching; nothing changed for keeps.</>
      ),
      principle: "Nolan · Accountability, Openness",
    },
    {
      n: 2,
      title: "Consensus hides a power hierarchy",
      stat: `${d.win_min_pct}–${d.win_max_pct}%`,
      statLabel: "spread in contested-vote win rates between councillors",
      body: (
        <>The chamber carries {d.base_carry_pct}% of motions, most unanimously — but
        win rates on the {d.n_contested.toLocaleString()} contested votes span{" "}
        {d.win_min_pct}–{d.win_max_pct}%, and a councillor's influence is unrelated
        to how loudly they dissent. Even in an era that was{" "}
        {d.oldguard_unanimous_pct}% unanimous, who <em>seconds</em> whom exposes the
        blocs the vote can't (heavy sponsors agree {d.sponsor_conv_high}% vs a{" "}
        {d.sponsor_conv_low}% base rate).</>
      ),
      principle: "CIPFA · principle B",
    },
    {
      n: 3,
      title: "Declaring a conflict became a ritual",
      stat: `${d.declared_stay_pct}%`,
      statLabel: "of declared conflicts, the councillor stays and votes anyway",
      body: (
        <>Declaring an interest lifts recusal ~80× — yet {d.declared_stay_pct}% of the
        time the member stays and votes, leaning toward letting the matter through.
        After the Inquiry, "impartiality" declarations ballooned to{" "}
        {d.impartiality_post_declared} declared votes at{" "}
        {d.impartiality_post_recusal_pct}% recusal: near-meaningless boilerplate.
        Declare more, recuse less.</>
      ),
      principle: "Nolan · Integrity, Objectivity",
    },
    {
      n: 4,
      title: "Entrenchment renews itself",
      stat: `${d.tenure_top_years} yrs`,
      statLabel: "longest-serving councillor",
      body: (
        <>Median service is {d.tenure_median_years} years and{" "}
        {d.tenure_15plus} councillors served 15+. The 2000s "old guard" sponsorship
        clique recruited the very members who then dominated the next two decades
        before fragmenting in 2008. The establishment reproduces itself.</>
      ),
      principle: "CIPFA · principle A",
    },
    {
      n: 5,
      title: "Officers decide; the chamber ratifies",
      stat: `${d.officer_compliance_pct}%`,
      statLabel: "of officer recommendations are adopted unchanged",
      body: (
        <>Council followed the officer recommendation in{" "}
        {d.officer_matched - d.officer_diverged} of {d.officer_matched} matched items
        ({d.officer_compliance_pct}%). The visible debate is largely theatre — the
        substantive decision is made upstream, in who writes the recommendation. The
        most important caveat on everything else here.</>
      ),
      principle: "CIPFA · principle F",
    },
    {
      n: 6,
      title: "Residents move outcomes only in numbers",
      stat: `${d.dose_0_refusal_pct}% → ${d.dose_5plus_refusal_pct}%`,
      statLabel: "refusal rate: no objectors vs 5+ coordinated objectors",
      body: (
        <>A lone objector is statistical noise ({d.dose_0_refusal_pct}% refusal,
        barely above baseline). But once five or more neighbours object together the
        refusal rate jumps to {d.dose_5plus_refusal_pct}%. The act of objecting hardly
        matters; coordinated numbers do.</>
      ),
      principle: "CIPFA · principle B",
    },
    {
      n: 7,
      title: "The money: concentrated, opaque — not captured",
      stat: `$${d.tender_redacted_m}M`,
      statLabel: `of $${d.tender_total_m}M in tenders is redacted (${d.tender_top10_share_pct}% to top-10 firms)`,
      body: (
        <>${d.tender_total_m}M of awarded work, with the top-10 firms taking{" "}
        {d.tender_top10_share_pct}% and a third of all dollars (${d.tender_redacted_m}M)
        hidden behind "Respondent N" placeholders. Yet every integrity test —
        threshold-gaming, entrenched incumbents, big-dollar leniency,
        repeat-applicant advantage — comes back <strong>null</strong>. The issue is
        transparency, not detectable capture.</>
      ),
      principle: "CIPFA · principles F, G",
    },
    {
      n: 8,
      title: "And the record that earns the council credit",
      stat: `${d.confidential_pre_pct}%`,
      statLabel: "confidential business across two decades (1995–2017) — a genuinely open baseline",
      body: (
        <>Read the same data through the council's defender and a real
        good-governance record stands up. For two decades barely{" "}
        {d.confidential_pre_pct}% of business was closed — and even where
        confidentiality <em>is</em> used it tracks lawful grounds, not controversy:
        the most contentious category, named developments, is the <em>least</em> closed
        ({d.conf_dev_pct}% vs a {d.conf_base_pct}% base), so closure is not used to bury
        difficult planning. The tender record passes <strong>every</strong> integrity
        test thrown at it — no threshold-gaming, no entrenched incumbent, no
        repeat-player edge, no decider-tied supplier. The chamber does <em>not</em>{" "}
        rubber-stamp its own Mayor — mayoral motions drew dissent{" "}
        {d.mayor_contest_pct}% of the time vs {d.other_contest_pct}% for backbench
        motions — and contested-vote power turns over at elections rather than
        sticking. The faults above are real, but they are exceptions in an
        otherwise sound record — which is exactly why they stand out.</>
      ),
      principle: "Nolan · Openness, Accountability · CIPFA · F, G",
    },
  ];

  return (
    <Card
      title="What 30 Years of Minutes Say — the Big Picture"
      subtitle={`A synthesis across every panel below · City of Cambridge · ${d.span} · ${d.n_minutes} minutes`}
    >
      <div className="overview-thesis">
        <p>
          On the evidence, Cambridge is a <strong>broadly sound council with specific,
          nameable weaknesses</strong> — not a failing one. Every integrity test on the
          dollars comes back null, the tender record is clean, the chamber does not
          rubber-stamp its Mayor, and for two decades its business was overwhelmingly
          open. Against that baseline the genuine concerns stand out: a consensus chamber
          that conceals real power inequality, and an accountability safeguard
          (conflict-of-interest recusal) that decayed into a formality once external
          scrutiny lifted.
        </p>
        <p className="overview-oneliner">
          A council that governs by consensus and runs a clean-tested money record, but
          conceals a durable power structure behind near-unanimous votes, lets
          conflict-declaration decay into formality — and behaved best only while someone
          was watching.
        </p>
      </div>

      <div className="overview-grid">
        {insights.map((it) => (
          <div key={it.n} className="overview-insight">
            <div className="overview-insight-head">
              <span className="overview-insight-num">{it.n}</span>
              <span className="overview-insight-title">{it.title}</span>
            </div>
            <div className="overview-insight-stat">{it.stat}</div>
            <div className="overview-insight-statlabel">{it.statLabel}</div>
            <p className="overview-insight-body">{it.body}</p>
            <span className="overview-insight-principle">{it.principle}</span>
          </div>
        ))}
      </div>

      <p className="chart-note overview-honesty">
        <strong>The honesty layer.</strong> The nulls are load-bearing: the <em>absence</em> of
        financial-corruption signatures is itself a finding — on three independent integrity tests
        the tender record comes back clean. The reading is deliberately <strong>balanced</strong>:
        strengths (insight 8) are graded where earned on a positive ladder (sound practice →
        good-governance strength), concerns sit at <strong>Observation</strong> or{" "}
        <strong>Governance-concern</strong> altitude — a pattern that warrants explanation against a
        named principle, never an assertion of wrongdoing or intent — and each is weighted to the
        strength of its evidence, not amplified by default. Each links to a panel below where the
        figure, its sample size, and its caveats are laid out in full.
      </p>
    </Card>
  );
}
