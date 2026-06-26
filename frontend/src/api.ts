// Reserved for future interactive API endpoints (councillor drill-downs etc.)
const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function get<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const url = new URL(`${BASE}${path}`);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    }
  }
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

// Read a pre-computed snapshot written by `council publish <council>`.
// Snapshots live at frontend/public/data/{name}.json and are served as
// static files — the site only reflects data from the last publish run.
async function getSnapshot<T>(name: string): Promise<T> {
  const res = await fetch(`/data/${name}.json`);
  if (!res.ok) throw new Error(`Snapshot not found: ${name}.json — run 'council publish' first`);
  const json = await res.json();
  return json.data as T;
}

export interface InterestSummary {
  councillor_id: number;
  councillor_name: string;
  total: number;
  by_type: Record<string, number>;
  top_topics: string[];
}

export interface DivergenceData {
  total_matched: number;
  diverged_count: number;
  followed_count: number;
  compliance_rate: number;
  year_min: number | null;
  year_max: number | null;
  exceptions: {
    meeting_date: string;
    item_number: string | null;
    title: string;
    officer_recommendation: string | null;
    council_outcome: string | null;
    match_confidence: number;
  }[];
}

export interface CoMoverNode {
  id: string;
}

export interface CoMoverLink {
  source: string;
  target: string;
  value: number;
}

export interface CoMoverData {
  nodes: CoMoverNode[];
  links: CoMoverLink[];
  pairs: {
    mover_id: number;
    mover_name: string;
    seconder_id: number;
    seconder_name: string;
    count: number;
  }[];
}

export interface AlignmentPair {
  name_a: string;
  name_b: string;
  agreement_rate: number;
  shared_votes: number;
  is_ally: boolean;
  is_opponent: boolean;
}

export interface TrendsData {
  contestation: {
    year: number;
    total_carried: number;
    total_with_dissent: number;
    contestation_rate: number;
    most_contested: string[];
  }[];
  topics: Record<string, Record<string, number>>;
}

export interface EngagementStat {
  year: number;
  public_questions: number;
  deputations: number;
  petitions: number;
}

export interface PlanningTrendYear {
  year: number;
  n_applications: number;
  decided: number;
  approved: number;
  refused: number;
  approval_pct: number;
}

export interface PlanningObjectionGroup {
  n: number;
  approved: number;
  refused: number;
  approval_pct: number;
}

export interface PlanningData {
  trend: PlanningTrendYear[];
  objections: {
    with_objection: PlanningObjectionGroup;
    no_objection: PlanningObjectionGroup;
  };
}

export interface DissenterProfile {
  name: string;
  total_votes_on_carried: number;
  against_count: number;
  dissent_rate: number;
  is_active: boolean;
  top_dissent_tags: string[];
}

export interface DissentPair {
  name_a: string;
  name_b: string;
  shared_dissent: number;
}

export interface TagContestationStat {
  tag: string;
  total_carried: number;
  contested: number;
  contestation_rate: number;
}

export interface DissentData {
  profiles: DissenterProfile[];
  coalitions: DissentPair[];
  by_tag: TagContestationStat[];
}

export interface DeclarationDetail {
  date: string;
  item: string | null;
  title: string | null;
  interest_type: string | null;   // financial / proximity / impartiality / other
  what: string | null;            // the actual interest description
  action: string;                 // "Stepped out" / "Stayed — voted for" / ...
  must_leave: boolean;
  quote: string | null;           // verbatim minute text
}

export interface RecusalProfile {
  name: string;
  declared_votes: number;
  recused: number;
  recusal_rate: number;
  is_active: boolean;
  declarations: DeclarationDetail[];
}

export interface ConflictRecusalData {
  declared_total: number;
  declared_recused: number;
  declared_recusal_pct: number;
  declared_against_pct: number;
  baseline_total: number;
  baseline_recusal_pct: number;
  baseline_against_pct: number;
  profiles: RecusalProfile[];
}

export interface TenderAward {
  date: string;
  description: string | null;
  amount: number;
  reference: string | null;
  is_confidential: boolean;
  quote: string | null;            // verbatim minute text
}

export interface ContractorTotal {
  name: string;
  n_awards: number;
  total_amount: number;
  awards: TenderAward[];
}

