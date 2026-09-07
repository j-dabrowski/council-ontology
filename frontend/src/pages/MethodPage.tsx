import { CouncilHeader } from "../components/CouncilHeader";
import { LoadingCard, ErrorCard } from "../components/InterestsChart";
import { useData } from "../hooks/useData";
import {
  api, MethodData, MethodSourcedValue, MethodYearRow, MethodMetric,
  MethodValidationSplit, MethodInventoryAgreementFlag, MethodSamplePerFileRow,
} from "../api";

const METRIC_ORDER = [
  "quote_completeness", "paraphrase_rate", "coverage_ratio",
  "inventory_agreement", "keyword_gap_rate",
] as const;

const METRIC_LABELS: Record<(typeof METRIC_ORDER)[number], string> = {
  quote_completeness: "Quote completeness",
  paraphrase_rate: "Paraphrase rate",
  coverage_ratio: "Coverage ratio",
  inventory_agreement: "Inventory agreement",
  keyword_gap_rate: "Keyword gap rate",
};

function formatPct(value: number | null): string {
  if (value == null) return "not available";
  return `${(value * 100).toFixed(1)}%`;
}

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

// B.3: both splits shown side by side, full corpus first — never averaged,
// never leading with the flattering sample. PASS/REVIEW/FAIL reuse the
// site's existing valence tally tile (ScorecardPanel's .sc-summary), so
// FAIL gets the same red the rest of the site uses for a critical finding —
// legible, not softened, not a new colour invented for this page.
function SplitTiles({ label, split }: { label: string; split: MethodValidationSplit }) {
  if (!("pass" in split)) {
    return <p className="chart-note">{label}: not available — {split.reason ?? "no data"} (<code>{split.source}</code>).</p>;
  }
  return (
    <div className="method-split">
      <p className="chart-note">
        {label} · n={split.n} · as of {formatDate(split.generated_at)} · <code>{split.source}</code>
      </p>
      <div className="sc-summary method-split-summary">
        <div className="sc-summary-item sc-supportive">
          <span className="sc-summary-num">{split.pass}</span>
          <span className="sc-summary-label">PASS</span>
        </div>
        <div className="sc-summary-item sc-neutral">
          <span className="sc-summary-num">{split.review}</span>
          <span className="sc-summary-label">REVIEW</span>
        </div>
        <div className="sc-summary-item sc-critical">
          <span className="sc-summary-num">{split.fail}</span>
          <span className="sc-summary-label">FAIL</span>
        </div>
      </div>
    </div>
  );
}

function MetricValue({ label, v }: { label: string; v: MethodSourcedValue<number> }) {
  return (
    <div className="method-metric-value">
      <span className="method-metric-value-label">{label}</span>
      <span className="method-metric-value-num">
        {v.value != null ? formatPct(v.value) : `not available (${v.reason ?? "no data"})`}
      </span>
    </div>
  );
}

// Inventory agreement has no aggregate in either summary file (B.6) — the
// real content on this page for that metric is the sample's per-entity-type
// flag list instead of a single value.
function FlaggedEntityTypes({ flags }: { flags: Record<string, MethodInventoryAgreementFlag> }) {
  const rows = Object.entries(flags).sort((a, b) => b[1].flagged_count - a[1].flagged_count);
  return (
    <p className="chart-note">
      Flagged in the 18-document sample:{" "}
      {rows.map(([key, flag], i) => (
        <span key={key}>
          {i > 0 && ", "}{key.replace(/_count$/, "").replace(/_/g, " ")} ({flag.flagged_count})
        </span>
      ))}.
    </p>
  );
}

function MetricCard({ label, metric }: { label: string; metric: MethodMetric }) {
  return (
    <div className="method-metric">
      <h4 className="method-metric-label">{label}</h4>
      {metric.definition && <p className="method-metric-def">{metric.definition}</p>}
      {metric.target && <p className="chart-note">{metric.target}</p>}
      <div className="method-metric-values">
        <MetricValue label={`Full corpus (n=${metric.full_corpus.n ?? "—"})`} v={metric.full_corpus} />
        <MetricValue label={`Sample (n=${metric.sample.n ?? "—"})`} v={metric.sample} />
      </div>
      {metric.sample.flagged_entity_types && (
        <FlaggedEntityTypes flags={metric.sample.flagged_entity_types} />
      )}
      <p className="method-metric-consequence">{metric.means_if_failed}</p>
    </div>
  );
}

