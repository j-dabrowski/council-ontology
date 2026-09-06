import { ComponentType } from "react";
import type { CouncillorsData } from "../api";
import type { ResolvedTest } from "./types";
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
import { QuestionResponsivenessPanel } from "../components/QuestionResponsivenessPanel";
import { SponsorshipNetworkPanel } from "../components/SponsorshipNetworkPanel";
import { ContestationChart } from "../components/TrendsChart";
import { BatteryTestCard } from "../components/BatteryTestPanel";

// test_id -> the component that draws its /analysis panel. An entry means
// "this test renders a panel on /analysis" (docs/frontend/
// SURFACE_PROJECTION_PLAN.md B.1) — 13 tests get a dedicated, richer
// component (docs/frontend/INTERACTIVITY.md's recipe); the other 14
// chart-bearing tests point at the generic BatteryTestCard, which renders
// whatever chart payload the snapshot carries. The remaining 2 registry rows
// (`has_deep_dive: false`) are not computable on this corpus and have no
// entry here — they appear on the scorecard only. Chart components
// themselves stay in `components/`; this map only references them.
export const PANEL_COMPONENTS: Record<
  string,
  ComponentType<{ test: ResolvedTest; cllrData: CouncillorsData | null }>
> = {
  "conflict.recusal_management": ConflictRecusalPanel,
  "conflict.recusal_trend": RecusalTrendPanel,
  "procurement.concentration": TenderConcentrationPanel,
  "governance.officer_ratification": DivergencePanel,
  "governance.power_spread": PowerPanel,
  "governance.durable_faction": SponsorshipNetworkPanel,
  "governance.incumbency": TenurePanel,
  "governance.chair_capture": MayoralAgendaPanel,
  "transparency.confidential_share": TransparencyTrendPanel,
  "engagement.question_responsiveness": QuestionResponsivenessPanel,
  "engagement.participation": EngagementChart,
  "planning.objection_responsiveness": ObjectionDosePanel,
  "governance.unanimity_trend": ContestationChart,
  "procurement.threshold_gaming": BatteryTestCard,
  "procurement.incumbency": BatteryTestCard,
  "procurement.decider_supplier_conflict": BatteryTestCard,
  "conflict.delegate_body_conflict": BatteryTestCard,
  "planning.big_dollar_leniency": BatteryTestCard,
  "planning.repeat_applicant": BatteryTestCard,
  "governance.oversight_body_capture": BatteryTestCard,
  "governance.freshman_effect": BatteryTestCard,
  "governance.election_cycle": BatteryTestCard,
  "governance.attendance": BatteryTestCard,
  "transparency.confidential_tender_size": BatteryTestCard,
  "transparency.confidential_topics": BatteryTestCard,
  "finance.eoy_spending": BatteryTestCard,
  "engagement.deputation_dissent": BatteryTestCard,
};
