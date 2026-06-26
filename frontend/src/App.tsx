import { useState } from "react";
import { CouncillorProvider } from "./components/CouncillorModal";
import { Logo } from "./components/Logo";
import { DivergencePanel } from "./components/DivergencePanel";
import { EngagementChart } from "./components/EngagementChart";
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
import { ScorecardPanel } from "./components/ScorecardPanel";
import { BatteryTestPanel } from "./components/BatteryTestPanel";

// The page is the battery: every panel below is a test, rendered in the SAME
// ORDER as the scorecard rows. Bespoke components for the rich tests; the generic
// BatteryTestPanel (by test_id) for the rest. Section id = panel-<slug> so the
// scorecard "jump to panel" links land here. (Eight descriptive non-test panels
// were retired — not tests — but their components remain in the repo for reuse.)
export default function App() {
  const [council, setCouncil] = useState("cambridge");

  const Test = (slug: string, testId: string) => (
    <section className="grid-full" id={`panel-${slug}`}>
      <BatteryTestPanel testId={testId} />
    </section>
  );

  return (
    <CouncillorProvider>
    <div className="app">
      <header className="site-header">
        <div className="header-inner">
          <Logo />
          <h1 className="site-title">
            City of{" "}
            <span className="council-select-wrap">
              <select
                className="council-select"
                value={council}
                onChange={e => setCouncil(e.target.value)}
              >
                <option value="cambridge">Cambridge</option>
              </select>
            </span>
            {" "}Council
          </h1>
          <p className="site-subtitle">
            Analysis of meeting minutes · 1995–2026 ·{" "}
            <span className="data-note">Full 30-year corpus</span>
          </p>
        </div>
      </header>

      <main className="main-grid">
        <section className="grid-full">
          <OverviewPanel />
        </section>
        <section className="grid-full">
          <ScorecardPanel />
        </section>

        {/* ── Integrity & procurement ── */}
        <section className="grid-full" id="panel-declared"><ConflictRecusalPanel /></section>
        <section className="grid-full" id="panel-recusal"><RecusalTrendPanel /></section>
        {Test("single-source", "procurement.single_source")}
        <section className="grid-full" id="panel-tenders"><TenderConcentrationPanel /></section>
        {Test("threshold-gaming", "procurement.threshold_gaming")}
        {Test("incumbency", "procurement.incumbency")}
        {Test("repeat-applicant", "planning.repeat_applicant")}

        {/* ── Governance & culture ── */}
        <section className="grid-full" id="panel-divergence"><DivergencePanel /></section>
        <section className="grid-full" id="panel-power"><PowerPanel /></section>
        {Test("unanimity", "governance.unanimity_trend")}
        <section className="grid-full" id="panel-sponsorship"><SponsorshipNetworkPanel /></section>
        <section className="grid-full" id="panel-tenure"><TenurePanel /></section>
        {Test("freshman", "governance.freshman_effect")}
        {Test("election-cycle", "governance.election_cycle")}
        {Test("attendance", "governance.attendance")}
        {Test("big-dollar", "planning.big_dollar_leniency")}
        <section className="grid-full" id="panel-mayoral"><MayoralAgendaPanel /></section>

        {/* ── Transparency & engagement ── */}
        <section className="grid-full" id="panel-transparency"><TransparencyTrendPanel /></section>
        <section className="grid-full" id="panel-engagement"><EngagementChart /></section>
        {Test("deputations", "engagement.deputation_dissent")}
        <section className="grid-full" id="panel-dose"><ObjectionDosePanel /></section>

        {/* ── Financial ── */}
        {Test("eoy", "finance.eoy_spending")}
        {Test("reserve", "finance.reserve_trajectory")}
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
    </CouncillorProvider>
  );
}
