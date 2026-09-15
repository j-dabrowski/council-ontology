import { useState } from "react";
import {
  ComposedChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceArea,
  BarChart, Bar, Legend, Cell,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, RecusalData, RecusalYearPoint, RecusalDeclarationDetail, EvidenceEntry } from "../api";
import { LoadingCard, ErrorCard } from "./InterestsChart";
import { DrillDown, SourceQuote } from "./DrillDown";
import { CATEGORY_LABEL, type ResolvedTest } from "../registry/types";

const ERA_ORDER = ["pre", "inquiry", "post"] as const;
const TYPE_COLOR: Record<string, string> = {
  financial: "#f87171",    // must leave — mandatory
  proximity: "#fb923c",    // must leave — proximity
  impartiality: "#60a5fa", // may stay and vote
};
const TYPE_LABEL: Record<string, string> = {
  financial: "Financial (must leave)",
  proximity: "Proximity (must leave)",
  impartiality: "Impartiality (may stay)",
};

// Era labels built from this council's own window (data.inquiry_window /
// data.era_label — config/council_eras.json, threaded through recusal.json)
// rather than a hardcoded era name and year range (SECOND_COUNCIL_PLAN.md
// Phase 3.4). Callers must check `data.inquiry_window` is non-null before
// using these — a council with no configured window has nothing to build
// them from.
function eraLabels(inquiryWindow: [number, number], eraLabel: string) {
  const [from, to] = inquiryWindow;
  return {
    short: {
      pre: `Before ${eraLabel}\n(pre-${from})`,
      inquiry: `${eraLabel}\n(${from}–${String(to).slice(-2)})`,
      post: `After ${eraLabel}\n(${to + 1}+)`,
    } as Record<string, string>,
    full: {
      pre: `before the ${eraLabel} (pre-${from})`,
      inquiry: `during the ${eraLabel} (${from}–${String(to).slice(-2)})`,
      post: `after the ${eraLabel} (${to + 1}+)`,
    } as Record<string, string>,
  };
}

// A by-type/by-era cell resting on <=3 declarations isn't a defensible basis
// for naming the individual(s) behind it, regardless of placement behind a
// click — a single misattributed declaration (extraction error) can flip the
// whole picture. Matches ConflictRecusalPanel.tsx / InterestsChart.tsx's own
// SMALL_N_FLOOR. See docs/review, BLOCKING flag, 2026-08-24 pass 2.
const SMALL_N_FLOOR = 3;

function RecusalDeclRow({ d, evidence }: { d: RecusalDeclarationDetail; evidence?: EvidenceEntry }) {
  const left = d.action.startsWith("Stepped");
  return (
    <div className="decl-row">
      <div className="decl-row-head">
        <span className={`decl-type decl-type-${left ? "impartiality" : "financial"}`}>
          {d.action}
        </span>
        <span className="decl-date">
          {d.date}{d.item ? ` · item ${d.item}` : ""}
        </span>
        <span className="decl-action">{d.councillor}</span>
      </div>
      <div className="decl-what">{d.what || <em>no description recorded</em>}</div>
      {evidence ? <SourceQuote entry={evidence} /> : <SourceQuote quote={d.quote} />}
    </div>
  );
}

const YearTooltip = ({ active, payload, label }: {
  active?: boolean;
  payload?: { payload: RecusalYearPoint }[];
  label?: number;
}) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{label}</p>
      <p style={{ color: "var(--stat-g)" }}>
        Stepped out: <strong>{d.must_leave_pct === null ? "—" : `${d.must_leave_pct}%`}</strong>
        {d.must_leave_declared > 0 && (
          <span style={{ color: "var(--text-muted)" }}> ({d.must_leave_recused}/{d.must_leave_declared} serious conflicts)</span>
        )}
      </p>
      <p style={{ color: "var(--note)" }}>
        Votes with a declared interest: <strong>{d.declared_share_pct}%</strong>
      </p>
    </div>
  );
};

const TypeEraTooltip = ({ active, payload, label }: {
  active?: boolean;
  payload?: { name: string; value: number; color: string; payload: Record<string, number> }[];
  label?: string;
}) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{(label || "").replace("\n", " ")}</p>
      {payload.filter((p) => p.value != null).map((p) => {
        const key = p.name;
        const n = payload[0].payload[`${key}_n`];
        return (
          <p key={key} style={{ color: p.color }}>
            {TYPE_LABEL[key] ?? key}: <strong>{p.value}%</strong>
            <span style={{ color: "var(--text-muted)" }}> (n={n})</span>
          </p>
        );
      })}
    </div>
  );
};

