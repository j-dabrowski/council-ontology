import { useMemo, useState } from "react";
import { CouncilHeader } from "../components/CouncilHeader";
import { LoadingCard, ErrorCard } from "../components/InterestsChart";
import { BatteryTestCard } from "../components/BatteryTestPanel";
import { useData } from "../hooks/useData";
import { api, WatchData, WatchMeeting, WatchException, CouncillorsData } from "../api";
import { REGISTRY_BY_ID } from "../registry";
import type { ResolvedTest } from "../registry/types";
import { useScrollToMeeting } from "../registry/anchors";

const PAGE_SIZE = 50;

// A watch.json exception carries only the fields a meeting's claim actually
// computed (test_id, why, stat, finding/verdict/valence/severity) — none of
// the corpus-wide numbers (n, base_rate, era, chart) a ResolvedTest normally
// carries from scorecard.json, and no meeting-scoped title/question (those
// don't exist on this surface yet — WATCH_FEED_PLAN.md Step 10). Join the
// static registry half in and leave the rest null/empty so the existing
// BatteryTestCard can render it unmodified.
function resolveException(exc: WatchException): ResolvedTest | null {
  const row = REGISTRY_BY_ID[exc.test_id];
  if (!row) {
    console.error(`WatchPage: exception test_id "${exc.test_id}" has no registry row — skipped`);
    return null;
  }
  return {
    ...row,
    finding: exc.finding,
    verdict: exc.verdict,
    valence: exc.valence,
    severity: exc.severity as ResolvedTest["severity"],
    data_ok: true,
    n: null,
    base_rate: null,
    era: null,
    scope: [],
    chart: null,
    series: [],
  };
}

function formatDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-AU", {
    day: "numeric", month: "long", year: "numeric",
  });
}

function ProvenanceFooter({ provenance: p }: { provenance: WatchMeeting["provenance"] }) {
  return (
    <dl className="watch-provenance">
      <div>
        <dt>Source</dt>
        <dd>
          {p.pdf_filename
            ? (p.pdf_url ? <a href={p.pdf_url} target="_blank" rel="noopener noreferrer">{p.pdf_filename}</a> : p.pdf_filename)
            : "not recorded"}
        </dd>
      </div>
      <div>
        <dt>Extracted</dt>
        <dd>{p.extracted_at ?? "not recorded"}</dd>
      </div>
      <div>
        <dt>Run</dt>
        <dd>
          {p.run_id ?? "not recorded"}
          {p.run_id_count > 1 && ` +${p.run_id_count - 1} earlier`}
        </dd>
      </div>
      <div>
        <dt>Model</dt>
        <dd>{p.model ?? "not recorded"}</dd>
      </div>
      <div>
        <dt>Validation</dt>
        <dd>
          {p.validation_status ?? "not recorded"}
          {p.coverage_ratio != null && ` (coverage ${(p.coverage_ratio * 100).toFixed(1)}%)`}
        </dd>
      </div>
    </dl>
  );
}

function MotionsSection({ motions }: { motions: WatchMeeting["motions"] }) {
  return (
    <div className="watch-motions-section">
      <h4 className="watch-motions-heading">What was decided</h4>
      {motions.length === 0 ? (
        <p className="watch-motions-empty">No items extracted for this meeting.</p>
      ) : (
        <ul className="watch-motions">
          {motions.map((m, i) => (
            <li className="watch-motion" key={i}>
              <div className="watch-motion-head">
                {m.item_number && <span className="watch-motion-number">{m.item_number}</span>}
                <span className="watch-motion-title">{m.title}</span>
                {m.outcome && <span className="watch-motion-outcome">{m.outcome}</span>}
              </div>
              {m.description && <p className="watch-motion-desc">{m.description}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function WatchRow({
  row, cllrData, open, onToggle,
}: {
  row: WatchMeeting; cllrData: CouncillorsData | null; open: boolean; onToggle: () => void;
}) {
  const { counts, tests } = row;
  const summary = tests.exceptions === 0
    ? `nothing outside baseline · ${tests.run} tests run, all within norms`
    : `${tests.exceptions} outside baseline · ${tests.run} tests run`;

  return (
    <div className="watch-row" data-meeting-id={row.meeting_id}>
      <button className="watch-row-toggle" onClick={onToggle} aria-expanded={open}>
        <span className="watch-row-mark">{open ? "▾" : "▸"}</span>
        <span className="watch-row-date">{formatDate(row.meeting_date)}</span>
        <span className="watch-row-type">{row.meeting_type}</span>
        <span className="watch-row-summary">
          {counts.items} items, {counts.motions} motions · {summary}
        </span>
      </button>
      {open && (
        <div className="watch-row-detail">
          <MotionsSection motions={row.motions} />
          {row.exceptions.map((exc) => {
            const resolved = resolveException(exc);
            if (!resolved) return null;
            return (
              <div className="watch-exception" key={exc.test_id}>
                <BatteryTestCard test={resolved} cllrData={cllrData} />
                <p className="watch-why">{exc.why}</p>
              </div>
            );
          })}
          {row.exceptions_withheld > 0 && (
            <p className="watch-withheld">
              {row.exceptions_withheld} additional exception{row.exceptions_withheld === 1 ? "" : "s"} withheld
              from this public feed.
            </p>
          )}
          <ProvenanceFooter provenance={row.provenance} />
        </div>
      )}
    </div>
  );
}

export function WatchPage() {
  const { data, loading, error } = useData<WatchData>(() => api.watch());
  const { data: cllrData } = useData<CouncillorsData>(() => api.councillors());
  const [page, setPage] = useState(0);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  // docs/frontend/WATCH_FEED_PLAN.md Step 7 — the OverviewPage strip links
  // to #/watch?meeting=<id>; WatchPage's rows start collapsed, unlike a
  // scorecard/analysis row, so arriving via that link must also expand the
  // named row, not just scroll to it.
  useScrollToMeeting((meetingId) => {
    setExpandedIds((prev) => (prev.has(meetingId) ? prev : new Set(prev).add(meetingId)));
  });

  const pageCount = data ? Math.max(1, Math.ceil(data.meetings.length / PAGE_SIZE)) : 1;
  const pageRows = useMemo(
    () => (data ? data.meetings.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE) : []),
    [data, page],
  );

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const toggle = (meetingId: number) => setExpandedIds((prev) => {
    const next = new Set(prev);
    if (next.has(meetingId)) next.delete(meetingId); else next.add(meetingId);
    return next;
  });

  return (
    <div className="app">
      <CouncilHeader />
      <main className="watch-page">
        <p className="chart-note">
          {data.n_meetings.toLocaleString()} meetings, newest first.
        </p>
        <div className="watch-feed">
          {pageRows.map((row) => (
            <WatchRow
              key={row.meeting_id}
              row={row}
              cllrData={cllrData}
              open={expandedIds.has(row.meeting_id)}
              onToggle={() => toggle(row.meeting_id)}
            />
          ))}
        </div>
        {pageCount > 1 && (
          <div className="watch-pager">
            <button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>← Newer</button>
            <span>Page {page + 1} of {pageCount}</span>
            <button disabled={page >= pageCount - 1} onClick={() => setPage((p) => p + 1)}>Older →</button>
          </div>
        )}
      </main>
      <footer className="site-footer">
        <p>
          Source: Town of Cambridge council meeting minutes (public record) ·
          Data extracted via Anthropic Claude ·{" "}
          <a
            href="https://www.cambridge.wa.gov.au/council/council-meetings"
            target="_blank"
            rel="noopener noreferrer"
          >
            cambridge.wa.gov.au
          </a>
        </p>
      </footer>
    </div>
  );
}
