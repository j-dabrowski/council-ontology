import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, Cell
} from "recharts";
import { useData } from "../hooks/useData";
import { api } from "../api";
import { ValenceChip } from "./ValenceChip";
import { Reveal } from "./DrillDown";
import { CouncillorTick } from "./CouncillorModal";

const COLORS = {
  financial: "#ef4444",
  impartiality: "#94a3b8",
  proximity: "#f59e0b",
  other: "#cbd5e1",
};

// A named individual's per-category count computed from <=3 records isn't a
// defensible per-person claim regardless of framing — see docs/review,
// BLOCKING flag, 2026-08-22 pass 1 (and pass 2: folding on the combined
// financial+proximity sum let a person with a large count in one category
// and a small count in the other still render the small one individually —
// each category must be folded independently). Applies to all four
// categories, not just the two legally must-leave ones — financial,
// proximity, and impartiality each fold into "Other" below this floor;
// "Other" itself has no distinct legal meaning to protect, so a small
// "Other" count needs no folding. Separately, a councillor whose *total*
// across all categories is at or under this floor is excluded from the
// named breakdown entirely (matching ConflictRecusalPanel.tsx's own
// SMALL_N_FLOOR) rather than shown with every category folded away.
const SMALL_N_FLOOR = 3;

interface HistBucket { label: string; lo: number; hi: number; count: number }

