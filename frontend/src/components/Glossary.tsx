// Jargon glossary (docs/uplift/migration/01-known-defects.md D-37/G-37):
// every governance-framework label and derived-statistic term used across
// panels, defined at its point of use via a hover/focus tooltip — not one
// static paragraph covering only the valence ladder (ScorecardPanel.tsx's
// existing note), and not a separate glossary page a reader has to go find.
//
// Scope of this pass: wired into every `principles` render (16 call sites,
// all identical `{" · "}{x.principles.join(" · ")}` — the one place every
// Nolan/CIPFA citation on every panel actually appears) via <Principles>.
// The other D-37 terms (lift, x N, DIRECTIONAL, base rate, matched votes,
// must-leave, impartiality interest, recusal, blended rate) are defined
// below but not yet auto-linked inside arbitrary headline/verdict prose —
// regex-matching a short common word like "lift" inside free text risks
// false-positive matches out of context, a follow-up pass with more
// tooling than this one needs, not attempted here. This term list may also
// need revisiting once 04-jurisdiction.md's WA-framework work lands and
// Nolan/CIPFA are demoted to a secondary mapping alongside the WA
// instruments — noted at that file's own Step 22 cross-reference.

import { useId, useState, type ReactNode } from "react";

export const GLOSSARY: Record<string, string> = {
  // Nolan Principles (UK 1995) — Investigator_prompt.txt Part 1.1, verbatim
  "Nolan Selflessness": "Decisions solely in the public interest, not for self, family, or friends.",
  "Nolan Integrity": "No obligations to outsiders who might influence you.",
  "Nolan Objectivity": "Decisions on merit, without bias.",
  "Nolan Accountability": "Submit to whatever scrutiny is appropriate.",
  "Nolan Openness": "Act and decide transparently; restrict information only with good reason.",
  "Nolan Honesty": "Truthful.",
  "Nolan Leadership": "Model these principles and challenge breaches in others.",
  // CIPFA / SOLACE "Delivering Good Governance in Local Government" (2016)
  // — Investigator_prompt.txt Part 1.2, verbatim
  "CIPFA-A": "Integrity, ethical values, rule of law — codes of conduct, interest declarations, whistleblowing arrangements.",
  "CIPFA-B": "Openness and comprehensive stakeholder engagement.",
  "CIPFA-C": "Defining outcomes in terms of sustainable economic/social/environmental benefits.",
  "CIPFA-D": "Determining the interventions to achieve those outcomes (incl. value for money).",
  "CIPFA-E": "Developing capacity — of the entity and of its leadership.",
  "CIPFA-F": "Managing risks and performance through robust internal control and strong public financial management.",
  "CIPFA-G": "Transparency, reporting and audit to deliver accountability.",
  // Derived-statistic vocabulary (not yet auto-linked in free text — see
  // module note above)
  "must-leave": "A financial or proximity interest that legally requires the councillor to leave the room and not vote — as opposed to an impartiality interest, which permits staying and voting.",
  "impartiality interest": "A declared interest type that lawfully permits a councillor to stay in the room and vote, unlike a must-leave (financial/proximity) interest.",
  "recusal": "A councillor stepping out of the room and not voting on an item, typically after declaring a conflict of interest.",
  "blended rate": "A recusal or compliance rate that pools every interest type together (financial, proximity, and impartiality) — can mask a genuine must-leave compliance problem behind a high volume of lawful impartiality stay-and-vote declarations, or vice versa.",
  "base rate": "The reference or comparison rate a finding is measured against — e.g. the chamber-wide average, or the rate an even/random spread would produce.",
  "lift": "The ratio of an observed rate to its base rate — a lift of 2x means the observed rate is twice the baseline.",
  "matched votes": "Votes successfully joined across two populations for a comparison (e.g. the same motion voted on by two different councillors) — not every vote in the corpus, only the subset that could be paired.",
  "DIRECTIONAL": "A finding whose direction (better/worse than baseline) is established from real data, but which hasn't cleared a higher evidentiary bar (e.g. a comparator council, a multiple-comparison correction) — reported as a real but provisional signal, not a settled conclusion.",
};

// Recognised tokens inside a `principles` string, longest-first so "CIPFA-A"
// matches before a bare "A" ever could, and multi-word Nolan names match
// before a shorter overlapping one.
const TOKEN_RE = new RegExp(
  Object.keys(GLOSSARY)
    .sort((a, b) => b.length - a.length)
    .map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|"),
  "g",
);

function Tooltip({ term, children }: { term: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const def = GLOSSARY[term];
  if (!def) return <>{children}</>;
  return (
    <span
      className="glossary-term"
      tabIndex={0}
      aria-describedby={id}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children}
      {open && (
        <span className="glossary-tooltip" role="tooltip" id={id}>
          {def}
        </span>
      )}
    </span>
  );
}

// Splits a principle string ("Nolan Integrity, Objectivity", "CIPFA-A/F")
// into its recognised jargon tokens, each wrapped with a definition
// tooltip, and the connecting punctuation left as plain text. Exported for
// the one caller (OverviewPanel.tsx) that renders a single principle
// string with no leading " · " separator — everywhere else, <Principles>.
export function GlossaryText({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  TOKEN_RE.lastIndex = 0;
  let i = 0;
  while ((match = TOKEN_RE.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    parts.push(<Tooltip key={i++} term={match[0]}>{match[0]}</Tooltip>);
    last = match.index + match[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts}</>;
}

/** Drop-in replacement for `{principles.join(" · ")}` with a leading
 * separator, used identically at all 16 call sites — every Nolan/CIPFA
 * citation on every panel becomes hoverable/focusable with its definition. */
export function Principles({ list }: { list: string[] }) {
  return (
    <>
      {list.map((p, i) => (
        <span key={i}>
          {" · "}
          <GlossaryText text={p} />
        </span>
      ))}
    </>
  );
}
