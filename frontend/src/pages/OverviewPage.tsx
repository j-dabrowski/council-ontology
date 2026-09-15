import { CouncilHeader } from "../components/CouncilHeader";
import { LatestMeetingStrip } from "../components/LatestMeetingStrip";
import { OverviewPanel } from "../components/OverviewPanel";
import { RatingBand } from "../components/RatingBand";
import { ScorecardPanel } from "../components/ScorecardPanel";
import { SiteFooter } from "../components/SiteFooter";

export function OverviewPage() {
  return (
    <div className="app">
      <CouncilHeader />

      <main className="main-grid">
        <section className="grid-full">
          <RatingBand />
        </section>
        <section className="grid-full">
          <LatestMeetingStrip />
        </section>
        <section className="grid-full">
          <OverviewPanel />
        </section>
        <section className="grid-full">
          <ScorecardPanel />
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
