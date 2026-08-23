import { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell, ReferenceLine,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, RecusalProfile, DeclarationDetail } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";
import { DrillDown, SourceQuote, Reveal } from "./DrillDown";
import { CouncillorLink, CouncillorTick } from "./CouncillorModal";

const TYPE_LABEL: Record<string, string> = {
  financial: "Financial", proximity: "Proximity",
  impartiality: "Impartiality", other: "Other",
};

function DeclarationRow({ d }: { d: DeclarationDetail }) {
  const t = d.interest_type ?? "other";
  return (
    <div className={`decl-row${d.must_leave ? " decl-mustleave" : ""}`}>
      <div className="decl-row-head">
        <span className={`decl-type decl-type-${t}`}>
          {TYPE_LABEL[t] ?? "Declared"}
          {d.must_leave && <span className="decl-mustleave-tag"> · must leave</span>}
        </span>
        <span className="decl-date">{d.date}{d.item ? ` · item ${d.item}` : ""}</span>
        <span className="decl-action">{d.action}</span>
      </div>
      {d.title && <div className="decl-title">{d.title}</div>}
      <div className="decl-what">{d.what || <em>no description recorded</em>}</div>
      <SourceQuote quote={d.quote} />
    </div>
  );
}

// Colour is graded on must_leave_recusal_rate — compliance on legally-mandatory
// financial/proximity conflicts only — never the blended recusal_rate, which
// mixes in lawful "impartiality" declarations a councillor is entitled to stay
// and vote on and can therefore mask (or invert) a real mandatory-conflict
// compliance picture. See docs/review — BLOCKING flag, 2026-08-11 pass 2.
//
// Councillors resting on <=3 must-leave declarations are excluded from this
// chart entirely (see SMALL_N_FLOOR below) rather than colour-graded, so this
// function is only ever called on profiles that already clear that floor.
// - null (zero must-leave declarations on record) -> grey, no compliance
//   colour applies at all.
// - otherwise -> the ordinary green/lime/amber/red scale.
function recusalColor(p: RecusalProfile): string {
  const r = p.must_leave_recusal_rate;
  if (r === null) return "#94a3b8"; // grey — zero must-leave declarations
  if (r >= 0.6) return "#22c55e";
  if (r >= 0.3) return "#84cc16";
  if (r >= 0.1) return "#f59e0b";
  return "#f87171";
}

// A named, legally-mandatory recusal rate computed from 3 or fewer records is
// not defensible regardless of framing — a single misattributed declaration
// (extraction error) can flip the whole rate for that person. See docs/review,
// BLOCKING flag, 2026-08-22 pass 1. Below this floor, a councillor is excluded
// from the named per-councillor breakdown entirely rather than shown with a
// caveat colour.
const SMALL_N_FLOOR = 3;

const CustomTooltip = ({ active, payload }: {
  active?: boolean;
  payload?: { payload: RecusalProfile & { pct: number } }[];
}) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const stayed = d.declared_votes - d.recused;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{d.name}{d.is_active ? " ●" : ""}</p>
      <p style={{ color: "var(--text-hi)" }}>
        {d.must_leave_recusal_rate !== null ? (
          <>
            Must-leave conflicts: <strong>{d.must_leave_recused}/{d.must_leave_declared}</strong>
            {" "}({Math.round(d.must_leave_recusal_rate * 100)}%)
          </>
        ) : (
          "No must-leave (financial/proximity) declarations on record"
        )}
      </p>
      <p style={{ color: "var(--text-muted)" }}>
        All declared interests: <strong>{d.pct}%</strong> stepped out ({d.recused} of {d.declared_votes})
      </p>
      <p style={{ color: "var(--text-muted)" }}>
        Recused {d.recused} · stayed and voted {stayed} · {d.declared_votes} declared in total
      </p>
    </div>
  );
};

interface HistBucket { label: string; lo: number; hi: number; count: number }

const HistTooltip = ({ active, payload }: {
  active?: boolean;
  payload?: { payload: HistBucket }[];
}) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{d.label} stepped out</p>
      <p style={{ color: "var(--text-hi)" }}>
        <strong>{d.count}</strong> councillor{d.count === 1 ? "" : "s"}
      </p>
    </div>
  );
};

