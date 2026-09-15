import { useMemo, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid,
} from "recharts";
import {
  api, LookupSearchEntry, ObjectionDoseBucket, ObjectionDoseData, ObjectionResponsivenessEvidence,
  RecordCouncillor, RecordStreetsApplication, RecordStreetsStreet,
  TenureData, TenureEvidence, TransparencyData, TransparencyEvidence, TrendsData,
} from "../api";
import { useData, useLazyData } from "../hooks/useData";
import { LoadingCard, ErrorCard } from "../components/InterestsChart";
import { SourceQuote } from "../components/DrillDown";
import { CouncilHeader } from "../components/CouncilHeader";
import { REGISTRY_BY_ID } from "../registry";
import { watchHref } from "../registry/anchors";

// docs/frontend/RECORD_PAGE_PLAN.md — Steps 4-8: type-ahead street lookup
// (feature 1), the objector calculator (feature 2), councillor cards
// (feature 3, Phase 2), topic drift (feature 4, Phase 3), and notable
// moments (feature 5, Phase 3). Deliberately plain: no severity chip, no
// principles list, no Objection/Response block — this page doesn't argue,
// it looks things up. Every figure shown comes straight from
// record_streets.json / dose.json / record_councillors.json / trends.json /
// tenure.json / transparency.json; nothing is computed here beyond
// formatting, the search filter, and picking the currently-selected
// bucket/year.

function formatDate(iso: string | null): string {
  if (!iso) return "date not recorded";
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-AU", {
    day: "numeric", month: "long", year: "numeric",
  });
}

function formatOutcome(outcome: string | null): string {
  if (!outcome) return "outcome not recorded";
  return outcome.charAt(0).toUpperCase() + outcome.slice(1);
}

function formatObjectors(n: number): string {
  if (n === 0) return "no objections";
  if (n === 1) return "1 objection";
  return `${n} objections`;
}

function SourceLine({ evidence }: { evidence: RecordStreetsApplication["evidence"] }) {
  return (
    <p className="src-doc">
      {evidence.filename ?? "document not recorded"}
      {evidence.meeting_date && <> · {formatDate(evidence.meeting_date)}</>}
      {" · "}
      {evidence.page != null ? `page ${evidence.page}` : "page not recorded"}
      {evidence.url && (
        <>
          {" · "}
          <a href={evidence.url} target="_blank" rel="noreferrer">source document</a>
        </>
      )}
    </p>
  );
}

function ApplicationRow({ app }: { app: RecordStreetsApplication }) {
  return (
    <li className="rec-app">
      <div className="rec-app-head">
        <span className="rec-app-date">{formatDate(app.date)}</span>
        <span className="rec-app-outcome">{formatOutcome(app.outcome)}</span>
        <span className="rec-app-objectors">{formatObjectors(app.n_objectors)}</span>
      </div>
      {app.description && <p className="rec-app-desc">{app.description}</p>}
      {app.reference && <p className="rec-app-ref">Reference {app.reference}</p>}
      <SourceLine evidence={app.evidence} />
    </li>
  );
}

