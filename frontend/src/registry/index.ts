// Joins config/test_registry.json (the static half of a test) with a
// snapshot's `tests` array (the computed half) into ResolvedTest[]. Every
// frontend surface should end up consuming resolveTests()'s output and
// nothing else — see docs/frontend/TEST_REGISTRY_PLAN.md Part C.

import registryData from "@registry"
import type { ScorecardTest } from "../api"
import { CATEGORY_ORDER, type ResolvedTest, type Severity, type TestRegistryEntry } from "./types"

export const REGISTRY: TestRegistryEntry[] = registryData as unknown as TestRegistryEntry[]

export const REGISTRY_BY_ID: Record<string, TestRegistryEntry> = Object.fromEntries(
  REGISTRY.map((row) => [row.id, row]),
)

const VALENCE_ORDER: Record<string, number> = { critical: 0, neutral: 1, supportive: 2 }
const CATEGORY_RANK: Record<string, number> = Object.fromEntries(
  CATEGORY_ORDER.map((category, i) => [category, i]),
)

// scorecard.json / digest.json carry `scope` (src/analysis/tests.py's
// TestResult.scope) even though ScorecardTest doesn't declare it — nothing
// in the frontend has read it before resolveTests().
type SnapshotTest = ScorecardTest & { scope?: string[] }

export function resolveTests(snapshotTests: ScorecardTest[]): ResolvedTest[] {
  const bySnapshotId = new Map<string, SnapshotTest>(
    (snapshotTests as SnapshotTest[]).map((t) => [t.test_id, t]),
  )
  const resolved: ResolvedTest[] = []

  for (const row of REGISTRY) {
    const snap = bySnapshotId.get(row.id)
    if (!snap) {
      console.error(`resolveTests: registry row "${row.id}" has no matching snapshot test — skipped`)
      continue
    }
    bySnapshotId.delete(row.id)
    resolved.push({
      ...row,
      finding: snap.headline,
      verdict: snap.verdict,
      valence: snap.valence,
      severity: snap.grade as Severity,
      data_ok: snap.data_ok,
      n: snap.n,
      base_rate: snap.base_rate,
      era: snap.era,
      scope: snap.scope ?? [],
      chart: snap.chart,
      series: snap.series,
    })
  }

  for (const orphan of bySnapshotId.values()) {
    console.error(`resolveTests: snapshot test "${orphan.test_id}" has no matching registry row — skipped`)
  }

  resolved.sort((a, b) => {
    const byCategory = CATEGORY_RANK[a.category] - CATEGORY_RANK[b.category]
    if (byCategory !== 0) return byCategory
    const byValence = VALENCE_ORDER[a.valence] - VALENCE_ORDER[b.valence]
    if (byValence !== 0) return byValence
    return a.order - b.order
  })

  return resolved
}
