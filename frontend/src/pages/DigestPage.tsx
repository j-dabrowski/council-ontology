import { Fragment } from "react";
import { CouncilHeader } from "../components/CouncilHeader";
import { BatteryTestCard } from "../components/BatteryTestPanel";
import { LoadingCard, ErrorCard } from "../components/InterestsChart";
import { useData } from "../hooks/useData";
import { api, DigestData, CouncillorsData } from "../api";
import { resolveTests } from "../registry";
import { groupByCategory } from "../registry/grouping";

// Local-review-only surface for the single-meeting digest, computed
// automatically for the latest minutes meeting by every `council draft` run
// (src/cli.py's cmd_draft, writing data/draft/<council>/<run_id>/local/digest.json)
// — see docs/frontend/PRODUCT_ROADMAP.md F2 for why single-meeting claims stay
// out of S7/S8/S9 and can never reach `council publish` regardless of Draft/
// Publish mode. Only ever populated in Draft mode (frontend/src/devMode.ts):
// in Publish mode, including the published site, this shows the standard
// "snapshot not found" error, since digest data never ships. No bespoke
// panels here: those are built against whole-corpus snapshot shapes, so every
// digest test renders through the same generic BatteryTestCard used for
// un-bespoke battery tests.
export function DigestPage() {
  const { data, loading, error } = useData<DigestData>(() => api.digest());
  const { data: cllrData } = useData<CouncillorsData>(() => api.councillors());
  if (loading) return <LoadingCard />;
  if (error || !data) {
    return (
      <ErrorCard
        msg={
          error ??
          (import.meta.env.DEV
            ? "This is a local review artifact and is never published. Run `council draft cambridge`, then flip the corner switch to DRAFT."
            : "This is a local review artifact and is never published.")
        }
      />
    );
  }

  // The digest snapshot carries only the 14 meeting_scope tests, so this
  // resolves to 14 rows, not 29 — correct, not padded; a category with none
  // of its tests meeting-scoped simply doesn't appear.
  //
  // title_technical/question_technical are put back to the snapshot's own
  // meeting-scoped phrasing ("Did anyone declare a conflict this meeting?")
  // on this surface only: the registry has no title_meeting/question_meeting
  // pair yet — that's a deliberately deferred Step 10 addition — and
  // substituting the corpus-wide copy here would silently change what the
  // digest says. category/principles/detail_panel come from the registry
  // like every other surface.
  const byId = new Map(data.tests.map((t) => [t.test_id, t]));
  const resolved = resolveTests(data.tests).map((r) => {
    const raw = byId.get(r.id)!;
    return { ...r, title_technical: raw.title, question_technical: raw.question };
  });
  const groups = groupByCategory(resolved);
  const meetingDate = new Date(`${data.meeting_date}T00:00:00`).toLocaleDateString("en-AU", {
    day: "numeric", month: "long", year: "numeric",
  });
  const s = data.summary;

  return (
    <div className="app">
      <CouncilHeader />
      <main className="main-grid">
        <section className="grid-full">
          <h3 className="analysis-group-heading">
            Single-meeting digest — local review only, never published
          </h3>
          <p className="chart-note">
            Meeting {data.meeting_id} · {meetingDate} · {s.n_tests} tests ·{" "}
            {s.n_supportive} supportive, {s.n_neutral} neutral, {s.n_critical} critical,{" "}
            {s.n_not_computable} not computable
          </p>
        </section>
        {groups.map((g) => (
          <Fragment key={g.name}>
            <section className="grid-full">
              <h3 className="analysis-group-heading">{g.name}</h3>
            </section>
            {g.tests.map((t) => (
              <section className="grid-full" key={t.id}>
                <BatteryTestCard test={t} cllrData={cllrData} />
              </section>
            ))}
          </Fragment>
        ))}
      </main>
    </div>
  );
}