function StreetResults({ street }: { street: RecordStreetsStreet }) {
  return (
    <div className="rec-street">
      <h2 className="rec-street-name">{street.name}</h2>
      <p className="rec-street-meta">
        <strong className="rec-street-count">
          {street.n_applications} {street.n_applications === 1 ? "result" : "results"}
        </strong>{" "}
        across {street.n_sites} {street.n_sites === 1 ? "site" : "sites"}
        {street.suburbs.length > 0 && <> · {street.suburbs.join(", ")}</>}
      </p>
      {street.sites.map((site) => (
        <div className="rec-site" key={site.address}>
          <h3 className="rec-site-address">
            {site.address}
            {site.lot_number && <span className="rec-site-lot"> · Lot {site.lot_number}</span>}
          </h3>
          {site.applications.length === 0 ? (
            <p className="rec-site-none">no applications on record for this site</p>
          ) : (
            <ul className="rec-app-list">
              {site.applications.map((app, i) => (
                // Index, not `reference` -- the same reference_number can
                // legitimately appear twice on one site in the corpus (an
                // amendment sharing its parent's DA number), so it isn't a
                // safe React key on its own. Found via a real console
                // warning while verifying this step.
                <ApplicationRow app={app} key={i} />
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

function StreetSearch({ streets }: { streets: RecordStreetsStreet[] }) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<RecordStreetsStreet | null>(null);

  const suggestions = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || selected) return [];
    return streets.filter((s) => s.name.toLowerCase().includes(q)).slice(0, 8);
  }, [query, selected, streets]);

  function pick(street: RecordStreetsStreet) {
    setSelected(street);
    setQuery(street.name);
  }

  function onChange(value: string) {
    setQuery(value);
    if (selected && value !== selected.name) setSelected(null);
  }

  function clear() {
    setQuery("");
    setSelected(null);
  }

  const showPanel = query.trim().length > 0 || selected !== null;
  // A real street from this council's own data, not a fixed example name
  // (SECOND_COUNCIL_PLAN.md Phase 3.2) — the one with the most applications
  // on record, so it's likely to actually return a result if typed.
  const exampleStreet = [...streets].sort((a, b) => b.n_applications - a.n_applications)[0]?.name;

  return (
    <div className="rec-search">
      <label className="rec-search-label" htmlFor="rec-street-input">
        Type a street name
      </label>
      <div className="rec-search-bar">
        <input
          id="rec-street-input"
          className="rec-search-input"
          type="text"
          value={query}
          onChange={(e) => onChange(e.target.value)}
          placeholder={exampleStreet ? `e.g. ${exampleStreet}` : "Street name"}
          autoComplete="off"
        />
        {showPanel && (
          <button
            type="button"
            className="rec-search-clear"
            onClick={clear}
            aria-label="Clear search"
          >
            ×
          </button>
        )}
      </div>
      {showPanel && (
        <div className="rec-search-panel">
          {suggestions.length > 0 && (
            <ul className="rec-suggestions">
              {suggestions.map((s) => (
                <li key={s.name}>
                  <button type="button" onClick={() => pick(s)}>
                    {s.name}
                    <span className="rec-suggestion-count">
                      {" "}
                      — {s.n_sites} {s.n_sites === 1 ? "site" : "sites"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {query.trim() && !selected && suggestions.length === 0 && (
            <p className="rec-no-match">No street matches "{query.trim()}".</p>
          )}
          {selected && <StreetResults street={selected} />}
        </div>
      )}
    </div>
  );
}

const LOOKUP_RESULT_CAP = 50;

function lookupKindLabel(kind: LookupSearchEntry["kind"]): string {
  if (kind === "motion") return "Motion";
  if (kind === "tender") return "Tender award";
  return "Agenda item";
}

function lookupSearchableText(entry: LookupSearchEntry): string {
  const parts =
    entry.kind === "motion" ? [entry.title, entry.description]
    : entry.kind === "tender" ? [entry.awarded_to, entry.description]
    : [entry.item_type, entry.description];
  return parts.filter(Boolean).join(" ").toLowerCase();
}

function LookupResultRow({ entry }: { entry: LookupSearchEntry }) {
  const date = formatDate(entry.meeting_date);
  const isConfidential = entry.kind !== "motion" && entry.is_confidential;

  let headline: string;
  let desc: string | null;
  if (entry.kind === "motion") {
    headline = entry.title + (entry.outcome && entry.outcome !== "carried" ? ` (${entry.outcome})` : "");
    desc = entry.description;
  } else if (entry.kind === "tender") {
    const amount = entry.amount != null ? ` — $${entry.amount.toLocaleString()}` : "";
    headline = (entry.awarded_to ?? "recipient not recorded") + amount;
    desc = entry.description;
  } else {
    headline = entry.item_type;
    desc = entry.description;
  }

  return (
    <li className="lookup-result">
      <div className="lookup-result-head">
        <span className="lookup-result-kind">{lookupKindLabel(entry.kind)}</span>
        <span className="lookup-result-date">{date}</span>
        {isConfidential && <span className="lookup-result-confidential">confidential</span>}
      </div>
      <a className="lookup-result-title" href={watchHref(entry.meeting_id)}>{headline}</a>
      {desc && <p className="lookup-result-desc">{desc}</p>}
    </li>
  );
}

function LookupSearch() {
  const { data, loading, error, trigger } = useLazyData(api.lookupSearch);
  const [query, setQuery] = useState("");

  const allEntries = useMemo<LookupSearchEntry[]>(() => {
    if (!data) return [];
    return [...data.motions, ...data.other_items, ...data.tenders];
  }, [data]);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return allEntries.filter((e) => lookupSearchableText(e).includes(q));
  }, [query, allEntries]);

  function clear() {
    setQuery("");
  }

  const showPanel = query.trim().length > 0;

  return (
    <div className="rec-search">
      <label className="rec-search-label" htmlFor="lookup-search-input">
        Search motions, agenda items, and tender awards
      </label>
      <div className="rec-search-bar">
        <input
          id="lookup-search-input"
          className="rec-search-input"
          type="text"
          value={query}
          onFocus={trigger}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. St John of God Hospital, Fleetcare"
          autoComplete="off"
        />
        {showPanel && (
          <button
            type="button"
            className="rec-search-clear"
            onClick={clear}
            aria-label="Clear search"
          >
            ×
          </button>
        )}
      </div>
      {showPanel && (
        <div className="rec-search-panel">
          {loading && <p className="rec-no-match">Loading search index…</p>}
          {error && <p className="rec-no-match">Failed to load search index: {error}</p>}
          {data && matches.length === 0 && (
            <p className="rec-no-match">No matches for "{query.trim()}".</p>
          )}
          {data && matches.length > 0 && (
            <>
              <p className="lookup-search-count">
                {matches.length} {matches.length === 1 ? "result" : "results"}
                {matches.length > LOOKUP_RESULT_CAP && ` — showing the first ${LOOKUP_RESULT_CAP}`}
              </p>
              <ul className="lookup-results">
                {matches.slice(0, LOOKUP_RESULT_CAP).map((e, i) => (
                  <LookupResultRow entry={e} key={i} />
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}

const OBJECTOR_BUCKET_LABELS: Record<string, string> = {
  "0": "no objections",
  "1": "1 objection",
  "2-4": "2 to 4 objections",
  "5+": "5 or more objections",
};

function bucketLabel(bucket: ObjectionDoseBucket): string {
  return OBJECTOR_BUCKET_LABELS[bucket.label] ?? bucket.label;
}

function ObjectorCalculator({ dose }: { dose: ObjectionDoseData }) {
  const [index, setIndex] = useState(0);
  const bucket = dose.buckets[index] ?? dose.buckets[0];

  // Computed from the data, never hardcoded (frontend/INTERACTIVITY.md's
  // hard rule) — the "5+" bucket's sample size and the single most-opposed
  // application are both derived from dose.buckets, not typed as a literal.
  const bucket5plus = dose.buckets.find((b) => b.label === "5+") ?? null;
  const mostOpposed = useMemo(() => {
    if (!bucket5plus || bucket5plus.apps.length === 0) return null;
    return [...bucket5plus.apps].sort((a, b) => b.n_objectors - a.n_objectors)[0];
  }, [bucket5plus]);

  const registryRow = REGISTRY_BY_ID["planning.objection_responsiveness"];

  return (
    <section className="rec-dose">
      <h2 className="static-h2">{registryRow?.title_public ?? "Whether objecting changes the outcome"}</h2>
      <p className="rec-dose-intro">
        Every decided planning application on record, grouped by how many
        residents formally objected to it. Move the slider to see how the
        refusal rate changes as objections rise.
      </p>

      <input
        className="rec-dose-slider"
        type="range"
        min={0}
        max={dose.buckets.length - 1}
        step={1}
        value={index}
        onChange={(e) => setIndex(Number(e.target.value))}
        aria-label="Number of objections"
      />
      <div className="rec-dose-ticks">
        {dose.buckets.map((b, i) => (
          <button
            type="button"
            key={b.label}
            className={i === index ? "rec-dose-tick rec-dose-tick-active" : "rec-dose-tick"}
            onClick={() => setIndex(i)}
          >
            {bucketLabel(b)}
          </button>
        ))}
      </div>

      <p className="rec-dose-rate">
        <span className="rec-dose-rate-num">{bucket.refusal_pct}%</span> of applications with{" "}
        {bucketLabel(bucket)} were refused
      </p>

      <p className="rec-caveat">
        {bucket5plus && (
          <>
            The busiest end of this — {OBJECTOR_BUCKET_LABELS["5+"]} — rests on only{" "}
            {bucket5plus.n} applications, so read that figure as directional, not a
            precise measurement.{" "}
          </>
        )}
        {mostOpposed && mostOpposed.outcome && (
          <>
            The most-opposed application on record drew {mostOpposed.n_objectors} objections,
            and it was {mostOpposed.outcome}.
          </>
        )}
      </p>
    </section>
  );
}

function formatYears(n: number): string {
  return `${n} ${n === 1 ? "year" : "years"}`;
}

function CouncillorCard({ c }: { c: RecordCouncillor }) {
  return (
    <dl className="rec-cllr-fields">
      <div className="rec-cllr-field">
        <dt>Years served</dt>
        <dd>{formatYears(c.years_served)}</dd>
      </div>
      <div className="rec-cllr-field">
        <dt>Motions moved</dt>
        <dd>{c.motions_moved}</dd>
      </div>
      <div className="rec-cllr-field">
        <dt>Votes cast</dt>
        <dd>{c.votes_cast}</dd>
      </div>
      <div className="rec-cllr-field">
        <dt>Most frequent seconder</dt>
        <dd>
          {c.most_frequent_seconder
            ? `${c.most_frequent_seconder.name} (${c.most_frequent_seconder.count} times)`
            : "not recorded"}
        </dd>
      </div>
      <div className="rec-cllr-field">
        <dt>Contested votes</dt>
        <dd>
          {c.contested_votes.total} total — {c.contested_votes.won} on the winning
          side, {c.contested_votes.lost} on the losing side
        </dd>
      </div>
    </dl>
  );
}

function CouncillorCards({ councillors }: { councillors: RecordCouncillor[] }) {
  // Computed from the data, never hardcoded — the earliest first_vote
  // across every councillor on record, not a typed year.
  const earliestYear = useMemo(() => {
    const years = councillors
      .map((c) => c.first_vote)
      .filter((d): d is string => !!d)
      .map((d) => Number(d.slice(0, 4)));
    return years.length ? Math.min(...years) : null;
  }, [councillors]);

  const [selectedName, setSelectedName] = useState(councillors[0]?.name ?? "");
  const selected = councillors.find((c) => c.name === selectedName) ?? null;

  return (
    <section className="rec-cllrs">
      <h2 className="static-h2">Councillors on record</h2>
      <p className="rec-dose-intro">
        {councillors.length} councillors{earliestYear && <> have served since {earliestYear}</>}.
        Select a name to see their record — years served, motions moved, votes
        cast, who most often seconded their motions, and how their contested
        votes split.
      </p>
      <select
        className="rec-cllr-select"
        value={selectedName}
        onChange={(e) => setSelectedName(e.target.value)}
        aria-label="Select a councillor"
      >
        {councillors.map((c) => (
          <option key={c.name} value={c.name}>{c.name}</option>
        ))}
      </select>
      {selected && <CouncillorCard c={selected} />}
    </section>
  );
}

// Fixed order, validated categorical palette (see index.css --topic-1..8 —
// dataviz skill's 8-hue default). "other" is deliberately NOT one of these
// eight — it's the residual catch-all bucket topic_distribution_by_year()
// bins anything outside the top 8 tags into, not a designed category, and
// gets its own muted, always-visible colour (--topic-other) instead of
// competing for a slot. Colours are assigned by alphabetical POSITION, not
// a name->colour dictionary, because the underlying tag vocabulary is
// LLM-assigned free text that can shift on a re-extraction — a hardcoded
// name map would silently stop covering a renamed or replaced category.
const TOPIC_COLOR_VARS = [
  "var(--topic-1)", "var(--topic-2)", "var(--topic-3)", "var(--topic-4)",
  "var(--topic-5)", "var(--topic-6)", "var(--topic-7)", "var(--topic-8)",
];

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function TopicDriftChart({ trends }: { trends: TrendsData }) {
  const [showTable, setShowTable] = useState(false);

  const years = useMemo(
    () => Object.keys(trends.topics).map(Number).sort((a, b) => a - b),
    [trends]
  );

  // Every category that appears in any year, "other" pulled out (it's
  // rendered separately below, always last, never folded away — RECORD_PAGE_
  // PLAN.md Step 7: "do not collapse or rename the 'other' bucket").
  const categories = useMemo(() => {
    const set = new Set<string>();
    for (const y of years) {
      for (const cat of Object.keys(trends.topics[String(y)] ?? {})) {
        if (cat !== "other") set.add(cat);
      }
    }
    return [...set].sort();
  }, [trends, years]);

  const colorByCategory = useMemo(() => {
    const map: Record<string, string> = { other: "var(--topic-other)" };
    categories.forEach((cat, i) => {
      map[cat] = TOPIC_COLOR_VARS[i % TOPIC_COLOR_VARS.length];
    });
    return map;
  }, [categories]);

  const allCategories = [...categories, "other"];

  const chartData = useMemo(
    () =>
      years.map((year) => {
        const row: Record<string, number | string> = { year };
        const yearTopics = trends.topics[String(year)] ?? {};
        for (const cat of allCategories) row[cat] = yearTopics[cat] ?? 0;
        return row;
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [trends, years, categories]
  );

  // Computed from the data, never hardcoded — how many years "other" is
  // the single largest bucket, the fact Step 7 requires be on screen, not
  // buried behind a tidier-looking chart.
  const otherLargestYears = useMemo(
    () =>
      chartData.filter((row) =>
        categories.every((cat) => Number(row.other) >= Number(row[cat] ?? 0))
      ).length,
    [chartData, categories]
  );

  return (
    <section className="rec-topics">
      <h2 className="static-h2">What the council spent its time on</h2>
      <p className="rec-dose-intro">
        Every carried motion since {years[0]}, grouped by topic and counted
        by year. "Other" is the largest single category in {otherLargestYears}{" "}
        of {years.length} years on record — it is shown here rather than
        folded into a tidier-looking handful of categories.
      </p>

      <ResponsiveContainer width="100%" height={380}>
        <BarChart data={chartData} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} interval={2} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11 }} width={36} />
          <Tooltip
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6 }}
            labelStyle={{ color: "var(--text-hi)" }}
          />
          <Legend formatter={(value) => capitalize(String(value))} />
          {allCategories.map((cat) => (
            <Bar key={cat} dataKey={cat} stackId="a" fill={colorByCategory[cat]} name={cat} />
          ))}
        </BarChart>
      </ResponsiveContainer>

      <button type="button" className="src-toggle" onClick={() => setShowTable((s) => !s)}>
        {showTable ? "▾" : "▸"} view the exact figures as a table
      </button>
      {showTable && (
        <div className="rec-topics-table-wrap">
          <table className="rec-topics-table">
            <thead>
              <tr>
                <th>Year</th>
                {allCategories.map((cat) => (
                  <th key={cat}>{capitalize(cat)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {chartData.map((row) => (
                <tr key={String(row.year)}>
                  <td>{row.year}</td>
                  {allCategories.map((cat) => (
                    <td key={cat}>{row[cat]}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function MomentCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rec-moment">
      <h3 className="rec-moment-title">{title}</h3>
      {children}
    </div>
  );
}

function LongestTenureMoment({
  tenure, evidence,
}: { tenure: TenureData; evidence: TenureEvidence | null }) {
  // Computed from the data, never hardcoded (frontend/INTERACTIVITY.md's
  // hard rule) — the councillor with the highest `years`, not a typed name.
  const byTenureDesc = useMemo(
    () => [...tenure.profiles].sort((a, b) => b.years - a.years),
    [tenure]
  );
  const longest = byTenureDesc[0] ?? null;
  if (!longest) return null;
  const runnersUp = byTenureDesc.slice(1, 3).map((p) => p.years);

  const entriesById = new Map((evidence?.entries ?? []).map((e) => [e.entity_id, e]));
  const firstEntry = longest.first_motion_id != null ? entriesById.get(longest.first_motion_id) ?? null : null;
  const lastEntry = longest.last_motion_id != null ? entriesById.get(longest.last_motion_id) ?? null : null;

  return (
    <MomentCard title="The longest tenure on record">
      <p>
        {longest.name} has served {longest.years} years — longer than anyone
        else on record
        {runnersUp.length > 0 && (
          <>, well ahead of the next-longest tenures ({runnersUp.join(" and ")} years)</>
        )}
        .
      </p>
      <p className="rec-moment-label">First recorded vote</p>
      <SourceQuote entry={firstEntry} />
      <p className="rec-moment-label">Most recent recorded vote</p>
      <SourceQuote entry={lastEntry} />
    </MomentCard>
  );
}

function ConfidentialitySpikeMoment({
  transparency, evidence,
}: { transparency: TransparencyData; evidence: TransparencyEvidence | null }) {
  const prevYear = transparency.years.find((y) => y.year === transparency.peak_year - 1);
  const nextYear = transparency.years.find((y) => y.year === transparency.peak_year + 1);
  const peakItems = evidence?.years.find((y) => y.year === transparency.peak_year)?.items ?? [];
  const example = peakItems[0] ?? null;

  return (
    <MomentCard title={`The ${transparency.peak_year} confidentiality spike`}>
      <p>
        {transparency.peak_pct}% of decided items were confidential in{" "}
        {transparency.peak_year}
        {prevYear && <> — up from {prevYear.confidential_pct}% in {prevYear.year}</>}
        {nextYear && <> and back down to {nextYear.confidential_pct}% the following year</>}.
      </p>
      {example ? (
        <>
          <p className="rec-moment-label">An example from {transparency.peak_year}</p>
          <SourceQuote entry={example} />
        </>
      ) : (
        <p className="rec-moment-label">no source quote recorded for this year</p>
      )}
    </MomentCard>
  );
}

function MostOpposedMoment({
  dose, evidence,
}: { dose: ObjectionDoseData; evidence: ObjectionResponsivenessEvidence | null }) {
  const bucket5plus = dose.buckets.find((b) => b.label === "5+") ?? null;
  const mostOpposed = useMemo(() => {
    if (!bucket5plus || bucket5plus.apps.length === 0) return null;
    return [...bucket5plus.apps].sort((a, b) => b.n_objectors - a.n_objectors)[0];
  }, [bucket5plus]);
  if (!mostOpposed) return null;

  const evBucket = evidence?.buckets.find((b) => b.label === "5+");
  const entry = evBucket?.applications.find((a) => a.entity_id === mostOpposed.entity_id) ?? null;

  return (
    <MomentCard title="The most-contested planning application on record">
      <p>
        {mostOpposed.description ?? "An application"} drew {mostOpposed.n_objectors}{" "}
        objections{mostOpposed.outcome && <> and was {mostOpposed.outcome}</>}.
      </p>
      <SourceQuote entry={entry} />
    </MomentCard>
  );
}

function NotableMoments({
  tenure, tenureEvidence, transparency, transparencyEvidence, dose, doseEvidence,
}: {
  tenure: TenureData; tenureEvidence: TenureEvidence | null;
  transparency: TransparencyData; transparencyEvidence: TransparencyEvidence | null;
  dose: ObjectionDoseData; doseEvidence: ObjectionResponsivenessEvidence | null;
}) {
  return (
    <section className="rec-moments">
      <h2 className="static-h2">Notable moments</h2>
      <p className="rec-dose-intro">
        A few specific facts from the record, each traceable back to a
        verbatim minute.
      </p>
      <LongestTenureMoment tenure={tenure} evidence={tenureEvidence} />
      <ConfidentialitySpikeMoment transparency={transparency} evidence={transparencyEvidence} />
      <MostOpposedMoment dose={dose} evidence={doseEvidence} />
    </section>
  );
}

export function RecordPage() {
  const streetsData = useData(api.recordStreets);
  const doseData = useData(api.dose);
  const doseEvidenceData = useData(api.evidenceObjectionResponsiveness);
  const councillorsData = useData(api.recordCouncillors);
  const tenureData = useData(api.tenure);
  const tenureEvidenceData = useData(api.evidenceTenure);
  const transparencyData = useData(api.transparency);
  const transparencyEvidenceData = useData(api.evidenceTransparency);
  const trendsData = useData(api.trends);

  return (
    <div className="static-page">
      <CouncilHeader />
      <div className="static-hero">
        <h1 className="static-h1">The record</h1>
        <p className="static-lead">
          A place to look up what's on the public record — by street, motion, contractor, or councillor.
        </p>
      </div>

      <section className="static-section">
        {streetsData.loading && <LoadingCard />}
        {streetsData.error && <ErrorCard msg={streetsData.error} />}
        {streetsData.data && (
          <>
            <StreetSearch streets={streetsData.data.streets} />
            <p className="rec-caveat">{streetsData.data.coverage.note}</p>
          </>
        )}
      </section>

      <section className="static-section">
        <LookupSearch />
      </section>

      <section className="static-section">
        {doseData.loading && <LoadingCard />}
        {doseData.error && <ErrorCard msg={doseData.error} />}
        {doseData.data && <ObjectorCalculator dose={doseData.data} />}
      </section>

      <section className="static-section">
        {councillorsData.loading && <LoadingCard />}
        {councillorsData.error && <ErrorCard msg={councillorsData.error} />}
        {councillorsData.data && <CouncillorCards councillors={councillorsData.data.councillors} />}
      </section>

      <section className="static-section">
        {trendsData.loading && <LoadingCard />}
        {trendsData.error && <ErrorCard msg={trendsData.error} />}
        {trendsData.data && <TopicDriftChart trends={trendsData.data} />}
      </section>

      <section className="static-section">
        {(tenureData.loading || transparencyData.loading || doseData.loading) && <LoadingCard />}
        {tenureData.error && <ErrorCard msg={tenureData.error} />}
        {transparencyData.error && <ErrorCard msg={transparencyData.error} />}
        {tenureData.data && transparencyData.data && doseData.data && (
          <NotableMoments
            tenure={tenureData.data}
            tenureEvidence={tenureEvidenceData.data}
            transparency={transparencyData.data}
            transparencyEvidence={transparencyEvidenceData.data}
            dose={doseData.data}
            doseEvidence={doseEvidenceData.data}
          />
        )}
      </section>
    </div>
  );
}
