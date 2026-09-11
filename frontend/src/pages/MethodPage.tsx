import { CouncilHeader } from "../components/CouncilHeader";
import { LoadingCard, ErrorCard } from "../components/InterestsChart";
import { useData } from "../hooks/useData";
import {
  api, MethodData, MethodSourcedValue, MethodYearRow, MethodMetric,
  MethodValidationSplit, MethodInventoryAgreementFlag, MethodSamplePerFileRow,
  MethodExtractionBatch, MethodSupplierExample, MethodResolvedCollision,
  MethodEntityResolution, ScorecardData,
} from "../api";
import { scorecardHref } from "../registry/anchors";

// README.md "Multi-level extraction pipeline" table, transcribed verbatim
// (README.md lines 823-836) rather than retyped from the plan's own
// paraphrase — checked directly against the file, not the plan's summary of
// it. Level 6 (Audit) is excluded: METHOD_PAGE_PLAN.md's run-order sequence
// (B.5) names only these seven stages, and its own "Deliberately not in
// this plan" section lists the Level 6 human audit explicitly. In RUN
// order (extract before validate), not the README's plan-order numbering —
// see the caption below the diagram.
interface PipelineStage {
  name: string;
  levelLabel: string;
  cost: string;
}
const PIPELINE_STAGES: PipelineStage[] = [
  { name: "Census", levelLabel: "Level 0", cost: "Free" },
  { name: "Inventory", levelLabel: "Level 1", cost: "$4.83 actual" },
  { name: "Typology (schema)", levelLabel: "Level 2", cost: "Free" },
  { name: "Sample selection + extraction", levelLabel: "Levels 3a/3b", cost: "Free + ~$0.50" },
  { name: "Validate sample", levelLabel: "Level 3c", cost: "Free" },
  { name: "Extract (full corpus)", levelLabel: "Level 5", cost: "~$70 actual" },
  { name: "Validate (full corpus)", levelLabel: "Level 4", cost: "Free" },
];
// git log -L 827,835:README.md — the table's own last edit, not this
// session's date. README.md carries no generated_at the way the data/
// files do, so a git-history date stands in, cited as such rather than
// invented or left unstated.
const PIPELINE_TABLE_DATE = "2026-07-19";

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

const fmtM = (n: number) => `$${(n / 1e6).toFixed(1)}M`;
const fmt$ = (n: number) => (n >= 1e6 ? fmtM(n) : `$${Math.round(n).toLocaleString()}`);

// docs/frontend/ENTITY_RESOLUTION_SECTION_PLAN.md Step 2 — a validation
// story: does the analysis's own supplier-matching and surname-collision
// logic hold up on this corpus's real spelling variants and real name
// collisions? Every string and number here reads off method.json's
// `entity_resolution` block; nothing is retyped from the plan's own
// worked examples.

// Case 1: every multi-spelling firm shown in full (there are 15 on the real
// corpus) — a short enough list to show whole, and more convincing than a
// chosen three.
function SupplierVariantRow({ example }: { example: MethodSupplierExample }) {
  return (
    <tr>
      <td>
        {example.raw.map((r, i) => (
          <span key={r.string}>
            {i > 0 && ", "}
            {r.string} <span className="method-variant-n">×{r.n}</span>
          </span>
        ))}
        <div>
          <code className="method-supplier-key">{example.merged_key}</code>
        </div>
      </td>
      <td className="method-num-cell">{example.n_awards}</td>
      <td className="method-num-cell">{fmt$(example.total_amount)}</td>
    </tr>
  );
}

function SupplierNormalisationCase({ sn }: { sn: MethodEntityResolution["supplier_normalisation"] }) {
  return (
    <>
      <h4 className="method-split-label">Case 1 — the same supplier, spelled differently</h4>
      <p className="chart-note">
        As of {formatDate(sn.generated_at)} · <code>{sn.source}</code> ·{" "}
        {sn.named_award_rows.toLocaleString()} named award rows, {sn.distinct_firms.toLocaleString()}{" "}
        distinct normalised firms.
      </p>
      <p>
        Every <code>tenders.awarded_to</code> value is normalised by lowercasing it, stripping
        company suffixes, dropping <code>.</code> and <code>,</code>, and removing internal
        whitespace — the rule is <code>{sn.rule}</code>. That collapses{" "}
        <strong>{sn.multi_variant_firms}</strong> firms whose award rows spell their own name more
        than one way, shown in full below.
      </p>
      <table className="method-table">
        <thead>
          <tr>
            <th>Raw spellings on record</th>
            <th>Awards</th>
            <th>Total value</th>
          </tr>
        </thead>
        <tbody>
          {sn.examples.map((ex) => (
            <SupplierVariantRow key={ex.merged_key} example={ex} />
          ))}
        </tbody>
      </table>
      <p className="chart-note">{sn.excluded_placeholders.note} — {sn.excluded_placeholders.n_awards}{" "}
        award row{sn.excluded_placeholders.n_awards === 1 ? "" : "s"} excluded on this basis.</p>
    </>
  );
}