export function InterestsChart() {
  const { data, loading, error } = useData(() => api.interests());

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const chartDataAll = data.map((s) => {
    const financial = s.by_type.financial ?? 0;
    const proximity = s.by_type.proximity ?? 0;
    const impartiality = s.by_type.impartiality ?? 0;
    const other = s.by_type.other ?? 0;
    const financialSmall = financial > 0 && financial <= SMALL_N_FLOOR;
    const proximitySmall = proximity > 0 && proximity <= SMALL_N_FLOOR;
    const impartialitySmall = impartiality > 0 && impartiality <= SMALL_N_FLOOR;
    const smallN = financialSmall || proximitySmall || impartialitySmall;
    return {
      name: s.councillor_name,
      financial: financialSmall ? 0 : financial,
      proximity: proximitySmall ? 0 : proximity,
      impartiality: impartialitySmall ? 0 : impartiality,
      other: other
        + (financialSmall ? financial : 0)
        + (proximitySmall ? proximity : 0)
        + (impartialitySmall ? impartiality : 0),
      total: s.total,
      smallN,
      financialSmall,
      proximitySmall,
      impartialitySmall,
    };
  });

  // Councillors resting on <=SMALL_N_FLOOR total declarations are excluded
  // from the named breakdown entirely, not just folded category-by-category
  // — see the note above SMALL_N_FLOOR.
  const chartData = chartDataAll.filter((d) => d.total > SMALL_N_FLOOR);
  const smallNRowsExcluded = chartDataAll.length - chartData.length;

  const maxFinancial = Math.max(...chartData.map((d) => d.financial));
  const chartHeight = Math.max(300, chartData.length * 28);
  const smallNCount = chartData.filter((d) => d.smallN).length;

  const HIST_BUCKETS: { label: string; lo: number; hi: number }[] = [
    { label: "0", lo: 0, hi: 0 },
    { label: "1–3", lo: 1, hi: 3 },
    { label: "4–9", lo: 4, hi: 9 },
    { label: "10–19", lo: 10, hi: 19 },
    { label: "20+", lo: 20, hi: Infinity },
  ];
  const histogram: HistBucket[] = HIST_BUCKETS.map((b) => ({
    ...b,
    count: data.filter((s) => {
      const n = (s.by_type.financial ?? 0) + (s.by_type.proximity ?? 0);
      return n >= b.lo && n <= b.hi;
    }).length,
  }));

  return (
    <Card title="Interest Declarations by Councillor" subtitle="1995–2026" valence="neutral">
      <p className="section-heading">
        How financial/proximity ("must-leave") declarations are distributed across the chamber
      </p>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={histogram} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={0} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11 }} width={30} />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload as HistBucket;
              return (
                <div className="tooltip">
                  <p className="tooltip-title">{d.label} declarations</p>
                  <p style={{ color: "var(--text-hi)" }}>
                    <strong>{d.count}</strong> councillor{d.count === 1 ? "" : "s"}
                  </p>
                </div>
              );
            }}
          />
          <Bar dataKey="count" name="Councillors" radius={[3, 3, 0, 0]} fill="#f59e0b" />
        </BarChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Financial and proximity declarations are both legally must-leave categories. No individual
        named at this level.
      </p>

      <Reveal label="see the per-councillor breakdown, by name">
        <p className="section-heading" style={{ marginTop: 12 }}>
          Interest declarations by councillor
          <span className="section-hint"> · click a name for their full profile</span>
        </p>
        <ResponsiveContainer width="100%" height={chartHeight}>
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 4, right: 32, bottom: 4, left: 64 }}
          >
            <XAxis type="number" tick={{ fontSize: 12 }} />
            <YAxis type="category" dataKey="name" width={88}
              tick={({ x, y, payload }: { x: number | string; y: number | string; payload: { value: string } }) => (
                <CouncillorTick x={x} y={y} payload={payload} />
              )} />
            <Tooltip
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null;
                const row = chartData.find((d) => d.name === label);
                return (
                  <div className="tooltip">
                    <p className="tooltip-title">{row?.name}</p>
                    {payload.map((p, i) => (
                      <p key={i} style={{ color: p.fill as string }}>
                        {String(p.dataKey)}: {String(p.value)}
                      </p>
                    ))}
                    {row?.smallN && (() => {
                      const foldedLabels = [
                        row.financialSmall && "financial",
                        row.proximitySmall && "proximity",
                        row.impartialitySmall && "impartiality",
                      ].filter((v): v is string => Boolean(v));
                      return (
                        <p style={{ color: "var(--text-muted)" }}>
                          {foldedLabels.join(" and ")} count{foldedLabels.length > 1 ? "s" : ""} too
                          small (≤{SMALL_N_FLOOR}) to attribute individually — folded into "other" above.
                        </p>
                      );
                    })()}
                  </div>
                );
              }}
            />
            <Legend />
            <Bar dataKey="impartiality" stackId="a" fill={COLORS.impartiality} name="Impartiality" />
            <Bar dataKey="proximity" stackId="a" fill={COLORS.proximity} name="Proximity" />
            <Bar dataKey="other" stackId="a" fill={COLORS.other} name="Other" />
            <Bar dataKey="financial" stackId="a" fill={COLORS.financial} name="Financial" radius={[0, 2, 2, 0]}>
              {chartData.map((entry, i) => (
                <Cell
                  key={i}
                  fill={entry.financial === maxFinancial && maxFinancial > 0 ? "#dc2626" : COLORS.financial}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="chart-note">
          Financial declarations indicate a direct pecuniary interest — a different category to
          routine impartiality notices. {smallNCount > 0 && (
            <>{smallNCount} councillor{smallNCount === 1 ? "" : "s"} with a financial, proximity, or
            impartiality count of {SMALL_N_FLOOR} or fewer {smallNCount === 1 ? "has" : "have"} that
            category folded into "Other" here rather than shown individually — too small a sample to
            attribute a per-category count to a named person. </>
          )}{smallNRowsExcluded > 0 && (
            <>{smallNRowsExcluded} further councillor{smallNRowsExcluded === 1 ? "" : "s"} with
            {" "}{SMALL_N_FLOOR} or fewer declarations in total {smallNRowsExcluded === 1 ? "is" : "are"} not
            shown by name here at all — too small a sample to attribute any breakdown to one person. </>
          )}Click a name to open that councillor's full profile.
        </p>
      </Reveal>
    </Card>
  );
}

// ── Shared primitives ──────────────────────────────────────────────────────────

export function Card({
  title,
  subtitle,
  valence,
  valenceLabel,
  backTo,
  children,
}: {
  title: string;
  subtitle?: string;
  valence?: "supportive" | "neutral" | "critical";
  valenceLabel?: string;
  backTo?: string; // scorecard row anchor id (e.g. "sc-declared") to link back up
  children: React.ReactNode;
}) {
  return (
    <div className="card">
      <div className="card-header">
        <div className="card-header-titles">
          <h2 className="card-title">{title}</h2>
          {subtitle && <span className="card-subtitle">{subtitle}</span>}
        </div>
        <div className="card-header-meta">
          {backTo && (
            <a className="card-back" href={`#${backTo}`} title="Back to this test on the scorecard">
              ↑ Scorecard
            </a>
          )}
          {valence && <ValenceChip valence={valence} label={valenceLabel} />}
        </div>
      </div>
      {children}
    </div>
  );
}

export function LoadingCard() {
  return (
    <div className="card loading-card">
      <div className="spinner" />
    </div>
  );
}

export function ErrorCard({ msg }: { msg: string | null }) {
  return (
    <div className="card error-card">
      <p>Failed to load: {msg ?? "unknown error"}</p>
    </div>
  );
}
