import { CATEGORY_LABEL, CATEGORY_ORDER, type ResolvedTest, type TestCategory } from "./types"

export interface TestGroup {
  name: string
  tests: ResolvedTest[]
}

// Buckets by `category`, in CATEGORY_ORDER — no regex over free-text genre,
// no "Other" bucket (Step 4's parity test guarantees every id has one of the
// four categories), and no dead "Planning & fairness" branch (see
// TEST_REGISTRY_PLAN.md A.3 point 3). Assumes `tests` is already
// valence-ordered within each category — resolveTests() sorts
// category -> valence -> order before this ever runs.
export function groupByCategory(tests: ResolvedTest[]): TestGroup[] {
  const buckets = new Map<TestCategory, ResolvedTest[]>(CATEGORY_ORDER.map((category) => [category, []]))
  for (const t of tests) {
    buckets.get(t.category)!.push(t)
  }
  return CATEGORY_ORDER
    .map((category) => ({ name: CATEGORY_LABEL[category], tests: buckets.get(category)! }))
    .filter((group) => group.tests.length > 0)
}
