import { surnameForms } from "./surname";
import patternData from "@patterns";

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

// The one guarded render path for any rendered string that might carry a
// named individual (PANEL_FRAMING_PLAN.md B.5's safety requirement — a
// guardrail that covers only some render paths is not a guardrail).
// Self-contained: pass the raw text and the full councillor name list, and
// this computes its own flagged set and its own redaction — no render path
// can drift from checking one thing while showing another. `testId`/`field`
// are for the console message only (e.g. testId="conflict.recusal_trend",
// field="finding").
export function RedactedText({
  text,
  names,
  testId,
  field,
}: {
  text: string;
  names: string[];
  testId?: string;
  field?: string;
}) {
  const flagged = findNamedCouncillorsInText(text, names);
  if (!flagged.length) return <>{text}</>;
  console.error(
    `[guardrail] test "${testId ?? "?"}" names ${flagged.join(", ")} in its ${field ?? "text"}` +
    ` — redacted in the rendered output pending review; see docs/review/editor/Editor_prompt.txt`
  );
  return (
    <>
      <div className="sc-row-guardrail">
        ⚠ Named-individual claim flagged for editorial review — redacted pending sign-off
      </div>
      {redactNamedCouncillors(text, flagged)}
    </>
  );
}

// Pattern-based redaction of PRIVATE individuals' names — a different
// problem from the councillor guardrail above (RECORD_PAGE_PLAN.md B.1).
// Private residents aren't a roster that can be matched by name; this
// matches shapes instead ("Owner:"/"Applicant:"/"Landowner:" field
// values, and bare Mr/Mrs/Ms/Dr-prefixed names) and mirrors
// src/privacy.py exactly — same docstring, same LIMITATION. The two are
// separate implementations (Python and TypeScript can't share compiled
// code) built from the one shared pattern definition at
// config/private_name_patterns.json, reached here via the @patterns
// Vite alias, so the pattern data itself can't drift between them even
// though the regex-building code is duplicated.
//
// LIMITATION, same as the Python side: a name with neither a label nor
// a personal title in front of it is not caught. Do not present this as
// complete.
interface PrivateNamePatterns {
  field_labels: string[];
  redacted_labels: string[];
  personal_titles: string[];
  placeholder: string;
}

const PATTERNS = patternData as unknown as PrivateNamePatterns;

function escapeAndJoin(items: string[]): string {
  return [...items].sort((a, b) => b.length - a.length).map(escapeRegExp).join("|");
}

const FIELD_ALT = escapeAndJoin(PATTERNS.field_labels);
const REDACTED_ALT = escapeAndJoin(PATTERNS.redacted_labels);
const TITLE_ALT = escapeAndJoin(PATTERNS.personal_titles);

// The lookahead's `\s+` (not `.*?`) owns the separating whitespace
// before the next field, so it survives the redaction instead of being
// swallowed into the removed span (src/privacy.py has the same fix).
const PRIVATE_LINE_RE = new RegExp(
  `\\b(?:${REDACTED_ALT})S?:\\s*.*?(?=\\n|$|\\s+(?:${FIELD_ALT})S?:)`,
  "gi",
);
const PRIVATE_TITLE_RE = new RegExp(
  `\\b(?:${TITLE_ALT})\\.?\\s+[A-Z][\\w'-]*(?:\\s+[A-Z][\\w'-]*){0,3}`,
  "g",
);

// Whole match (label, colon and value) is replaced by the placeholder —
// not just the value — so no "Owner:"/"Applicant:" string survives
// anywhere in a redacted payload (RECORD_PAGE_PLAN.md Step 3's payload
// test checks exactly that; B.1 says "lines removed", not "values
// redacted"). src/privacy.py has the identical fix and the same note.
export function redactPrivateNames(text: string | null | undefined): string | null | undefined {
  if (!text) return text;
  const withLinesRedacted = text.replace(PRIVATE_LINE_RE, PATTERNS.placeholder);
  return withLinesRedacted.replace(PRIVATE_TITLE_RE, PATTERNS.placeholder);
}

export function containsPrivateNamePattern(text: string | null | undefined): boolean {
  if (!text) return false;
  // Regexes are stateful (`g` flag) — reset lastIndex before each test
  // so a prior call's position doesn't cause a false negative.
  PRIVATE_LINE_RE.lastIndex = 0;
  PRIVATE_TITLE_RE.lastIndex = 0;
  return PRIVATE_LINE_RE.test(text) || PRIVATE_TITLE_RE.test(text);
}
