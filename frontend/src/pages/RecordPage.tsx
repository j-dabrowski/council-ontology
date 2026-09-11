// docs/frontend/RECORD_PAGE_PLAN.md — Step 1: page shell only. No
// registry-derived content, no chart, no figure yet (that starts at Step 3).
// Deliberately plain: no severity chip, no principles list, no
// Objection/Response block — this page doesn't argue, it looks things up.
export function RecordPage() {
  return (
    <div className="static-page">
      <div className="static-hero">
        <h1 className="static-h1">The record</h1>
        <p className="static-lead">
          A place to look up what's on the public record for your street, your
          councillor, or a planning application — not an argument, just the
          facts as recorded in council minutes, with a link back to the source
          document for every figure shown.
        </p>
      </div>

      <section className="static-section">
        <h2 className="static-h2">What this page is for</h2>
        <p>
          Most of this site makes a case, one governance test at a time. This
          page doesn't. It's a browsable index — type in a street and see what
          applications have been lodged there, or look up how a particular
          question tends to play out — with nothing more than the plain facts
          and a source you can check for yourself.
        </p>
      </section>
    </div>
  );
}