export interface TenderData {
  total_awards: number;
  total_amount: number;
  named_awards: number;
  named_amount: number;
  redacted_awards: number;
  redacted_amount: number;
  distinct_named: number;
  top10_amount: number;
  top10_share: number;
  contractors: ContractorTotal[];
}

export interface ObjectionDoseBucket {
  label: string;
  n: number;
  refused: number;
  refusal_pct: number;
}

export interface ObjectionDoseData {
  total_decided: number;
  max_objections: number;
  headline_examples: string[];
  buckets: ObjectionDoseBucket[];
}

export interface TransparencyYear {
  year: number;
  total: number;
  confidential: number;
  confidential_pct: number;
}

export interface TransparencyData {
  pre_era_pct: number;
  peak_year: number;
  peak_pct: number;
  category_totals: Record<string, { total: number; confidential: number }>;
  years: TransparencyYear[];
}

export interface TenureProfile {
  name: string;
  years: number;
  n_votes: number;
  first: string;
  last: string;
  is_active: boolean;
}

export interface TenureData {
  median_years: number;
  n_councillors: number;
  histogram: Record<string, number>;
  profiles: TenureProfile[];
}

export interface MayorContest {
  name: string;
  carried: number;
  contested: number;
  contest_pct: number;
}

export interface MayoralData {
  mayor_moved: number;
  mayor_carried_pct: number;
  mayor_contest_pct: number;
  other_moved: number;
  other_carried_pct: number;
  other_contest_pct: number;
  contest_factor: number;
  per_mayor: MayorContest[];
}

export interface ContestedVoteDetail {
  date: string;
  item: string | null;
  title: string | null;
  choice: string;                  // "For" / "Against"
  outcome: string;                 // "Carried" / "Lost"
  won: boolean;
  margin: number | null;           // votes_for − votes_against
  quote: string | null;            // verbatim minute text
}

export interface PowerProfile {
  name: string;
  n: number;
  win_rate: number;
  dissent_rate: number;
  dissent_n: number;
  dissent_effectiveness: number | null;
  is_active: boolean;
  n_shown: number;
  votes: ContestedVoteDetail[];
}

export interface PowerTermPoint {
  term: string;
  win_rate: number;
  n: number;
}

export interface PowerOverTime {
  name: string;
  points: PowerTermPoint[];
}

export interface PowerData {
  base_carry_rate: number;
  base_fail_rate: number;
  n_contested: number;
  profiles: PowerProfile[];
  over_time: PowerOverTime[];
}

export interface RecusalDeclarationDetail {
  date: string;
  item: string | null;
  councillor: string;
  action: string;          // "Stepped out" / "Stayed — voted"
  what: string | null;
  quote: string | null;    // verbatim minute text
}

export interface RecusalTypeEra {
  interest_type: string;   // financial | proximity | impartiality | other
  era: string;             // pre | inquiry | post
  declared: number;
  recused: number;
  recusal_pct: number;
  n_shown: number;
  declarations: RecusalDeclarationDetail[];
}

export interface RecusalYearPoint {
  year: number;
  must_leave_declared: number;
  must_leave_recused: number;
  must_leave_pct: number | null;
  declared_share_pct: number;
}

export interface RecusalDriver {
  name: string;
  stayed: number;
  total: number;
}

export interface RecusalData {
  inquiry_window: number[];
  must_leave_pre_pct: number;
  must_leave_pre_n: number;
  must_leave_inquiry_pct: number;
  must_leave_inquiry_n: number;
  must_leave_post_pct: number;
  must_leave_post_n: number;
  financial_inquiry_pct: number;
  financial_inquiry_n: number;
  financial_post_pct: number;
  financial_post_n: number;
  impartiality_post_declared: number;
  impartiality_post_recusal_pct: number;
  by_type_era: RecusalTypeEra[];
  by_year: RecusalYearPoint[];
  drivers: RecusalDriver[];
}