export function RecusalTrendPanel({ test }: { test: ResolvedTest }) {
  const { data, loading, error } = useData<RecusalData>(() => api.recusal());
  // The evidence chain, loaded separately: a missing/unpublished evidence
  // file degrades gracefully to each row's legacy `quote` field (see
  // RecusalDeclRow) rather than blocking the panel.
  const { data: evidence } = useData(() => api.evidenceRecusalTrend());
  const [selected, setSelected] = useState<{ era: string; type: string } | null>(null);

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const evidenceById = new Map<number, EvidenceEntry>();
  if (evidence) {
    for (const e of evidence.entries) evidenceById.set(e.entity_id, e);
  }

  const selectedCell = selected
    ? data.by_type_era.find(
        (r) => r.era === selected.era && r.interest_type === selected.type
      ) ?? null
    : null;

  // recharts types the Bar onClick arg without our data fields; read era off it.
  const pickCell = (e: unknown, type: string) => {
    const era = (e as { era?: string })?.era;
    if (era) setSelected({ era, type });
  };

  // Year arc: data densifies from ~2005; plot from 2008 so early single-meeting
  // years don't dominate the axis.
  const yearData = data.by_year.filter((y) => y.year >= 2008);

  // Every era-bucketed figure below (the hero row, the objection callout,
  // the type×era bar chart) is meaningless without a configured scrutiny
  // window — this council's `by_type_era` comes back empty and the pre/
  // inquiry/post percentages are computed off zero rows. Render that whole
  // section only when there's a real window to bucket by (SECOND_COUNCIL_
  // PLAN.md Phase 3.4); the year-by-year chart below stays either way.
  const hasEra = data.inquiry_window != null;
  const window = hasEra ? (data.inquiry_window as [number, number]) : null;
  const labels = hasEra ? eraLabels(window!, data.era_label ?? "scrutiny window") : null;

  // Confound-beater: recusal % by interest type within each era.
  const byTE: Record<string, Record<string, number>> = {
    pre: {}, inquiry: {}, post: {},
  };
  for (const r of data.by_type_era) {
    if (!byTE[r.era]) continue;
    byTE[r.era][r.interest_type] = r.recusal_pct;
    byTE[r.era][`${r.interest_type}_n`] = r.declared;
  }
  const typeEraData = labels ? ERA_ORDER.map((era) => ({
    era,
    eraLabel: labels.short[era],
    financial: byTE[era].financial ?? null,
    proximity: byTE[era].proximity ?? null,
    impartiality: byTE[era].impartiality ?? null,
    financial_n: byTE[era].financial_n ?? 0,
    proximity_n: byTE[era].proximity_n ?? 0,
    impartiality_n: byTE[era].impartiality_n ?? 0,
  })) : [];

  return (
    <>
      {hasEra && (
        <>
          <div className="planning-hero-row">
            <div className="planning-stat">
              <span className="planning-stat-num planning-stat-recent">{data.must_leave_inquiry_pct}%</span>
              <span className="planning-stat-label">stepped out during the {data.era_label} ({window![0]}–{window![1]})</span>
            </div>
            <div className="planning-stat-arrow">→</div>
            <div className="planning-stat">
              <span className="planning-stat-num planning-stat-peak">{data.must_leave_post_pct}%</span>
              <span className="planning-stat-label">stepped out afterwards ({window![1] + 1}+)</span>
            </div>
            <div className="planning-stat-divider" />
            <div className="planning-stat">
              <span className="planning-stat-num">{data.impartiality_post_recusal_pct}%</span>
              <span className="planning-stat-label">
                recusal on the {data.impartiality_post_declared} post-{window![1] + 1} "impartiality" declarations
              </span>
            </div>
          </div>

          <div className="objection-callout">
            <span className="objection-callout-diff">
              {data.financial_inquiry_pct}%→{data.financial_post_pct}%
            </span>
            <span className="objection-callout-text">
              Even on <strong>financial conflicts</strong> — where the law <em>requires</em> a member to
              leave the room — recusal held at <strong>{data.financial_inquiry_pct}%</strong> during the
              {" "}{data.era_label} and <strong>{data.financial_post_pct}%</strong> after it.
              {data.financial_post_n <= 3 && (
                <> The only post-{window![1] + 1} financial-conflict declaration(s) on record
                  {" "}(n={data.financial_post_n}) are too few to assess a trend either way on
                  financial conflicts alone.</>
              )}
            </span>
          </div>
        </>
      )}

      <p className="section-heading">
        Stepping out vs. declaring, year by year — serious conflicts only
      </p>
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={yearData} margin={{ top: 8, right: 36, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} interval={1} />
          <YAxis yAxisId="L" unit="%" domain={[0, 100]} tick={{ fontSize: 11 }} width={40} />
          <YAxis yAxisId="R" orientation="right" unit="%" domain={[0, 14]}
            tick={{ fontSize: 11 }} width={36} />
          {hasEra && (
            <ReferenceArea yAxisId="L" x1={window![0]} x2={window![1]} fill="#f59e0b" fillOpacity={0.08}
              label={{ value: data.era_label ?? undefined, position: "insideTop", fontSize: 10, fill: "#f59e0b" }} />
          )}
          <Tooltip content={<YearTooltip />} />
          <Line yAxisId="L" type="monotone" dataKey="must_leave_pct" stroke="#22c55e"
            strokeWidth={2.5} connectNulls={false} name="Stepped out %"
            dot={{ r: 2.5, fill: "#22c55e" }} activeDot={{ r: 5 }} />
          <Line yAxisId="R" type="monotone" dataKey="declared_share_pct" stroke="#f59e0b"
            strokeWidth={1.8} strokeDasharray="5 3" connectNulls name="Votes w/ declared interest %"
            dot={false} activeDot={{ r: 4 }} />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Green (left axis) = share of <em>serious</em> (financial or proximity) declared conflicts where the
        councillor recorded ABSENT — i.e. left the room. Amber (right axis, dashed) = declared-interest
        votes as a share of all votes. Years with fewer than 4 serious conflicts are left as gaps.
      </p>

      {hasEra && (
        <>
          <p className="section-heading">
            Beating the obvious objection: recusal fell <em>within</em> every interest type
            <span className="section-hint"> · click a bar to see the declarations behind it</span>
          </p>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={typeEraData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="eraLabel" tick={{ fontSize: 10 }} interval={0} />
              <YAxis unit="%" domain={[0, 100]} tick={{ fontSize: 11 }} width={40} />
              <Tooltip content={<TypeEraTooltip />} cursor={{ fill: "var(--cursor)" }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="financial" name="financial" fill={TYPE_COLOR.financial} radius={[3, 3, 0, 0]}
                cursor="pointer" onClick={(e) => pickCell(e, "financial")}>
                {typeEraData.map((e, i) => <Cell key={i} fillOpacity={e.financial_n < 20 ? 0.45 : 1} />)}
              </Bar>
              <Bar dataKey="proximity" name="proximity" fill={TYPE_COLOR.proximity} radius={[3, 3, 0, 0]}
                cursor="pointer" onClick={(e) => pickCell(e, "proximity")}>
                {typeEraData.map((e, i) => <Cell key={i} fillOpacity={e.proximity_n < 20 ? 0.45 : 1} />)}
              </Bar>
              <Bar dataKey="impartiality" name="impartiality" fill={TYPE_COLOR.impartiality} radius={[3, 3, 0, 0]}
                cursor="pointer" onClick={(e) => pickCell(e, "impartiality")} />
            </BarChart>
          </ResponsiveContainer>

          {selectedCell && (
            <DrillDown
              title={`${TYPE_LABEL[selectedCell.interest_type] ?? selectedCell.interest_type} — ${labels!.full[selectedCell.era] ?? selectedCell.era}`}
              subtitle={`stepped out on ${selectedCell.recused}/${selectedCell.declared} (${selectedCell.recusal_pct}%)${selectedCell.n_shown < selectedCell.declared ? ` · showing ${selectedCell.n_shown} most recent` : ""}`}
              onClose={() => setSelected(null)}
            >
              {selectedCell.declarations.length === 0 && (
                <p className="chart-note">No itemised declarations behind this cell.</p>
              )}
              {selectedCell.declarations.length > 0 && selectedCell.declared <= SMALL_N_FLOOR && (
                <p className="chart-note">
                  n too small to name individual declarations — shown at aggregate level only
                  ({selectedCell.declared} on record, {SMALL_N_FLOOR} or fewer).
                </p>
              )}
              {selectedCell.declarations.length > 0 && selectedCell.declared > SMALL_N_FLOOR && (
                selectedCell.declarations.map((d, i) => (
                  <RecusalDeclRow key={i} d={d}
                    evidence={d.entity_id != null ? evidenceById.get(d.entity_id) : undefined} />
                ))
              )}
            </DrillDown>
          )}

          <p className="chart-note">
            Faded bars are n&lt;20 (directional). Must-leave totals: pre {data.must_leave_pre_n},{" "}
            {data.era_label} {data.must_leave_inquiry_n}, post {data.must_leave_post_n}.
            Declaration→vote matched at item level (item reference ↔ agenda item).
          </p>
        </>
      )}
      <p className="chart-note bt-meta">
        <span className="sc-genre">{CATEGORY_LABEL[test.category]}</span>
        {" · "}{test.principles.join(" · ")}
        {" · "}{test.question_technical}
      </p>
    </>
  );
}
