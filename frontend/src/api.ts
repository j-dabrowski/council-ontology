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

export const api = {
  interests:  () => getSnapshot<InterestSummary[]>("interests"),
  divergence: () => getSnapshot<DivergenceData>("divergence"),
  coMovers:   () => getSnapshot<CoMoverData>("co-movers"),
  alignment:  () => getSnapshot<{ pairs: AlignmentPair[] }>("alignment"),
  trends:     () => getSnapshot<TrendsData>("trends"),
  engagement: () => getSnapshot<EngagementStat[]>("engagement"),
  planning:   () => getSnapshot<PlanningData>("planning"),
  dissent:    () => getSnapshot<DissentData>("dissent"),
};
