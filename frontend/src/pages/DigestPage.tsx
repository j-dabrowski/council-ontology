import { Fragment } from "react";
import { CouncilHeader } from "../components/CouncilHeader";
import { BatteryTestCard } from "../components/BatteryTestPanel";
import { LoadingCard, ErrorCard } from "../components/InterestsChart";
import { useData } from "../hooks/useData";
import { api, ScorecardData, CouncillorsData } from "../api";
import { groupTestsByGenre } from "../groupTestsByGenre";

// Local-review-only surface for `council meeting-digest --save` output
// (see docs/frontend/PRODUCT_ROADMAP.md F2 and `council meeting-digest`'s
// own docstring): never wired into `council draft`/`council publish`, so
// /data/digest.json only exists when a dev server is started with
// VITE_DIGEST_FILE set (see vite.config.ts's digestPreview() plugin) —
// everywhere else, including the published site, this page shows the
// standard "snapshot not found" error. No bespoke panels here: those are
// built against whole-corpus snapshot shapes, so every digest test renders
// through the same generic BatteryTestCard used for un-bespoke battery tests.
export function DigestPage() {
  const { data, loading, error } = useData<ScorecardData>(() => api.digest());
  const { data: cllrData } = useData<CouncillorsData>(() => api.councillors());
  if (loading) return <LoadingCard />;
  if (error || !data) {
    return (
      <ErrorCard
        msg={error ?? "run 'council meeting-digest <council> --meeting <id> --save', then start the dev server with VITE_DIGEST_FILE set to that file"}
      />
    );
  }

  const groups = groupTestsByGenre(data.tests);

  return (
    <div className="app">
      <CouncilHeader />
      <main className="main-grid">
        <section className="grid-full">
          <h3 className="analysis-group-heading">
            Single-meeting digest — local review only, never published
          </h3>
        </section>
        {groups.map((g) => (
          <Fragment key={g.name}>
            <section className="grid-full">
              <h3 className="analysis-group-heading">{g.name}</h3>
            </section>
            {g.tests.map((t) => (
              <section className="grid-full" key={t.test_id}>
                <BatteryTestCard test={t} cllrData={cllrData} />
              </section>
            ))}
          </Fragment>
        ))}
      </main>
    </div>
  );
}