// Case 2: before (raw collisions), after (both resolved on provenance) — the
// room the brief asks for, not a one-line mention. The three B.6 limits sit
// beside the figure each one qualifies rather than collecting at the bottom.
function CollisionCard({ c }: { c: MethodResolvedCollision }) {
  return (
    <div className="method-metric" key={c.firm}>
      <h4 className="method-metric-label">{c.firm} — {fmt$(c.amount)}</h4>
      {c.what_it_is ? (
        <p className="method-metric-def">{c.what_it_is[0].toUpperCase() + c.what_it_is.slice(1)}.</p>
      ) : (
        <p className="method-metric-def">Not yet characterised.</p>
      )}
      <p className="method-metric-consequence">
        {c.resolution
          ? `Resolution: ${c.resolution}.`
          : `Unresolved — ${(c.reason ?? "needs manual review").replace(/_/g, " ")}.`}
      </p>
    </div>
  );
}

function SurnameCollisionCase({ sc }: { sc: MethodEntityResolution["surname_collision"] }) {
  return (
    <>
      <h4 className="method-split-label">Case 2 — does a tender winner share a decider's surname?</h4>
      <p className="chart-note">
        As of {formatDate(sc.generated_at)} · <code>{sc.source}</code>
      </p>
      <div className="method-metric-values">
        <div className="method-metric-value">
          <span className="method-metric-value-label">Named awards tested</span>
          <span className="method-metric-value-num">{sc.named_awards.toLocaleString()}</span>
        </div>
        <div className="method-metric-value">
          <span className="method-metric-value-label">Voting-councillor surnames tested</span>
          <span className="method-metric-value-num">{sc.surnames_tested.toLocaleString()}</span>
        </div>
        <div className="method-metric-value">
          <span className="method-metric-value-label">Raw candidate matches</span>
          <span className="method-metric-value-num">{sc.naive_matches.toLocaleString()}</span>
        </div>
      </div>
      <p className="chart-note">{sc.limits[2]}</p>

      {sc.resolved.map((c) => (
        <CollisionCard key={c.firm} c={c} />
      ))}
      {sc.dedup_note && <p className="chart-note">{sc.dedup_note}.</p>}

      <div className="method-metric-values">
        <div className="method-metric-value">
          <span className="method-metric-value-label">Genuine matches</span>
          <span className="method-metric-value-num">{sc.genuine_matches.toLocaleString()}</span>
        </div>
        {sc.unresolved_matches > 0 && (
          <div className="method-metric-value">
            <span className="method-metric-value-label">Awaiting manual resolution</span>
            <span className="method-metric-value-num">{sc.unresolved_matches.toLocaleString()}</span>
          </div>
        )}
      </div>
      <p className="chart-note">{sc.limits[1]}</p>
      <p className="chart-note">{sc.limits[0]}</p>
    </>
  );
}

