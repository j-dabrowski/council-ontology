import { Fragment } from "react";
import { CouncilHeader } from "../components/CouncilHeader";
import { BatteryTestPanel } from "../components/BatteryTestPanel";
import { LoadingCard, ErrorCard } from "../components/InterestsChart";
import { useData } from "../hooks/useData";
import { api, ScorecardData } from "../api";
import { resolveTests } from "../registry";
import { groupByCategory } from "../registry/grouping";
import { BESPOKE_PANELS } from "../bespokePanels";

// Every battery test gets a panel, driven by the published scorecard data —
// not a hardcoded per-test_id list. A test with a BESPOKE_PANELS entry gets
// its dedicated component; everything else renders through the generic
// BatteryTestPanel (which "gets a panel for free", per its own docstring).
// This is what makes a newly Refiner-codified, published test show up here
// with a working anchor link with no frontend change required.
export function AnalysisPage() {
  const { data, loading, error } = useData<ScorecardData>(() => api.scorecard());
  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const groups = groupByCategory(resolveTests(data.tests));

  return (
    <div className="app">
      <CouncilHeader />

      <main className="main-grid">
        {groups.map((g) => (
          <Fragment key={g.name}>
            <section className="grid-full">
              <h3 className="analysis-group-heading">{g.name}</h3>
            </section>
            {g.tests.map((t) => {
              const Bespoke = BESPOKE_PANELS[t.id];
              return (
                <section className="grid-full" id={`panel-${t.detail_panel}`} key={t.id}>
                  {Bespoke ? <Bespoke /> : <BatteryTestPanel testId={t.id} />}
                </section>
              );
            })}
          </Fragment>
        ))}
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
