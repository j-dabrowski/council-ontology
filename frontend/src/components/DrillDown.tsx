import { useEffect, useRef, useState } from "react";
import type { EvidenceEntry, EvidenceQuote } from "../api";

/**
 * Reusable drill-down drawer. A panel renders this below its chart when the
 * user clicks an element (a bar, a row, a cell) to inspect the underlying
 * records. Generic on purpose — each panel supplies its own row rendering as
 * children. Pair with <SourceQuote/> for the verbatim "receipt".
 */
export function DrillDown({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: React.ReactNode;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // When opened (or the selection changes), bring the drawer into view.
  useEffect(() => {
    ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [title]);
  return (
    <div className="drill" role="region" aria-label={typeof title === "string" ? title : undefined} ref={ref}>
      <div className="drill-head">
        <div className="drill-head-titles">
          <span className="drill-title">{title}</span>
          {subtitle && <span className="drill-subtitle">{subtitle}</span>}
        </div>
        <button className="drill-close" onClick={onClose} aria-label="Close detail">
          ✕
        </button>
      </div>
      <div className="drill-body">{children}</div>
    </div>
  );
}

/**
 * Gates a named-individual claim (a specific person + a specific stat) behind
 * an explicit click rather than rendering it as a standing headline note —
 * the mitigation docs/strategy/PRIVATE_ASSESSMENT.md calls for wherever a
 * panel would otherwise single someone out in always-visible chart-note prose.
 */
export function Reveal({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="reveal">
      <button className="src-toggle" onClick={() => setOpen((o) => !o)}>
        {open ? "▾" : "▸"} {label}
      </button>
      {open && <span className="reveal-body">{children}</span>}
    </span>
  );
}

/**
 * The provenance "receipt": a collapsed toggle that reveals the verbatim minute
 * text an extracted fact came from. The credibility multiplier — and reusable
 * anywhere an entity has an extraction_evidence quote.
 *
 * Two call shapes:
 *  - `quote` — the legacy one-quote-per-entity join every panel but
 *    DivergencePanel still uses (src/cli.py's inline joins,
 *    docs/frontend/EVIDENCE_CHAIN_PLAN.md A.5): a bare string or null, no
 *    tier information. Unchanged behaviour, just no more `.trim()` — the
 *    quote is returned unmodified from the database and rendered that way
 *    (B.6); a stray leading/trailing space belongs to the source PDF's
 *    extraction, not something to silently tidy away.
 *  - `entry` — resolve_evidence()'s full output (EVIDENCE_CHAIN_PLAN.md
 *    Part C): every quote behind one entity, each carrying a match tier
 *    computed at request time (B.2), plus the document it came from.
 *    Renders the four-tier vocabulary and B.5's "no source quote recorded"
 *    for an entity with none.
 */
export function SourceQuote(
  props:
    | { quote: string | null; entry?: undefined }
    | { entry: EvidenceEntry | null; quote?: undefined }
) {
  const [open, setOpen] = useState(false);

  if ("entry" in props) {
    const { entry } = props;
    if (!entry || entry.quotes.length === 0) {
      return <span className="src-none">no source quote recorded</span>;
    }
    const doc = entry.document;
    return (
      <div className="src">
        <button className="src-toggle" onClick={() => setOpen((o) => !o)}>
          {open ? "▾" : "▸"} source from the minutes
          {entry.quotes.length > 1 ? ` (${entry.quotes.length})` : ""}
        </button>
        {open && (
          <div className="src-detail">
            {entry.quotes.map((q, i) => (
              <EvidenceQuoteBlock key={i} quote={q} />
            ))}
            {doc && (
              <p className="src-doc">
                {doc.filename ?? "document not recorded"}
                {entry.meeting_date && <> · {entry.meeting_date}</>}
                {" · "}
                {doc.page != null ? `page ${doc.page}` : "page not recorded"}
                {doc.url && (
                  <>
                    {" · "}
                    <a href={doc.url} target="_blank" rel="noreferrer">source PDF</a>
                  </>
                )}
              </p>
            )}
          </div>
        )}
      </div>
    );
  }

  const { quote } = props;
  if (!quote) return <span className="src-none">no source quote extracted</span>;
  return (
    <div className="src">
      <button className="src-toggle" onClick={() => setOpen((o) => !o)}>
        {open ? "▾" : "▸"} source from the minutes
      </button>
      {open && <blockquote className="src-quote">“{quote}”</blockquote>}
    </div>
  );
}

function EvidenceQuoteBlock({ quote }: { quote: EvidenceQuote }) {
  if (quote.tier === "paraphrase") {
    return (
      <div className="src-paraphrase">
        <span className="src-tier-flag">paraphrase — not found verbatim in the source</span>
        <p className="src-paraphrase-text">{quote.text}</p>
      </div>
    );
  }
  return (
    <blockquote className="src-quote">
      “{quote.text}”
      {quote.tier === "stripped" && (
        <span className="src-tier-flag src-tier-flag-inline">
          matched allowing for PDF text artefacts
        </span>
      )}
    </blockquote>
  );
}
