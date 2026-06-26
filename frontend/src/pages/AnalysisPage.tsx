import { CouncilHeader } from "../components/CouncilHeader";
import { DivergencePanel } from "../components/DivergencePanel";
import { EngagementChart } from "../components/EngagementChart";
import { ConflictRecusalPanel } from "../components/ConflictRecusalPanel";
import { RecusalTrendPanel } from "../components/RecusalTrendPanel";
import { TenderConcentrationPanel } from "../components/TenderConcentrationPanel";
import { ObjectionDosePanel } from "../components/ObjectionDosePanel";
import { TransparencyTrendPanel } from "../components/TransparencyTrendPanel";
import { TenurePanel } from "../components/TenurePanel";
import { MayoralAgendaPanel } from "../components/MayoralAgendaPanel";
import { PowerPanel } from "../components/PowerPanel";
import { SponsorshipNetworkPanel } from "../components/SponsorshipNetworkPanel";
import { BatteryTestPanel } from "../components/BatteryTestPanel";

export function AnalysisPage() {
  const Test = (slug: string, testId: string) => (
    <section className="grid-full" id={`panel-${slug}`}>
      <BatteryTestPanel testId={testId} />
    </section>
  );

  return (
    <div className="app">
      <CouncilHeader />

      <main className="main-grid">

        <section className="grid-full">
          <h3 className="analysis-group-heading">Integrity &amp; Procurement</h3>
        </section>
        <section className="grid-full" id="panel-declared"><ConflictRecusalPanel /></section>
        <section className="grid-full" id="panel-recusal"><RecusalTrendPanel /></section>
        {Test("single-source", "procurement.single_source")}
        <section className="grid-full" id="panel-tenders"><TenderConcentrationPanel /></section>
        {Test("threshold-gaming", "procurement.threshold_gaming")}
        {Test("incumbency", "procurement.incumbency")}
        {Test("repeat-applicant", "planning.repeat_applicant")}

        <section className="grid-full">
          <h3 className="analysis-group-heading">Governance &amp; Culture</h3>
        </section>
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

        <section className="grid-full">
          <h3 className="analysis-group-heading">Transparency &amp; Engagement</h3>
        </section>
        <section className="grid-full" id="panel-transparency"><TransparencyTrendPanel /></section>
        <section className="grid-full" id="panel-engagement"><EngagementChart /></section>
        {Test("deputations", "engagement.deputation_dissent")}
        <section className="grid-full" id="panel-dose"><ObjectionDosePanel /></section>

        <section className="grid-full">
          <h3 className="analysis-group-heading">Financial</h3>
        </section>
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
  );
}
