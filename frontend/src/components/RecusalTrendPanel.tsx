import {
  ComposedChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceArea,
  BarChart, Bar, Legend, Cell,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, RecusalData, RecusalYearPoint } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";

const ERA_ORDER = ["pre", "inquiry", "post"] as const;
const ERA_LABEL: Record<string, string> = {
  pre: "Before Inquiry\n(pre-2018)",
  inquiry: "Inquiry\n(2018–21)",
  post: "After Inquiry\n(2022+)",
};
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
      <p style={{ color: "#22c55e" }}>
        Stepped out: <strong>{d.must_leave_pct === null ? "—" : `${d.must_leave_pct}%`}</strong>
        {d.must_leave_declared > 0 && (
          <span style={{ color: "#94a3b8" }}> ({d.must_leave_recused}/{d.must_leave_declared} serious conflicts)</span>
        )}
      </p>
      <p style={{ color: "#f59e0b" }}>
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
            <span style={{ color: "#94a3b8" }}> (n={n})</span>
          </p>
        );
      })}
    </div>
  );
};

export function RecusalTrendPanel() {
  const { data, loading, error } = useData<RecusalData>(() => api.recusal());

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  // Year arc: data densifies from ~2005; plot from 2008 so early single-meeting
  // years don't dominate the axis.
  const yearData = data.by_year.filter((y) => y.year >= 2008);

  // Confound-beater: recusal % by interest type within each era.
  const byTE: Record<string, Record<string, number>> = {
    pre: {}, inquiry: {}, post: {},
  };
  for (const r of data.by_type_era) {
    if (!byTE[r.era]) continue;
    byTE[r.era][r.interest_type] = r.recusal_pct;
    byTE[r.era][`${r.interest_type}_n`] = r.declared;
  }
  const typeEraData = ERA_ORDER.map((era) => ({
    era,
    eraLabel: ERA_LABEL[era],
    financial: byTE[era].financial ?? null,
    proximity: byTE[era].proximity ?? null,
    impartiality: byTE[era].impartiality ?? null,
    financial_n: byTE[era].financial_n ?? 0,
    proximity_n: byTE[era].proximity_n ?? 0,
    impartiality_n: byTE[era].impartiality_n ?? 0,
  }));

  const topDriver = data.drivers[0];

  return (
    <Card
      title="Declared, Then Stayed — the Quiet Collapse of Recusal"
      subtitle="Did declaring a conflict still mean leaving the room? · serious (financial/proximity) interests, 1995–2026"
    >
      <div className="planning-hero-row">
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-recent">{data.must_leave_inquiry_pct}%</span>
          <span className="planning-stat-label">stepped out during the Inquiry (2018–21)</span>
        </div>
        <div className="planning-stat-arrow">→</div>
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-peak">{data.must_leave_post_pct}%</span>
          <span className="planning-stat-label">stepped out afterwards (2022+)</span>
        </div>
        <div className="planning-stat-divider" />
        <div className="planning-stat">
          <span className="planning-stat-num">{data.impartiality_post_recusal_pct}%</span>
          <span className="planning-stat-label">
            recusal on the {data.impartiality_post_declared} post-2022 "impartiality" declarations
          </span>
        </div>
      </div>

      <div className="objection-callout">
        <span className="objection-callout-diff">
          {data.financial_inquiry_pct}%→{data.financial_post_pct}%
        </span>
        <span className="objection-callout-text">
          The fall isn't just a shift to softer interests. Even on <strong>financial conflicts</strong> —
          where the law <em>requires</em> a member to leave the room — recusal dropped from{" "}
          <strong>{data.financial_inquiry_pct}%</strong> during the state-appointed Authorised Inquiry to{" "}
          <strong>{data.financial_post_pct}%</strong> after it
          (n={data.financial_post_n}, directional). Compliance tightened while Cambridge was under
          scrutiny, then let go once the inquiry lifted.
        </span>
      </div>

      <p className="section-heading">
        Stepping out vs. declaring, year by year — serious conflicts only
      </p>
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={yearData} margin={{ top: 8, right: 36, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} interval={1} />
          <YAxis yAxisId="L" unit="%" domain={[0, 100]} tick={{ fontSize: 11 }} width={40} />
          <YAxis yAxisId="R" orientation="right" unit="%" domain={[0, 14]}
            tick={{ fontSize: 11 }} width={36} />
          <ReferenceArea yAxisId="L" x1={2018} x2={2021} fill="#f59e0b" fillOpacity={0.08}
            label={{ value: "Authorised Inquiry", position: "insideTop", fontSize: 10, fill: "#f59e0b" }} />
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
        votes as a share of all votes. The two diverge sharply: declarations rose roughly five-fold while
        stepping-out fell away. Years with fewer than 4 serious conflicts are left as gaps. 2026 is a
        part-year.
      </p>

      <p className="section-heading">
        Beating the obvious objection: recusal fell <em>within</em> every interest type
      </p>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={typeEraData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
          <XAxis dataKey="eraLabel" tick={{ fontSize: 10 }} interval={0} />
          <YAxis unit="%" domain={[0, 100]} tick={{ fontSize: 11 }} width={40} />
          <Tooltip content={<TypeEraTooltip />} cursor={{ fill: "#1e293b55" }} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="financial" name="financial" fill={TYPE_COLOR.financial} radius={[3, 3, 0, 0]}>
            {typeEraData.map((e, i) => <Cell key={i} fillOpacity={e.financial_n < 20 ? 0.45 : 1} />)}
          </Bar>
          <Bar dataKey="proximity" name="proximity" fill={TYPE_COLOR.proximity} radius={[3, 3, 0, 0]}>
            {typeEraData.map((e, i) => <Cell key={i} fillOpacity={e.proximity_n < 20 ? 0.45 : 1} />)}
          </Bar>
          <Bar dataKey="impartiality" name="impartiality" fill={TYPE_COLOR.impartiality} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <p className="chart-note">
        A hostile reader would say: "recusal fell only because declarations shifted to <em>impartiality</em>
        interests, where the law lets you stay and vote." True in part — impartiality declarations did
        balloon. But the collapse shows up <em>within</em> the must-leave categories too: financial recusal
        {" "}went {data.financial_inquiry_pct}% → {data.financial_post_pct}%
        and proximity fell after the Inquiry as well. Faded bars are n&lt;20 (directional). Must-leave totals:
        pre {data.must_leave_pre_n}, Inquiry {data.must_leave_inquiry_n}, post {data.must_leave_post_n}.
        {topDriver && (
          <> Post-2022, the most frequent stay-and-vote on a serious conflict is{" "}
          <strong>{topDriver.name}</strong> ({topDriver.stayed}/{topDriver.total}).</>
        )}
        {" "}Declaration→vote matched at item level (item reference ↔ agenda item).
      </p>
    </Card>
  );
}
