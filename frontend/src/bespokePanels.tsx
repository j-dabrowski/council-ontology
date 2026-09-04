import { ComponentType } from "react";
import type { ResolvedTest } from "./registry/types";
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
import { QuestionResponsivenessPanel } from "./components/QuestionResponsivenessPanel";
import { SponsorshipNetworkPanel } from "./components/SponsorshipNetworkPanel";
import { ContestationChart } from "./components/TrendsChart";

// test_id -> dedicated component, for the tests that have earned a bespoke
// panel (richer drill-down than the generic BatteryTestPanel gives for
// free). Deliberately opt-in and manual (docs/frontend/INTERACTIVITY.md's
// recipe) — a test with no entry here still renders, via BatteryTestPanel,
// so missing from this map is never a visibility gap, only a polish one.
export const BESPOKE_PANELS: Record<string, ComponentType<{ test: ResolvedTest }>> = {
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
};
