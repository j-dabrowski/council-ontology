const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function get<T>(path: string, params?: Record<string, string | number | boolean>): Promise<T> {
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

export const api = {
  interests: (fromYear = 2024) => get<InterestSummary[]>("/api/interests", { from_year: fromYear }),
  divergence: (fromYear = 2024) => get<DivergenceData>("/api/divergence", { from_year: fromYear }),
  coMovers: (fromYear = 2024, activeOnly = true) =>
    get<CoMoverData>("/api/co-movers", { from_year: fromYear, active_only: activeOnly }),
  alignment: (fromYear = 2024, minShared = 10) =>
    get<{ pairs: AlignmentPair[] }>("/api/alignment", { from_year: fromYear, min_shared: minShared }),
  trends: (fromYear = 2024) => get<TrendsData>("/api/trends", { from_year: fromYear }),
  engagement: (fromYear = 2024) => get<EngagementStat[]>("/api/engagement", { from_year: fromYear }),
};
