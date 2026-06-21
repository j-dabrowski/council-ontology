import { InterestsChart } from "./components/InterestsChart";
import { DivergencePanel } from "./components/DivergencePanel";
import { CoMoverGraph } from "./components/CoMoverGraph";
import { ContestationChart } from "./components/TrendsChart";
import { EngagementChart } from "./components/EngagementChart";
import { AlignmentHeatmap } from "./components/AlignmentHeatmap";

export default function App() {
  return (
    <div className="app">
      <header className="site-header">
        <div className="header-inner">
          <h1 className="site-title">City of Cambridge Council</h1>
          <p className="site-subtitle">
            Analysis of meeting minutes · 2024–2026 ·{" "}
            <span className="data-note">30-year corpus extraction in progress</span>
          </p>
        </div>
      </header>

      <main className="main-grid">
        <section className="grid-full">
          <DivergencePanel />
        </section>

        <section className="grid-half">
          <InterestsChart />
        </section>
        <section className="grid-half">
          <ContestationChart />
        </section>

        <section className="grid-full">
          <CoMoverGraph />
        </section>

        <section className="grid-half">
          <EngagementChart />
        </section>
        <section className="grid-half">
          <AlignmentHeatmap />
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
