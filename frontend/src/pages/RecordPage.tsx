import { useMemo, useState } from "react";
import { api, RecordStreetsApplication, RecordStreetsStreet } from "../api";
import { useData } from "../hooks/useData";
import { LoadingCard, ErrorCard } from "../components/InterestsChart";

// docs/frontend/RECORD_PAGE_PLAN.md — Step 4: type-ahead street lookup.
// Deliberately plain: no severity chip, no principles list, no
// Objection/Response block — this page doesn't argue, it looks things up.
// Every figure shown comes straight from record_streets.json; nothing is
// computed here beyond formatting and the search filter itself.

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

export function RecordPage() {
  const { data, loading, error } = useData(api.recordStreets);

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
        {loading && <LoadingCard />}
        {error && <ErrorCard msg={error} />}
        {data && (
          <>
            <StreetSearch streets={data.streets} />
            <p className="rec-caveat">{data.coverage.note}</p>
          </>
        )}
      </section>
    </div>
  );
}
