import { ScorecardTest, Valence } from "./api";

const VALENCE_ORDER: Record<Valence, number> = { critical: 0, neutral: 1, supportive: 2 };

// Genre pattern -> section name, in display order. Shared by ScorecardPanel
// (the summary rows) and AnalysisPage (the full per-test panels) so both
// stay in sync automatically — teaching a new genre pattern happens once,
// here, not in every place that groups tests by genre.
const ORDER: [string, (genre: string) => boolean][] = [
  ["Integrity & procurement", (g) => /procurement|conflict|integrity/i.test(g)],
  ["Governance & culture", (g) => /governance|culture/i.test(g)],
  ["Planning & fairness", (g) => /planning|fairness/i.test(g)],
  ["Transparency & engagement", (g) => /transparency|engagement/i.test(g)],
  ["Financial", (g) => /financial/i.test(g)],
];

export interface TestGroup {
  name: string;
  tests: ScorecardTest[];
}

// Assign each test to exactly one genre family (first match wins), then sort
// each family critical -> neutral -> supportive. Anything matching no known
// pattern lands in a trailing "Other" group rather than being dropped.
export function groupTestsByGenre(tests: ScorecardTest[]): TestGroup[] {
  const buckets = new Map<string, ScorecardTest[]>(ORDER.map(([name]) => [name, []]));
  const other: ScorecardTest[] = [];
  for (const t of tests) {
    const hit = ORDER.find(([, match]) => match(t.genre));
    (hit ? buckets.get(hit[0])! : other).push(t);
  }
  const groups = ORDER
    .map(([name]) => ({
      name,
      tests: buckets.get(name)!.sort((a, b) => VALENCE_ORDER[a.valence] - VALENCE_ORDER[b.valence]),
    }))
    .filter((g) => g.tests.length);
  if (other.length) groups.push({ name: "Other", tests: other });
  return groups;
}
