import { getMode } from "./devMode";

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

// Read a pre-computed snapshot. In Publish mode (the default, and the only
// mode possible in a production build — see devMode.ts) this is
// frontend/public/data/{name}.json, the static files `council publish`
// writes — the site only reflects data from the last publish run. In Draft
// mode (dev server only, via the corner switch) this instead reads
// /data/draft/{name}.json, served live from the newest `council draft` run
// by vite.config.ts's draftOverlay() plugin.
async function getSnapshot<T>(name: string): Promise<T> {
  const draftMode = getMode() === "draft";
  const res = await fetch(`${draftMode ? "/data/draft" : "/data"}/${name}.json`);
  // Vite's dev server SPA-falls-back to index.html (200, text/html) for any
  // unmatched path rather than a real 404 — so a missing snapshot (e.g. no
  // `council draft` has ever been run yet) would otherwise surface as a
  // cryptic "JSON.parse: unexpected character" instead of this message.
  if (!res.ok || !res.headers.get("content-type")?.includes("json")) {
    throw new Error(
      draftMode
        ? `Snapshot not found: ${name}.json — run 'council draft' first`
        : `Snapshot not found: ${name}.json — run 'council publish' first`
    );
  }
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
    motion_text: string | null;
    quote: string | null;
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
  entity_id: number | null;       // interest_declarations.id, for the evidence chain lookup
}