function SchemaFlags({ v }: { v: MethodSourcedValue<number> & { flagged_files?: string[] } }) {
  if (v.value == null) {
    return <p className="chart-note">Schema flags: not available — {v.reason ?? "no data"}.</p>;
  }
  return (
    <p className="chart-note">
      <strong>{v.value}</strong> schema-validation flag{v.value === 1 ? "" : "s"}
      {v.n != null && ` across ${v.n} validated documents`} · as of {formatDate(v.generated_at)} ·{" "}
      <code>{v.source}</code>
      {v.flagged_files && ` (${v.flagged_files.length} file${v.flagged_files.length === 1 ? "" : "s"} flagged)`}.
    </p>
  );
}

function statusChipClass(status: MethodSamplePerFileRow["status"]): string {
  if (status === "PASS") return "valence-chip valence-supportive";
  if (status === "REVIEW") return "valence-chip valence-neutral";
  return "valence-chip valence-critical";
}

function PerFileTable({ v }: { v: MethodSourcedValue<MethodSamplePerFileRow[]> }) {
  if (!v.value) {
    return <p className="chart-note">Per-file results not available — {v.reason ?? "no data"}.</p>;
  }
  return (
    <>
      <p className="chart-note">As of {formatDate(v.generated_at)} · <code>{v.source}</code>{v.n != null && ` · n=${v.n}`}</p>
      <table className="method-table">
        <thead>
          <tr>
            <th>File</th><th>Date</th><th>Paraphrase</th><th>Coverage</th><th>Keyword gap</th><th>Status</th>
          </tr>
        </thead>
        <tbody>
          {v.value.map((row) => (
            <tr key={row.filename}>
              <td><code>{row.filename}</code></td>
              <td className="date-cell">{row.meeting_date}</td>
              <td className="method-num-cell">{row.paraphrase_pct}%</td>
              <td className="method-num-cell">{row.coverage_pct}%</td>
              <td className="method-num-cell">{row.keyword_gap_pct}%</td>
              <td><span className={statusChipClass(row.status)}>{row.status}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
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
          <h3 className="static-h2">Validation</h3>
          <p>
            Every extracted document is scored against five metrics, each compared to
            a target from the sample validation report's own METRICS block. The result
            is one of three statuses, applied by <code>determine_status()</code> in{" "}
            <code>src/validation/core.py</code>: <strong>FAIL</strong> if an entity carries
            zero source quotes, or completeness is under 50%, or paraphrase is 80% or
            higher with coverage under 2%; <strong>REVIEW</strong> if coverage is under
            3%, paraphrase is 50% or higher, keyword gap is 40% or higher, or
            completeness is under 80%; <strong>PASS</strong> otherwise. Agendas are
            exempt from the coverage-based FAIL and REVIEW triggers — their
            recommendation text naturally covers less of the document than full
            minutes do.
          </p>

          <SplitTiles label="Full corpus" split={data.validation.full_corpus_split} />
          <SplitTiles label="Stratified sample" split={data.validation.sample_split} />

          <p className="chart-note">
            These two splits are not averaged together, and are not the same
            measurement: the full corpus covers all {data.validation.full_corpus_split.n ?? "—"}{" "}
            validated documents, agendas included; the sample covers{" "}
            {data.validation.sample_split.n ?? "—"} stratified documents, validated
            separately on a different date (see the source freshness table above). A
            FAIL is dominated by missing quotes — zero quotes, or fewer than half the
            entities carrying one — not by wrong ones: the corpus-wide paraphrase rate
            is {formatPct(data.validation.metrics.paraphrase_rate.full_corpus.value)}.
          </p>

          {METRIC_ORDER.map((key) => (
            <MetricCard key={key} label={METRIC_LABELS[key]} metric={data.validation.metrics[key]} />
          ))}

          <SchemaFlags v={data.validation.schema_flags} />

          <h4 className="method-split-label">Sample per-file results</h4>
          <PerFileTable v={data.validation.sample_per_file} />
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