export function ConflictRecusalPanel() {
  const { data, loading, error } = useData(() => api.declared());
  const [selected, setSelected] = useState<string | null>(null);

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const selectedProfile = selected
    ? data.profiles.find((p) => p.name === selected) ?? null
    : null;

  // Reader clicking through to verify a bar's colour should see the number
  // the colour is actually based on (must-leave rate), not just the blended
  // figure — both stated explicitly, neither replacing the other.
  const drillSubtitle = (p: RecusalProfile) => {
    const blended = `all declared interests: ${p.recused}/${p.declared_votes} (${Math.round(p.recusal_rate * 100)}%)`;
    if (p.must_leave_recusal_rate === null) {
      return `${p.declarations.length} on record · no must-leave conflicts on record · ${blended}`;
    }
    const mustLeave = `must-leave conflicts: ${p.must_leave_recused}/${p.must_leave_declared} (${Math.round(p.must_leave_recusal_rate * 100)}%)`;
    return `${p.declarations.length} on record · ${mustLeave} · ${blended}`;
  };

  const chartData = data.profiles
    .map((p) => ({
      ...p,
      shortName: p.name.split(" ").slice(-1)[0] || p.name,
      // Blended rate — drives the histogram above and the "declared items"
      // stat; unrelated to compliance grading.
      pct: +(p.recusal_rate * 100).toFixed(0),
      // What the per-councillor bar's length AND colour are graded on: the
      // must-leave-only rate when one exists, the blended rate only as a
      // fallback for zero-must-leave (grey) profiles.
      gradePct: +((p.must_leave_recusal_rate ?? p.recusal_rate) * 100).toFixed(0),
    }));

  // The named per-councillor breakdown excludes anyone whose must-leave rate
  // rests on <=SMALL_N_FLOOR records — see the note above recusalColor().
  const namedChartData = chartData.filter(
    (p) => p.must_leave_recusal_rate === null || p.must_leave_declared > SMALL_N_FLOOR
  );
  const smallNExcluded = chartData.length - namedChartData.length;

  const chartHeight = Math.max(320, namedChartData.length * 30);

  // How much more likely is a recusal once an interest is declared?
  const factor = data.baseline_recusal_pct > 0
    ? Math.round(data.declared_recusal_pct / data.baseline_recusal_pct)
    : null;

  // Unnamed default view: distribution of recusal rates across the chamber,
  // no identity attached. The per-councillor breakdown (name + rate together)
  // only renders once the reader explicitly opens it below — see BLOCKING #2,
  // docs/review, 2026-08-11.
  const HIST_WIDTH = 20;
  const histogram: HistBucket[] = Array.from({ length: 5 }, (_, i) => {
    const lo = i * HIST_WIDTH;
    const hi = lo + HIST_WIDTH;
    return {
      label: `${lo}–${hi === 100 ? 100 : hi}%`,
      lo,
      hi,
      count: chartData.filter((p) => p.pct >= lo && (hi === 100 ? p.pct <= hi : p.pct < hi)).length,
    };
  });
  const nWithMustLeave = chartData.filter((p) => p.declarations.some((d) => d.must_leave)).length;

  return (
    <Card
      title="Declaring a Conflict — Do Councillors Step Out, or Vote Anyway?"
      subtitle="Behaviour on votes where the councillor declared an interest · 1995–2026"
      valence="critical"
      backTo="sc-declared"
    >
      <div className="planning-hero-row">
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-recent">{data.baseline_recusal_pct}%</span>
          <span className="planning-stat-label">step out on a normal vote</span>
        </div>
        <div className="planning-stat-arrow">→</div>
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-peak">{data.declared_recusal_pct}%</span>
          <span className="planning-stat-label">step out when they declare a conflict</span>
        </div>
        <div className="planning-stat-divider" />
        <div className="planning-stat">
          <span className="planning-stat-num">{data.declared_total.toLocaleString()}</span>
          <span className="planning-stat-label">declared-interest votes on record</span>
        </div>
      </div>

      <div className="objection-callout">
        <span className="objection-callout-diff">{factor ? `${factor}×` : "—"}</span>
        <span className="objection-callout-text">
          Declaring an interest makes a councillor about <strong>{factor}× more likely</strong> to
          recuse ({data.declared_recusal_pct}% vs {data.baseline_recusal_pct}% baseline, n=
          {data.declared_total.toLocaleString()}/{data.baseline_total.toLocaleString()}) — yet they
          still stay in the chamber and vote roughly <strong>three times out of four</strong>. And
          when they do vote, they side against the motion <em>less</em> often than usual (
          {data.declared_against_pct}% vs {data.baseline_against_pct}%): a declared-interest vote
          leans toward letting the matter through.
        </span>
      </div>

      <p className="section-heading">
        How council-wide recusal behaviour is distributed — councillors with ≥8 declared votes
      </p>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={histogram} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={0} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11 }} width={30} />
          <Tooltip content={<HistTooltip />} cursor={{ fill: "var(--cursor)" }} />
          <Bar dataKey="count" name="Councillors" radius={[3, 3, 0, 0]} fill="#60a5fa" />
        </BarChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Distribution of stepped-out rates across the {chartData.length} councillors with ≥8
        declared-interest votes — no individual named at this level. Of these, {nWithMustLeave} have at
        least one legally-mandatory ("must-leave") declaration on record; the rest have only ever
        declared lawful "impartiality" interests, which they are entitled to stay and vote on.
      </p>

      <Reveal label="see the per-councillor breakdown, by name">
        <p className="section-heading" style={{ marginTop: 12 }}>
          Who steps out, and who stays
          <span className="section-hint"> · click a bar to see the actual interests they declared</span>
        </p>
        <ResponsiveContainer width="100%" height={chartHeight}>
          <BarChart
            data={namedChartData}
            layout="vertical"
            margin={{ top: 4, right: 48, bottom: 4, left: 92 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" horizontal={false} />
            <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="name" width={88}
              tick={({ x, y, payload }: { x: number | string; y: number | string; payload: { value: string } }) => (
                <CouncillorTick x={x} y={y} payload={payload} />
              )} />
            <ReferenceLine
              x={data.declared_recusal_pct}
              stroke="#475569"
              strokeDasharray="4 4"
              label={{ value: "chamber avg", position: "top", fontSize: 10, fill: "#64748b" }}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: "var(--cursor)" }} />
            <Bar
              dataKey="gradePct"
              name="Recusal %"
              radius={[0, 3, 3, 0]}
              cursor="pointer"
              onClick={(entry: { name?: string }) => entry?.name && setSelected(entry.name)}
            >
              {namedChartData.map((entry, i) => (
                <Cell key={i} fill={recusalColor(entry)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>

        {selectedProfile && (
          <DrillDown
            title={<><CouncillorLink name={selectedProfile.name} /> — declared interests</>}
            subtitle={drillSubtitle(selectedProfile)}
            onClose={() => setSelected(null)}
          >
            {selectedProfile.declarations.length === 0 && (
              <p className="chart-note">No itemised declarations extracted for this councillor.</p>
            )}
            {selectedProfile.declarations.map((d, i) => (
              <DeclarationRow key={i} d={d} />
            ))}
          </DrillDown>
        )}

        <p className="chart-note">
          "Recusal" = recorded ABSENT on an item where the councillor declared an interest — i.e. they
          left the room rather than vote. Bar length and colour here are graded on the{" "}
          <strong>must-leave-only</strong> rate — legally-mandatory financial/proximity conflicts —
          not the blended rate quoted elsewhere on this page, because a councillor can post a low
          blended rate purely out of lawful "impartiality" declarations they are entitled to stay and
          vote on. Green = usually steps out on a mandatory conflict; amber/red = usually stays and
          votes on one; <strong>grey = no must-leave declarations on record</strong> — only lawful
          "impartiality" ones, so no compliance colour applies. {smallNExcluded > 0 && (
            <>{smallNExcluded} further councillor{smallNExcluded === 1 ? "" : "s"} with{" "}
            {SMALL_N_FLOOR} or fewer must-leave declarations on record{" "}
            {smallNExcluded === 1 ? "is" : "are"} not shown by name here — too small a sample to
            attribute a legally-mandatory compliance rate to one person. </>
          )}The spread among the shown bars is stark: some councillors recuse on the clear majority
          of their mandatory conflicts, others have declared one dozens of times and never once left
          the chamber.
        </p>
      </Reveal>

      <p className="chart-note">
        <strong>In the council's defence:</strong> the first limb of the safeguard plainly works —
        declaring an interest lifts recusal about {factor}×, so disclosure is real, not cosmetic, and
        many of these declarations are lawful "impartiality" interests the member is *entitled* to stay
        and vote on. The data concedes that. What it still raises is the *manage* limb: staying and
        voting three times out of four leaves the identify–disclose–<strong>manage</strong> chain
        breaking at the last link. Severity: Governance-concern · Nolan Integrity, Objectivity.
      </p>
    </Card>
  );
}