export interface RecusalProfile {
  name: string;
  declared_votes: number;
  recused: number;
  recusal_rate: number;
  is_active: boolean;
  // Legally-mandatory (financial/proximity) declarations only — excludes lawful
  // "impartiality" declarations the councillor is entitled to stay and vote on.
  // must_leave_recusal_rate is null when must_leave_declared is 0 (no mandatory
  // conflicts on record at all), matching the pipeline's null-for-zero convention.
  must_leave_declared: number;
  must_leave_recused: number;
  must_leave_recusal_rate: number | null;
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
  entity_id: number | null;        // tenders.id, for the evidence chain lookup
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

export interface DoseApp {
  entity_id: number;
  reference: string | null;
  description: string | null;
  address: string | null;
  n_objectors: number;
  outcome: string | null;   // "approved" | "refused"
  quote: string | null;
}

export interface ObjectionDoseBucket {
  label: string;
  n: number;
  refused: number;
  refusal_pct: number;
  n_shown: number;
  apps: DoseApp[];
}

export interface ObjectionDoseData {
  total_decided: number;
  max_objections: number;
  headline_examples: string[];
  buckets: ObjectionDoseBucket[];
}

export interface ConfidentialItem {
  kind: string;           // "tender" | "other_item" | "delegated_decision" | "budget_item"
  description: string | null;
  amount: number | null;
  date: string | null;
  quote: string | null;
  entity_table: string;   // "tenders" | "other_items" | "delegated_decisions" | "budget_items"
  entity_id: number;
}

export interface TransparencyYear {
  year: number;
  total: number;
  confidential: number;
  confidential_pct: number;
  n_shown: number;
  items: ConfidentialItem[];
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

export interface MayoralMotion {
  title: string | null;
  date: string;
  votes_for: number | null;
  votes_against: number | null;
  quote: string | null;
  entity_id: number;
}

export interface MayorContest {
  name: string;
  carried: number;
  contested: number;
  contest_pct: number;
  n_shown: number;
  motions: MayoralMotion[];
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
  entity_id: number | null;        // motions.id, for the evidence chain lookup
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
  entity_id: number | null; // interest_declarations.id, for the evidence chain lookup
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

export interface PQResponseDetail {
  date: string;
  questioner: string | null;
  question: string | null;
  status: string;           // "Answered in meeting" / "Taken on notice"
  fielded_by: string | null;
  quote: string | null;
  entity_id: number | null; // public_questions.id, for the evidence chain lookup
}

export interface PQEraStat {
  era: string;              // pre | inquiry | post
  answered: number;
  on_notice: number;
  blank: number;
  on_notice_pct: number;
  n_shown: number;
  questions: PQResponseDetail[];
}

export interface PQYearPoint {
  year: number;
  answered: number;
  on_notice: number;
  n_nonblank: number;
  on_notice_pct: number | null;
}

export interface QuestionResponsivenessData {
  inquiry_window: number[];
  total: number;
  answered: number;
  on_notice: number;
  blank: number;
  answered_pct: number;
  on_notice_pct: number;
  pre_pct: number;
  pre_n: number;
  inquiry_pct: number;
  inquiry_n: number;
  post_pct: number;
  post_n: number;
  peak_year: number | null;
  peak_pct: number | null;
  by_era: PQEraStat[];
  by_year: PQYearPoint[];
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
  conf_dev_pct: number;
  conf_base_pct: number;
  pq_pre_pct: number;
  pq_inquiry_pct: number;
  pq_post_pct: number;
  pq_peak_pct: number | null;
  pq_peak_year: number | null;
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

export interface CouncillorProfile {
  name: string;
  slug: string;
  is_active: boolean;
  tenure_years: number | null;
  first_vote: string | null;
  last_vote: string | null;
  n_votes: number | null;
  roles: string[];
  n_contested: number | null;
  win_rate: number | null;
  dissent_rate: number | null;
  dissent_n: number | null;
  dissent_effectiveness: number | null;
  n_declarations: number;
  n_recused: number;
  recusal_rate: number | null;
  declarations: DeclarationDetail[];
  dissent_votes: ContestedVoteDetail[];
  moved: number;
  seconded: number;
  top_partners: { name: string; count: number }[];
}

export interface CouncillorsData {
  by_name: Record<string, CouncillorProfile>;
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

// The published `/watch` feed (docs/frontend/WATCH_FEED_PLAN.md C.2) — one
// row per minutes meeting, newest first, corpus-wide. Written by `council
// draft`'s `compute_watch_feed()` then filtered to public-tier claims only
// by `project_watch_feed_to_public()` before it ever reaches a snapshot
// (src/analysis/meeting_baselines.py), so every field here is already safe
// to render as-is — no separate deep/full view exists on this surface.
export interface WatchException {
  test_id: string;
  threshold_kind: "any_occurrence" | "percentile" | "ratio" | "absolute";
  baseline_median: number | null;
  // Scripted, never authored, and never a claim about anyone (C.2) — safe
  // to render verbatim, unlike `finding`/`verdict`.
  why: string;
  stat: Record<string, unknown> | null;
  finding: string;
  verdict: string;
  valence: Valence;
  severity: string;
}

export interface WatchProvenance {
  pdf_filename: string | null;
  pdf_url: string | null;
  extracted_at: string | null;
  run_id: string | null;
  run_id_count: number;
  model: string | null;
  validation_status: string | null;
  coverage_ratio: number | null;
}

export interface WatchMeeting {
  meeting_id: number;
  meeting_date: string;
  meeting_type: string;
  body_class: string;
  counts: { items: number; motions: number; other_items: number };
  tests: { run: number; exceptions: number; within_baseline: number };
  exceptions: WatchException[];
  exceptions_withheld: number;
  provenance: WatchProvenance;
}

export interface WatchData {
  council: string;
  generated_at: string;
  n_meetings: number;
  meetings: WatchMeeting[];
}

// The extraction-quality record behind `/method`
// (docs/frontend/METHOD_PAGE_PLAN.md, B.6) — every metric is an object
// carrying its own source file and that file's generated_at, never a bare
// number, so a stale figure is stale on its face. A missing or unparseable
// source is `{value: null, reason: "source_missing", ...}` rather than a
// zero.
export interface MethodSourcedValue<T> {
  value: T | null;
  source: string;
  generated_at: string | null;
  n: number | null;
  reason?: string;
}

export interface MethodYearRow {
  year: number;
  censused: number | null;
  documents_in_db: number;
  minutes_in_db: number;
}

// Inventory agreement (docs/frontend/METHOD_PAGE_PLAN.md B.6) has no
// aggregate in either summary file — only a per-entity-type, per-document
// flag list in report.txt's sample-side detail. `reason` is
// "no_aggregate_in_source" here, distinct from "source_missing" (the file
// exists and is valid; it just doesn't compute this aggregate).
export interface MethodInventoryAgreementFlag {
  flagged_count: number;
  docs: { filename: string; l1: string; extracted: string; ratio: string }[];
}

export interface MethodMetric {
  definition: string | null;
  target: string | null;
  means_if_failed: string;
  full_corpus: MethodSourcedValue<number>;
  sample: MethodSourcedValue<number> & {
    flagged_entity_types?: Record<string, MethodInventoryAgreementFlag>;
  };
}

// Present: {pass, review, fail, errors, source, generated_at, n} (full
// corpus) or {pass, review, fail, converged, source, generated_at, n}
// (sample) — no `value` key at all. Missing/malformed source: `value: null`
// plus `reason`, per MethodSourcedValue. Two genuinely different shapes for
// the same field, both real (src/analysis/method.py), so this type is a
// union rather than forcing one shape to fit the other.
export type MethodValidationSplit =
  | { pass: number; review: number; fail: number; errors?: number; converged?: boolean;
      source: string; generated_at: string | null; n: number | null }
  | MethodSourcedValue<null>;

export interface MethodSamplePerFileRow {
  filename: string;
  meeting_date: string;
  paraphrase_pct: number;
  coverage_pct: number;
  keyword_gap_pct: number;
  status: "PASS" | "REVIEW" | "FAIL";
}

// One error instance from extraction_errors.json — carries the full raw LLM
// response and Pydantic message, neither of which this page renders (B.4:
// framed as one batch with error *classes*, never a per-document dump).
// Typed for completeness/future use; MethodPage only reads `.length`.
export interface MethodExtractionError {
  filename: string;
  error_class: string;
  error_type: string;
  error_message: string;
  raw_llm_response?: string;
}

// docs/frontend/METHOD_PAGE_PLAN.md B.4: "labelled as one batch, or left
// off" — 341 attempted against however many documents are in the database
// now, never rendered as a corpus-wide rate. Present/missing is a union for
// the same reason as MethodValidationSplit above (src/analysis/method.py's
// `_build_extraction_batch()`: no `value` key when the batch record exists).
export type MethodExtractionBatch =
  | {
      batch_id: string; attempted: number; succeeded: number; failed: number;
      errors_by_class: Record<string, MethodExtractionError[]>;
      note: string; source: string; generated_at: string | null; n: number | null;
    }
  | MethodSourcedValue<null>;

// The evidence chain (docs/frontend/EVIDENCE_CHAIN_PLAN.md Part C):
// resolve_evidence()'s full output — every quote behind one entity, each
// carrying a match tier computed at request time (B.2), never char_offset.
export type EvidenceTier = "exact" | "normalised" | "stripped" | "paraphrase";

export interface EvidenceQuote {
  text: string;
  tier: EvidenceTier;
  char_offset: number | null;
  resolved_offset: number | null;
  resolved_against: "pdf" | "minutes_text" | null;
}

export interface EvidenceDocument {
  filename: string | null;
  url: string | null;
  page: number | null;
}

export interface EvidenceEntry {
  entity_table: string;
  entity_id: number;
  role: string;
  meeting_id: number | null;
  meeting_date: string | null;
  document: EvidenceDocument | null;
  quotes: EvidenceQuote[];
  tier?: "no_evidence"; // present only when quotes is empty (B.5)
}

export interface OfficerRatificationPair {
  meeting_date: string | null;
  item_number: string | null;
  title: string;
  diverged: boolean;
  council_outcome: string | null;
  agenda_motion: EvidenceEntry | null;
  minutes_motion: EvidenceEntry | null;
}

export interface OfficerRatificationEvidence {
  pairs: OfficerRatificationPair[];
}

// docs/frontend/EVIDENCE_CHAIN_PLAN.md Step 6 — deliberately carries only
// EvidenceEntry (Part C), not dose.json's business fields (reference,
// address, description, outcome). Joined to dose.json by entity_id.
export interface ObjectionResponsivenessBucket {
  label: string;
  applications: EvidenceEntry[];
}

export interface ObjectionResponsivenessEvidence {
  buckets: ObjectionResponsivenessBucket[];
}

// Deliberately carries only EvidenceEntry (Part C), not transparency.json's
// business fields (description, amount, date). Joined to it by
// (entity_table, entity_id).
export interface TransparencyEvidenceYear {
  year: number;
  items: EvidenceEntry[];
}

export interface TransparencyEvidence {
  years: TransparencyEvidenceYear[];
}

// Deliberately carries only EvidenceEntry (Part C), not mayoral.json's
// business fields (title, date, votes_for/against). Joined to it by
// entity_id — a mayor with zero qualifying motions is simply absent here.
export interface ChairCaptureMayor {
  name: string;
  motions: EvidenceEntry[];
}

export interface ChairCaptureEvidence {
  mayors: ChairCaptureMayor[];
}

// ConflictRecusalPanel's drill-down is per-councillor, not chart-bar driven —
// a flat list, not buckets. The frontend builds one Map<entity_id,
// EvidenceEntry> from it and looks each DeclarationDetail up by its own
// entity_id (interest_declarations.id); a declaration with no matched
// InterestDeclaration row (entity_id: null) has nothing to look up.
export interface RecusalManagementEvidence {
  entries: EvidenceEntry[];
}

// RecusalTrendPanel's drill-down is per-cell (interest type × era), also
// flat rather than chart-bar buckets — same lookup convention as
// RecusalManagementEvidence above.
export interface RecusalTrendEvidence {
  entries: EvidenceEntry[];
}

// PowerPanel's per-councillor drill-down, also flat — same lookup
// convention as RecusalManagementEvidence/RecusalTrendEvidence above.
export interface PowerSpreadEvidence {
  entries: EvidenceEntry[];
}

// QuestionResponsivenessPanel's per-era drill-down, also flat — same
// lookup convention as the other per-councillor/per-cell evidence files.
export interface QuestionResponsivenessEvidence {
  entries: EvidenceEntry[];
}

// TenderConcentrationPanel's per-contractor drill-down, also flat — same
// lookup convention as the other per-cell/per-profile evidence files.
export interface ConcentrationEvidence {
  entries: EvidenceEntry[];
}

// The tests.<generator> group's shared shape (docs/frontend/
// EVIDENCE_CHAIN_PLAN.md Step 6): unlike the tests above, these have no
// bespoke panel — BatteryTestBody's one generic drill-down reads this same
// shape for every test in the group, so `label` must match the chart bar/
// point label exactly and the field is always "entries", never a
// test-specific name.
export interface GenericBatteryEvidenceBucket {
  label: string;
  entries: EvidenceEntry[];
}

export interface GenericBatteryEvidence {
  buckets: GenericBatteryEvidenceBucket[];
}

// Exported (unlike the internal getSnapshot()) because the caller supplies
// the test id at call time — BatteryTestBody fetches lazily, per test,
// on first click, rather than through a named api.evidenceX() method.
export function evidenceForBatteryTest(testId: string): Promise<GenericBatteryEvidence> {
  return getSnapshot<GenericBatteryEvidence>(`evidence/${testId}`);
}

export interface MethodData {
  council: string;
  generated_at: string;
  coverage: {
    census_total: MethodSourcedValue<number>;
    by_year: MethodYearRow[];
    type_mix: MethodSourcedValue<Record<string, number>>;
    document_flags: MethodSourcedValue<Record<string, number>>;
  };
  validation: {
    metrics: {
      quote_completeness: MethodMetric;
      paraphrase_rate: MethodMetric;
      coverage_ratio: MethodMetric;
      inventory_agreement: MethodMetric;
      keyword_gap_rate: MethodMetric;
    };
    full_corpus_split: MethodValidationSplit;
    sample_split: MethodValidationSplit;
    sample_per_file: MethodSourcedValue<MethodSamplePerFileRow[]>;
    schema_flags: MethodSourcedValue<number> & { flagged_files?: string[] };
  };
  extraction_batch: MethodExtractionBatch;
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
  questionResponsiveness: () => getSnapshot<QuestionResponsivenessData>("question-responsiveness"),
  sponsorship:  () => getSnapshot<SponsorshipData>("sponsorship"),
  overview:     () => getSnapshot<OverviewData>("overview"),
  councillors:  () => getSnapshot<CouncillorsData>("councillors"),
  // Published (docs/frontend/WATCH_FEED_PLAN.md B.3) — renders in both Draft
  // and Publish mode via the normal getSnapshot() path, unlike the old
  // local-review-only digest it replaces.
  watch:        () => getSnapshot<WatchData>("watch"),
  // Published (docs/frontend/METHOD_PAGE_PLAN.md B.6) — the extraction-quality
  // record. Not claim-derived, defaults to full tier like most snapshots
  // (src/cli.py SNAPSHOT_TIER) until a human decision promotes it to public.
  method:       () => getSnapshot<MethodData>("method"),
  // docs/frontend/EVIDENCE_CHAIN_PLAN.md Step 3 — full tier like `method`
  // above (never in SNAPSHOT_TIER). Not wired into any panel yet (Step 5).
  evidenceOfficerRatification: () =>
    getSnapshot<OfficerRatificationEvidence>("evidence/governance.officer_ratification"),
  evidenceObjectionResponsiveness: () =>
    getSnapshot<ObjectionResponsivenessEvidence>("evidence/planning.objection_responsiveness"),
  evidenceTransparency: () =>
    getSnapshot<TransparencyEvidence>("evidence/transparency.confidential_share"),
  evidenceChairCapture: () =>
    getSnapshot<ChairCaptureEvidence>("evidence/governance.chair_capture"),
  evidenceRecusalManagement: () =>
    getSnapshot<RecusalManagementEvidence>("evidence/conflict.recusal_management"),
  evidenceRecusalTrend: () =>
    getSnapshot<RecusalTrendEvidence>("evidence/conflict.recusal_trend"),
  evidencePowerSpread: () =>
    getSnapshot<PowerSpreadEvidence>("evidence/governance.power_spread"),
  evidenceQuestionResponsiveness: () =>
    getSnapshot<QuestionResponsivenessEvidence>("evidence/engagement.question_responsiveness"),
  evidenceConcentration: () =>
    getSnapshot<ConcentrationEvidence>("evidence/procurement.concentration"),
};
