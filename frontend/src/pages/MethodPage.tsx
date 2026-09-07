import { CouncilHeader } from "../components/CouncilHeader";
import { LoadingCard, ErrorCard } from "../components/InterestsChart";
import { useData } from "../hooks/useData";
import { api, MethodData, MethodSourcedValue, MethodYearRow } from "../api";

// docs/frontend/METHOD_PAGE_PLAN.md — the extraction-quality record. Every
// figure here reads straight off method.json; nothing is written as a
// default, a placeholder, or an example (the plan's standing rule). A gap
// in the source data renders as an explicit "not available" note, never a
// zero or a blank cell.

// UTC, not the viewer's local timezone: every generated_at in method.json
// is a UTC timestamp, and a reader west of Greenwich would otherwise see a
// date one day earlier/later than the source file's own — e.g.
// inventories/summary.json's 16:34 UTC rolls to the next calendar day
// anywhere UTC+8 or later.
function formatDate(iso: string | null): string {
  if (!iso) return "not recorded";
  return new Date(iso).toLocaleDateString("en-AU", {
    day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
  });
}

// B.1: "the page opens with the freshness table... so a reader sees the
// spread before any figure." Every date below is method.json's own
// generated_at for that file — nothing here is hand-typed, including the
// two source files (validation/summary.json, sample_validation/report.txt)
// whose own numbers this page doesn't render until later steps; only their
// dates are shown now, for the spread.
function FreshnessTable({ data }: { data: MethodData }) {
  const rows: { file: string; generatedAt: string | null }[] = [
    { file: "data/census.json", generatedAt: data.coverage.census_total.generated_at },
    { file: "data/inventories/summary.json", generatedAt: data.coverage.type_mix.generated_at },
    { file: "data/extraction_errors.json", generatedAt: data.extraction_batch.generated_at },
    { file: "data/validation/summary.json", generatedAt: data.validation.full_corpus_split.generated_at },
    { file: "data/sample_validation/report.txt", generatedAt: data.validation.sample_split.generated_at },
  ];
  return (
    <table className="method-table method-freshness-table">
      <thead>
        <tr><th>Source</th><th>Generated</th></tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.file}>
            <td><code>{r.file}</code></td>
            <td>{formatDate(r.generatedAt)}</td>
          </tr>
        ))}
        <tr>
          <td><code>data/council.db</code></td>
          <td>live — queried {formatDate(data.generated_at)}</td>
        </tr>
      </tbody>
    </table>
  );
}

// B.2: three columns, divergence drawn rather than smoothed. A year where
// the database exceeds the census (2022-2026 in the real corpus — the
// scraper ran again after the census did) is the normal, explainable case
// and must not read as an error, so the delta badge below uses the same
// informational blue as a link, never red.
function CoverageMatrix({ coverage, asOf }: { coverage: MethodData["coverage"]; asOf: string }) {
  const rows = [...coverage.by_year].sort((a, b) => b.year - a.year);
  if (rows.length === 0) {
    return <p className="chart-note">Coverage matrix not available — {coverage.census_total.reason ?? "no year data"}.</p>;
  }
  return (
    <>
      <p className="chart-note">
        Censused counts as of {formatDate(coverage.census_total.generated_at)} (<code>{coverage.census_total.source}</code>) ·
        documents/minutes in the database queried live, {formatDate(asOf)}.
      </p>
      <table className="method-table">
        <thead>
          <tr>
            <th>Year</th>
            <th>Censused</th>
            <th>Documents in database</th>
            <th>Minutes in database</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r: MethodYearRow) => {
            const delta = r.censused != null ? r.documents_in_db - r.censused : null;
            return (
              <tr key={r.year}>
                <td className="method-year-cell">{r.year}</td>
                <td>{r.censused ?? "—"}</td>
                <td>
                  {r.documents_in_db}
                  {delta !== null && delta !== 0 && (
                    <span className="method-delta">{delta > 0 ? `+${delta}` : delta}</span>
                  )}
                </td>
                <td>{r.minutes_in_db}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}

function SourceCaption({ v }: { v: MethodSourcedValue<unknown> }) {
  if (v.value == null) {
    return <p className="chart-note">Not available — {v.reason ?? "no data"} (<code>{v.source}</code>).</p>;
  }
  return (
    <p className="chart-note">
      As of {formatDate(v.generated_at)} · <code>{v.source}</code>{v.n != null && ` · n=${v.n}`}
    </p>
  );
}

function TallyTable({ tally }: { tally: Record<string, number> }) {
  const rows = Object.entries(tally).sort((a, b) => b[1] - a[1]);
  return (
    <table className="method-table method-table-compact">
      <tbody>
        {rows.map(([key, count]) => (
          <tr key={key}>
            <td>{key.replace(/_/g, " ")}</td>
            <td className="method-num-cell">{count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function MethodPage() {
  const { data, loading, error } = useData<MethodData>(() => api.method());

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  return (
    <div className="app">
      <CouncilHeader />
      <main className="method-page">
        <div className="static-hero">
          <h2 className="static-h1">Method</h2>
          <p className="static-lead">
            How this corpus was built, and how far its own audit files say it can be
            trusted — every figure below traces to one specific file, dated next to it.
          </p>
        </div>

        <div className="static-section">
          <h3 className="static-h2">Source freshness</h3>
          <FreshnessTable data={data} />
        </div>

        <div className="static-section">
          <h3 className="static-h2">Coverage</h3>
          <CoverageMatrix coverage={data.coverage} asOf={data.generated_at} />
          <p className="chart-note">
            This corpus's outer boundary is what has been downloaded — no file records
            what the council published but the scraper never fetched.
          </p>
        </div>

        <div className="static-section">
          <h3 className="static-h2">Meeting type mix</h3>
          <SourceCaption v={data.coverage.type_mix} />
          {data.coverage.type_mix.value && <TallyTable tally={data.coverage.type_mix.value} />}
        </div>

        <div className="static-section">
          <h3 className="static-h2">Document flags</h3>
          <SourceCaption v={data.coverage.document_flags} />
          {data.coverage.document_flags.value && <TallyTable tally={data.coverage.document_flags.value} />}
        </div>
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
