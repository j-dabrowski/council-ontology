import { Fragment } from "react";
import { CouncilHeader } from "../components/CouncilHeader";
import { BatteryTestCard } from "../components/BatteryTestPanel";
import { LoadingCard, ErrorCard } from "../components/InterestsChart";
import { useData } from "../hooks/useData";
import { api, DigestData, CouncillorsData } from "../api";
import { groupTestsByGenre } from "../groupTestsByGenre";
import { resolveTests } from "../registry";

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

  const groups = groupTestsByGenre(data.tests);
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
            {g.tests.map((t) => {
              // BatteryTestCard now takes a ResolvedTest (Step 7) — resolved
              // here per-row purely to keep compiling; title_technical/
              // question_technical are put straight back to the snapshot's
              // own meeting-scoped phrasing ("Did anyone declare a conflict
              // this meeting?"), since the registry has no meeting-scoped
              // copy field yet and substituting its corpus-wide title would
              // silently change what this page says (TEST_REGISTRY_PLAN.md
              // Step 9, not done here).
              const [resolved] = resolveTests([t]);
              if (!resolved) return null;
              const test = { ...resolved, title_technical: t.title, question_technical: t.question };
              return (
                <section className="grid-full" key={t.test_id}>
                  <BatteryTestCard test={test} cllrData={cllrData} />
                </section>
              );
            })}
          </Fragment>
        ))}
      </main>
    </div>
  );
}
