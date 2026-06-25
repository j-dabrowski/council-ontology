import { Valence } from "../api";

const LABELS: Record<Valence, string> = {
  supportive: "Supportive",
  neutral: "Neutral",
  critical: "Critical",
};

const ICONS: Record<Valence, string> = {
  supportive: "✓",
  neutral: "—",
  critical: "▲",
};

// A small good / neutral / bad flag so a reader can digest each finding's
// direction at a glance. `notComputable` overrides to a muted "no data" chip.
export function ValenceChip({
  valence,
  notComputable,
  label,
}: {
  valence: Valence;
  notComputable?: boolean;
  label?: string;
}) {
  if (notComputable) {
    return <span className="valence-chip valence-nodata">○ No data</span>;
  }
  return (
    <span className={`valence-chip valence-${valence}`}>
      {ICONS[valence]} {label ?? LABELS[valence]}
    </span>
  );
}
