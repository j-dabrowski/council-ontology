import { CouncilHeader } from "../components/CouncilHeader";
import { OverviewPanel } from "../components/OverviewPanel";
import { ScorecardPanel } from "../components/ScorecardPanel";

export function OverviewPage() {
  return (
    <div className="app">
      <CouncilHeader />

      <main className="main-grid">
        <section className="grid-full">
          <OverviewPanel />
        </section>
        <section className="grid-full">
          <ScorecardPanel />
        </section>
      </main>

      <footer className="site-footer">
        <p>
          Source: City of Cambridge council meeting minutes (public record) ·
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
