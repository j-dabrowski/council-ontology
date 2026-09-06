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
import { BatteryTestBody } from "../components/BatteryTestPanel";

// test_id -> the body-only component that draws its /analysis panel. An
// entry means "this test renders a panel on /analysis" (docs/frontend/
// SURFACE_PROJECTION_PLAN.md B.1) — 13 tests get a dedicated, richer
// component (docs/frontend/INTERACTIVITY.md's recipe); the other 14
// chart-bearing tests point at the generic BatteryTestBody, which renders
// whatever chart payload the snapshot carries. Every entry is body-only —
// the analysis page's shell supplies the Card, severity chip and
// Objection/Response uniformly (B.3), so a registered component here never
// wraps itself in a Card. The remaining 2 registry rows (`has_deep_dive:
// false`) are not computable on this corpus and have no entry here — they
// appear on the scorecard only. Chart components themselves stay in
// `components/`; this map only references them.
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
  "procurement.threshold_gaming": BatteryTestBody,
  "procurement.incumbency": BatteryTestBody,
  "procurement.decider_supplier_conflict": BatteryTestBody,
  "conflict.delegate_body_conflict": BatteryTestBody,
  "planning.big_dollar_leniency": BatteryTestBody,
  "planning.repeat_applicant": BatteryTestBody,
  "governance.oversight_body_capture": BatteryTestBody,
  "governance.freshman_effect": BatteryTestBody,
  "governance.election_cycle": BatteryTestBody,
  "governance.attendance": BatteryTestBody,
  "transparency.confidential_tender_size": BatteryTestBody,
  "transparency.confidential_topics": BatteryTestBody,
  "finance.eoy_spending": BatteryTestBody,
  "engagement.deputation_dissent": BatteryTestBody,
};
