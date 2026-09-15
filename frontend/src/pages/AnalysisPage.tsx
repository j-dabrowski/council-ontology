import { Fragment } from "react";
import { CouncilHeader } from "../components/CouncilHeader";
import { SiteFooter } from "../components/SiteFooter";
import { Card, LoadingCard, ErrorCard } from "../components/InterestsChart";
import { SeverityChip } from "../components/SeverityChip";
import { ObjectionResponse } from "../components/ObjectionResponse";
import { RedactedText } from "../guardrail";
import { useData } from "../hooks/useData";
import { api, ScorecardData, CouncillorsData } from "../api";
import { resolveTests } from "../registry";
import { groupByCategory } from "../registry/grouping";
import { PANEL_COMPONENTS } from "../registry/components";
import { useScrollToTest } from "../registry/anchors";

// The page composes the shell; a registered panel only draws its body
// (docs/frontend/SURFACE_PROJECTION_PLAN.md B.3). Every row where
// has_deep_dive is true has a PANEL_COMPONENTS entry (Step 1's parity
// guarantee), so there is no bespoke/generic fork here any more — the
// registered component IS the panel, whichever kind it is.
export function AnalysisPage() {
  const { data, loading, error } = useData<ScorecardData>(() => api.scorecard());
  const { data: cllrData } = useData<CouncillorsData>(() => api.councillors());
  useScrollToTest();
  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const councillorNames = cllrData ? Object.keys(cllrData.by_name) : [];
  const groups = groupByCategory(resolveTests(data.tests).filter((t) => t.has_deep_dive));

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
              const PanelBody = PANEL_COMPONENTS[t.id];
              return (
                <section className="grid-full" data-test-id={t.id} key={t.id}>
                  <Card
                    title={t.title_technical}
                    finding={<RedactedText text={t.finding} names={councillorNames} testId={t.id} field="finding" />}
                    valence={t.valence}
                    backTo={t.id}
                  >
                    <div className={`bt-headline bt-${t.valence}`}>
                      <SeverityChip severity={t.severity} />
                    </div>
                    <PanelBody test={t} cllrData={cllrData} />
                    {t.valence === "critical" && <ObjectionResponse test={t} />}
                  </Card>
                </section>
              );
            })}
          </Fragment>
        ))}
      </main>

      <SiteFooter />
    </div>
  );
}