export interface OverviewData {
  span: string;
  n_minutes: number;
  n_documents: number;
  confidential_pre_pct: number;
  confidential_peak_pct: number;
  confidential_peak_year: number;
  recusal_inquiry_pct: number;
  recusal_post_pct: number;
  financial_inquiry_pct: number;
  financial_post_pct: number;
  base_carry_pct: number;
  n_contested: number;
  win_min_pct: number;
  win_max_pct: number;
  sponsor_conv_high: number;
  sponsor_conv_low: number;
  oldguard_unanimous_pct: number;
  declared_stay_pct: number;
  impartiality_post_declared: number;
  impartiality_post_recusal_pct: number;
  tenure_median_years: number;
  tenure_15plus: number;
  tenure_top_name: string;
  tenure_top_years: number;
  officer_matched: number;
  officer_diverged: number;
  officer_compliance_pct: number;
  dose_0_refusal_pct: number;
  dose_5plus_refusal_pct: number;
  tender_total_m: number;
  tender_redacted_m: number;
  tender_top10_share_pct: number;
  mayor_contest_pct: number;
  other_contest_pct: number;
}

export interface SponsorEdge {
  era_label: string;
  name_a: string;
  name_b: string;
  sponsorships: number;
  lift: number;
  agree_pct: number | null;
  agree_n: number;
  kind: "alliance" | "procedural" | "mixed";
}

export interface SponsorNode {
  name: string;
  moved: number;
  seconded: number;
  in_core: boolean;
}

export interface SponsorEra {
  label: string;
  year_from: number;
  year_to: number;
  n_events: number;
  n_active: number;
  cluster_size: number;
  core_names: string[];
  structure: string;
}

export interface SponsorshipData {
  alliances: SponsorEdge[];
  procedural: SponsorEdge[];
  convergence_high_agree: number;
  convergence_low_agree: number;
  oldguard_label: string;
  oldguard_unanimous_pct: number;
  oldguard_nodes: SponsorNode[];
  oldguard_edges: SponsorEdge[];
  eras: SponsorEra[];
}

export type Valence = "supportive" | "neutral" | "critical";

export interface TestChartBar { label: string; value: number; highlight?: boolean; }
export interface TestChartRefline { label: string; value?: number; after?: string; }
export interface TestChart {
  kind: "bars" | "line";
  unit?: string;
  refline?: TestChartRefline | null;
  bars?: TestChartBar[];
  points?: { x: number; y: number }[];
}

export interface ScorecardTest {
  test_id: string;
  title: string;
  genre: string;
  principle: string;
  question: string;
  valence: Valence;
  grade: string;
  headline: string;
  verdict: string;
  data_ok: boolean;
  n: number | null;
  base_rate: string | null;
  era: string | null;
  detail_panel: string | null;
  series: { x: number; y: number }[];
  chart: TestChart | null;
}

export interface ScorecardData {
  summary: {
    n_tests: number;
    n_supportive: number;
    n_neutral: number;
    n_critical: number;
    n_not_computable: number;
  };
  tests: ScorecardTest[];
}

export const api = {
  scorecard:  () => getSnapshot<ScorecardData>("scorecard"),
  interests:  () => getSnapshot<InterestSummary[]>("interests"),
  divergence: () => getSnapshot<DivergenceData>("divergence"),
  coMovers:   () => getSnapshot<CoMoverData>("co-movers"),
  alignment:  () => getSnapshot<{ pairs: AlignmentPair[] }>("alignment"),
  trends:     () => getSnapshot<TrendsData>("trends"),
  engagement: () => getSnapshot<EngagementStat[]>("engagement"),
  planning:   () => getSnapshot<PlanningData>("planning"),
  dissent:    () => getSnapshot<DissentData>("dissent"),
  declared:   () => getSnapshot<ConflictRecusalData>("declared"),
  tenders:    () => getSnapshot<TenderData>("tenders"),
  dose:       () => getSnapshot<ObjectionDoseData>("dose"),
  transparency: () => getSnapshot<TransparencyData>("transparency"),
  tenure:     () => getSnapshot<TenureData>("tenure"),
  mayoral:    () => getSnapshot<MayoralData>("mayoral"),
  power:      () => getSnapshot<PowerData>("power"),
  recusal:    () => getSnapshot<RecusalData>("recusal"),
  sponsorship: () => getSnapshot<SponsorshipData>("sponsorship"),
  overview:   () => getSnapshot<OverviewData>("overview"),
};
