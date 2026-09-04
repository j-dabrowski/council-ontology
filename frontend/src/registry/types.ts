// Types for the canonical test registry (config/test_registry.json) and the
// ResolvedTest produced by joining a registry row with its snapshot row.
// See docs/frontend/TEST_REGISTRY_PLAN.md Part B for the field-by-field
// rationale; nothing here should diverge from that plan without updating it.

import type { TestChart, Valence } from "../api"

export type { Valence }

export type TestCategory =
  | "integrity_procurement"
  | "governance_culture"
  | "transparency_engagement"
  | "financial"

// The seven G_* grade labels from src/analysis/tests.py, verbatim — typed in
// full even though only five appear in the current run (B.6).
export type Severity =
  | "Sound practice"
  | "Good-governance strength"
  | "Commendable"
  | "Observation"
  | "Governance concern"
  | "Integrity flag"
  | "Not computable on this corpus"

// The static, council-agnostic half of a test — authored once in
// config/test_registry.json. Never carries a computed number or a finding.
export interface TestRegistryEntry {
  id: string
  code?: string
  order: number
  category: TestCategory
  question_technical: string
  question_public: string
  title_technical: string
  title_public: string
  principles: string[]
  method: string
  caveats: string[]
  objection: string | null
  response: string | null
  evidence_query: string
  evidence_snapshot: string | null
  has_deep_dive: boolean
  public_interest: boolean
  meeting_scope: boolean
  detail_panel: string
}

// One registry row joined with its snapshot row (scorecard.json / digest.json)
// on `id`. The computed half — everything below — changes every run and every
// council; see ScorecardTest in ../api.ts for where these types come from.
export interface ResolvedTest extends TestRegistryEntry {
  finding: string
  verdict: string
  valence: Valence
  severity: Severity
  data_ok: boolean
  n: number | null
  base_rate: string | null
  era: string | null
  scope: string[]
  chart: TestChart | null
  series: { x: number; y: number }[]
}

export const CATEGORY_ORDER: TestCategory[] = [
  "integrity_procurement",
  "governance_culture",
  "transparency_engagement",
  "financial",
]

export const CATEGORY_LABEL: Record<TestCategory, string> = {
  integrity_procurement: "Integrity & procurement",
  governance_culture: "Governance & culture",
  transparency_engagement: "Transparency & engagement",
  financial: "Financial",
}