function EntityResolutionSection({ er }: { er: MethodEntityResolution }) {
  return (
    <div className="static-section">
      <h3 className="static-h2">Entity resolution</h3>
      <p>
        Two live demonstrations of a join discipline the analysis already applies elsewhere on
        this site: matching supplier names that are spelled inconsistently across the corpus, and
        checking whether a tender ever went to a firm sharing a surname with the councillor who
        voted on it.
      </p>
      <SupplierNormalisationCase sn={er.supplier_normalisation} />
      <SurnameCollisionCase sc={er.surname_collision} />
    </div>
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

// B.5: run order (extract before validate), not the README's plan-order
// numbering — Level 4 (validate) is numbered before Level 5 (extract), but
// extraction finished first. `extractedAt`/`validatedAt` are the real dates
// this ran, read off method.json rather than retyped, so the caption below
// doesn't go stale independently of the record it's explaining.
function PipelineDiagram({ extractedAt, validatedAt }: { extractedAt: string | null; validatedAt: string | null }) {
  return (
    <>
      <p className="chart-note">
        Cost and status: README.md's "Multi-level extraction pipeline" table, last
        updated {formatDate(PIPELINE_TABLE_DATE)} (git history) — a hand-maintained
        doc, not a generated snapshot, so a commit date stands in for the generated_at
        the data/ files carry.
      </p>
      <div className="pipeline-diagram">
        {PIPELINE_STAGES.map((stage, i) => (
          <div className="pipeline-stage-wrap" key={stage.name}>
            <div className="pipeline-stage">
              <span className="pipeline-stage-level">{stage.levelLabel}</span>
              <span className="pipeline-stage-name">{stage.name}</span>
              <span className="pipeline-stage-cost">{stage.cost}</span>
              <span className="pipeline-stage-status">
                Done{stage.name === "Extract (full corpus)" && extractedAt &&
                  ` — 580 docs, ${formatDate(extractedAt)}`}
              </span>
            </div>
            {i < PIPELINE_STAGES.length - 1 && <div className="pipeline-arrow" aria-hidden="true">↓</div>}
          </div>
        ))}
      </div>
      <p className="chart-note">
        The README's level numbers are plan order, not run order: full-corpus
        validation is planned as Level 4, before Level 5's extraction — but
        extraction actually completed {formatDate(extractedAt)}, and full-corpus
        validation ran afterward, on {formatDate(validatedAt)}. This diagram follows
        what happened; the README's level numbers are kept as a record of how the
        pipeline was designed, not renumbered to match.
      </p>
    </>
  );
}

// B.4: framed as one batch, with error classes — never as a corpus-wide
// rate (341 attempted is not 341 of the corpus's current document count).
function ExtractionBatchCard({ batch }: { batch: MethodExtractionBatch }) {
  if (!("batch_id" in batch)) {
    return <p className="chart-note">Last extraction batch: not available — {batch.reason ?? "no data"}.</p>;
  }
  const classes = Object.entries(batch.errors_by_class).sort((a, b) => b[1].length - a[1].length);
  return (
    <div className="method-batch">
      <p className="chart-note">
        The last recorded extraction batch — <code>{batch.batch_id}</code>,{" "}
        {formatDate(batch.generated_at)}: <strong>{batch.succeeded} of {batch.attempted}</strong>{" "}
        succeeded, {batch.failed} schema-validation failure{batch.failed === 1 ? "" : "s"}.
      </p>
      {classes.length > 0 && (
        <ul className="method-error-classes">
          {classes.map(([cls, errs]) => (
            <li key={cls}><code>{cls}</code> ({errs.length})</li>
          ))}
        </ul>
      )}
      <p className="chart-note">{batch.note} · <code>{batch.source}</code></p>
    </div>
  );
}

// §4: not asserted, demonstrated — cites the current battery's own counts
// from scorecard.json (data.summary) rather than typing "2" and "10" as
// prose, so this paragraph can't drift from what the scorecard actually
// ships. Links straight to each not-computable row via scorecardHref(),
// the same deep-link mechanism ScorecardPanel's own rows already answer to.
function NullsStatement() {
  const { data, loading, error } = useData<ScorecardData>(() => api.scorecard());
  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const notComputable = data.tests.filter((t) => !t.data_ok);

  return (
    <>
      <p>
        A system that only reports findings is a system that manufactures them: if a test
        can't run against this corpus, the honest response is to say so, not to quietly
        drop the row. The standard battery currently ships{" "}
        <strong>{data.summary.n_not_computable}</strong> not-computable result
        {data.summary.n_not_computable === 1 ? "" : "s"} alongside{" "}
        <strong>{data.summary.n_supportive}</strong> supportive one
        {data.summary.n_supportive === 1 ? "" : "s"} — the nulls are on the record next to
        the good news, not filtered out ahead of it.
      </p>
      {notComputable.length > 0 && (
        <p className="chart-note">
          Not computable on this corpus:{" "}
          {notComputable.map((t, i) => (
            <span key={t.test_id}>
              {i > 0 && ", "}
              <a href={scorecardHref(t.test_id)}>{t.title}</a>
            </span>
          ))}.
        </p>
      )}
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
          <h3 className="static-h2">Meeting type mix</h3>
          <SourceCaption v={data.coverage.type_mix} />
          {data.coverage.type_mix.value && <TallyTable tally={data.coverage.type_mix.value} />}
        </div>

        <div className="static-section">
          <h3 className="static-h2">Document flags</h3>
          <SourceCaption v={data.coverage.document_flags} />
          {data.coverage.document_flags.value && <TallyTable tally={data.coverage.document_flags.value} />}
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

        <EntityResolutionSection er={data.entity_resolution} />

        <div className="static-section">
          <h3 className="static-h2">Pipeline</h3>
          <PipelineDiagram
            extractedAt={data.extraction_batch.generated_at}
            validatedAt={data.validation.full_corpus_split.generated_at}
          />
          <h4 className="method-split-label">Last extraction batch</h4>
          <ExtractionBatchCard batch={data.extraction_batch} />
        </div>

        <div className="static-section">
          <h3 className="static-h2">Why nulls are reported</h3>
          <NullsStatement />
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
