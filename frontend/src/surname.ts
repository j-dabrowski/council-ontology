// Display surname from a full name string.
//
// Snapshots carry only a single `name` string, so panels that label a chart
// axis with a surname have to derive one. The naive `split(" ").slice(-1)[0]`
// this replaces truncated multi-token surnames to their last word — the
// corpus's one affected councillor, "Michael Le Page", rendered everywhere as
// "Page", which is not their name and made them unfindable on the page.
//
// Walks back from the final token, absorbing the nobiliary/toponymic
// particles that are part of the surname rather than separators.
const PARTICLES = new Set([
  "le", "la", "de", "del", "della", "di", "da", "dos", "das",
  "van", "von", "der", "den", "ter", "ten", "st", "st.",
]);

export function surname(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length <= 1) return name;
  let i = parts.length - 1;
  while (i > 1 && PARTICLES.has(parts[i - 1].toLowerCase())) i--;
  return parts.slice(i).join(" ");
}

// Every form a councillor's surname may appear as in prose — the
// particle-aware surname plus the bare final token. Used by the scorecard's
// name-redaction guardrail, where matching too little is the dangerous
// direction: "Le Page" must be caught, and "Page" must stay caught too.
export function surnameForms(name: string): string[] {
  const full = surname(name);
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const bare = parts[parts.length - 1] ?? name;
  return full === bare ? [full] : [full, bare];
}
