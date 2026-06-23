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
            Analysis of meeting minutes · 1995–2026 ·{" "}
            <span className="data-note">Full 30-year corpus</span>
          </p>
        </div>
      </header>

      <main className="main-grid">
        <section className="grid-full">
          <DivergencePanel />
        </section>

        <section className="grid-full">
          <InterestsChart />
        </section>
        <section className="grid-full">
          <AlignmentHeatmap />
        </section>

        <section className="grid-full">
          <ContestationChart />
        </section>

        <section className="grid-full">
          <CoMoverGraph />
        </section>

        <section className="grid-full">
          <EngagementChart />
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
