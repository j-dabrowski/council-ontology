import { useMemo, useState } from "react";
import { api, ObjectionDoseBucket, ObjectionDoseData, RecordStreetsApplication, RecordStreetsStreet } from "../api";
import { useData } from "../hooks/useData";
import { LoadingCard, ErrorCard } from "../components/InterestsChart";
import { REGISTRY_BY_ID } from "../registry";

// docs/frontend/RECORD_PAGE_PLAN.md — Steps 4-5: type-ahead street lookup
// (feature 1) and the objector calculator (feature 2). Deliberately plain:
// no severity chip, no principles list, no Objection/Response block — this
// page doesn't argue, it looks things up. Every figure shown comes straight
// from record_streets.json / dose.json; nothing is computed here beyond
// formatting, the search filter, and picking the currently-selected bucket.

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
        {street.n_sites} {street.n_sites === 1 ? "site" : "sites"} ·{" "}
        {street.n_applications} {street.n_applications === 1 ? "application" : "applications"}
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

  return (
    <div className="rec-search">
      <label className="rec-search-label" htmlFor="rec-street-input">
        Type a street name
      </label>
      <input
        id="rec-street-input"
        className="rec-search-input"
        type="text"
        value={query}
        onChange={(e) => onChange(e.target.value)}
        placeholder="e.g. Cambridge Street"
        autoComplete="off"
      />
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

export function RecordPage() {
  const streetsData = useData(api.recordStreets);
  const doseData = useData(api.dose);

  return (
    <div className="static-page">
      <div className="static-hero">
        <h1 className="static-h1">The record</h1>
        <p className="static-lead">
          A place to look up what's on the public record for your street — not
          an argument, just the facts as recorded in council minutes, with a
          link back to the source document for every application shown.
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
        {doseData.loading && <LoadingCard />}
        {doseData.error && <ErrorCard msg={doseData.error} />}
        {doseData.data && <ObjectorCalculator dose={doseData.data} />}
      </section>
    </div>
  );
}
