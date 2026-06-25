import { InterestsChart } from "./components/InterestsChart";
import { DivergencePanel } from "./components/DivergencePanel";
import { CoMoverGraph } from "./components/CoMoverGraph";
import { ContestationChart } from "./components/TrendsChart";
import { EngagementChart } from "./components/EngagementChart";
import { AlignmentHeatmap } from "./components/AlignmentHeatmap";
import { PlanningTrendChart } from "./components/PlanningTrendChart";
import { PlanningObjectionsPanel } from "./components/PlanningObjectionsPanel";
import { DissentProfilesChart } from "./components/DissentProfilesChart";
import { DissentCoalitionsPanel } from "./components/DissentCoalitionsPanel";
import { ConflictRecusalPanel } from "./components/ConflictRecusalPanel";
import { RecusalTrendPanel } from "./components/RecusalTrendPanel";
import { TenderConcentrationPanel } from "./components/TenderConcentrationPanel";
import { ObjectionDosePanel } from "./components/ObjectionDosePanel";
import { TransparencyTrendPanel } from "./components/TransparencyTrendPanel";
import { TenurePanel } from "./components/TenurePanel";
import { MayoralAgendaPanel } from "./components/MayoralAgendaPanel";
import { PowerPanel } from "./components/PowerPanel";
import { SponsorshipNetworkPanel } from "./components/SponsorshipNetworkPanel";
import { OverviewPanel } from "./components/OverviewPanel";

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
        {/* Overview — cross-cutting synthesis of every panel below */}
        <section className="grid-full">
          <OverviewPanel />
        </section>

        {/* Conflict of interest — flagship */}
        <section className="grid-full">
          <ConflictRecusalPanel />
        </section>

        {/* Recusal compliance over time — the Inquiry conduct shock */}
        <section className="grid-full">
          <RecusalTrendPanel />
        </section>

        {/* Voting power — who wins on contested decisions (second flagship) */}
        <section className="grid-full">
          <PowerPanel />
        </section>

        {/* Sponsorship network — who backed whom; the blocs the vote hides */}
        <section className="grid-full">
          <SponsorshipNetworkPanel />
        </section>

        {/* Tenders — where the money went */}
        <section className="grid-full">
          <TenderConcentrationPanel />
        </section>

        {/* Transparency — confidential business over time */}
        <section className="grid-full">
          <TransparencyTrendPanel />
        </section>

        {/* Planning analysis */}
        <section className="grid-full">
          <PlanningTrendChart />
        </section>

        <section className="grid-half">
          <PlanningObjectionsPanel />
        </section>

        <section className="grid-half">
          <ObjectionDosePanel />
        </section>

        <section className="grid-full">
          <DissentCoalitionsPanel />
        </section>

        {/* Dissent analysis */}
        <section className="grid-full">
          <DissentProfilesChart />
        </section>

        {/* Mayoral agenda-setting */}
        <section className="grid-full">
          <MayoralAgendaPanel />
        </section>

        {/* Council composition — tenure */}
        <section className="grid-full">
          <TenurePanel />
        </section>

        {/* Existing panels */}
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
