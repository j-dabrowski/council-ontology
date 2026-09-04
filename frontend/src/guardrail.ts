import { surnameForms } from "./surname";

// Structural guardrail: a test's headline/verdict must never carry a named
// individual through this always-visible slot unnoticed — any valence, not
// just critical, since a supportive-valence test about the council can still
// contain an unflattering clause about one person (see docs/review, BLOCKING
// flag 4, 2026-08-22 pass 1). A hit is redacted in the rendered output itself
// (not just logged) — a console-only warning is invisible to anyone without
// devtools open, which is exactly the audience this guards.
export function findNamedCouncillorsInText(text: string, councillorNames: string[]): string[] {
  return councillorNames.filter((name) => {
    // Both the particle-aware surname ("Le Page") and the bare last token
    // ("Page") — a redaction guardrail must never match less than before.
    return surnameForms(name).some((f) => f.length > 2 && text.includes(f));
  });
}

export function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function redactNamedCouncillors(text: string, names: string[]): string {
  if (!names.length) return text;
  const alternatives = names.flatMap((name) => {
    return [name, ...surnameForms(name)].map(escapeRegExp);
  });
  const pattern = new RegExp(alternatives.join("|"), "g");
  return text.replace(pattern, "[named individual — flagged for review]");
}
