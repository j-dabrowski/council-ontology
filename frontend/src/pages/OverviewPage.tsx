import { CouncilHeader } from "../components/CouncilHeader";
import { LatestMeetingStrip } from "../components/LatestMeetingStrip";
import { OverviewPanel } from "../components/OverviewPanel";
import { RatingBand } from "../components/RatingBand";
import { ScorecardPanel } from "../components/ScorecardPanel";

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
