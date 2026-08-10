import { useEffect, useRef, useState } from "react";

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
 */
export function SourceQuote({ quote }: { quote: string | null }) {
  const [open, setOpen] = useState(false);
  if (!quote) return <span className="src-none">no source quote extracted</span>;
  return (
    <div className="src">
      <button className="src-toggle" onClick={() => setOpen((o) => !o)}>
        {open ? "▾" : "▸"} source from the minutes
      </button>
      {open && <blockquote className="src-quote">“{quote.trim()}”</blockquote>}
    </div>
  );
}
