import { Severity } from "../registry/types";

type SeverityTier = "strength" | "observation" | "concern" | "nodata";

// One fixed map from each of the seven G_* grades (src/analysis/tests.py) to
// a visual tier + ladder rank, per PANEL_FRAMING_PLAN.md B.7. The ladder's
// semantics are untouched — no test is re-graded — this only groups the
// grades for a reader to place at a glance. `rank` runs top (best, 1) to
// bottom (worst) of the ladder; "Not computable" isn't a graded position on
// it, so it's ranked 0 rather than implied worse than "Integrity flag".
const SEVERITY_META: Record<Severity, { tier: SeverityTier; rank: number; label: string }> = {
  "Commendable":                    { tier: "strength",    rank: 1, label: "Commendable" },
  "Good-governance strength":       { tier: "strength",    rank: 2, label: "Good-governance strength" },
  "Sound practice":                 { tier: "strength",    rank: 3, label: "Sound practice" },
  "Observation":                    { tier: "observation", rank: 4, label: "Observation" },
  "Governance concern":             { tier: "concern",     rank: 5, label: "Governance concern" },
  "Integrity flag":                 { tier: "concern",     rank: 6, label: "Integrity flag" },
  "Not computable on this corpus":  { tier: "nodata",      rank: 0, label: "Not computable on this corpus" },
};

// A fixed-vocabulary chip that groups the battery's seven severity grades
// into four visual tiers (strength / observation / concern / no data), same
// shape and placement discipline as ValenceChip. The label is always the
// grade string itself — never prefixed with the word "Severity:".
export function SeverityChip({ severity }: { severity: Severity }) {
  const meta = SEVERITY_META[severity];
  return <span className={`severity-chip severity-${meta.tier}`}>{meta.label}</span>;
}
