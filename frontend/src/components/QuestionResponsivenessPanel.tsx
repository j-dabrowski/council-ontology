import { useState } from "react";
import {
  ComposedChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceArea,
  BarChart, Bar, Cell,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, QuestionResponsivenessData, PQResponseDetail, PQYearPoint, EvidenceEntry } from "../api";
import { LoadingCard } from "./InterestsChart";
import { BatteryTestBody } from "./BatteryTestPanel";
import { DrillDown, SourceQuote } from "./DrillDown";
import { CATEGORY_LABEL, type ResolvedTest } from "../registry/types";
import { Principles } from "./Glossary";

const ERA_ORDER = ["pre", "inquiry", "post"] as const;

// Era labels built from this council's own window (data.inquiry_window /
// data.era_label — config/council_eras.json, threaded through question-
// responsiveness.json) rather than a hardcoded era name and year range
// (SECOND_COUNCIL_PLAN.md Phase 3.4). Callers must check
// `data.inquiry_window` is non-null first.
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

function PQRow({ q, evidence }: { q: PQResponseDetail; evidence?: EvidenceEntry }) {
  const deferred = q.status.startsWith("Taken");
  return (
    <div className="decl-row">
      <div className="decl-row-head">
        <span className={`decl-type decl-type-${deferred ? "financial" : "impartiality"}`}>
          {q.status}
        </span>
        <span className="decl-date">{q.date}</span>
        <span className="decl-action">
          {q.questioner || "public questioner"}
          {q.fielded_by ? ` · fielded by ${q.fielded_by}` : ""}
        </span>
      </div>
      <div className="decl-what">{q.question || <em>no question summary recorded</em>}</div>
      {evidence ? <SourceQuote entry={evidence} /> : <SourceQuote quote={q.quote} />}
    </div>
  );
}

const YearTooltip = ({ active, payload, label }: {
  active?: boolean;
  payload?: { payload: PQYearPoint }[];
  label?: number;
}) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{label}</p>
      <p style={{ color: "var(--stat-r, #f87171)" }}>
        Taken on notice: <strong>{d.on_notice_pct === null ? "—" : `${d.on_notice_pct}%`}</strong>
        <span style={{ color: "var(--text-muted)" }}> ({d.on_notice}/{d.n_nonblank} questions)</span>
      </p>
    </div>
  );
};

const EraTooltip = ({ active, payload, label }: {
  active?: boolean;
  payload?: { value: number; payload: { on_notice: number; nb: number } }[];
  label?: string;
}) => {
  if (!active || !payload?.length) return null;
  const p = payload[0];
  return (
    <div className="tooltip">
      <p className="tooltip-title">{(label || "").replace("\n", " ")}</p>
      <p style={{ color: "#f87171" }}>
        Deferred: <strong>{p.value}%</strong>
        <span style={{ color: "var(--text-muted)" }}> ({p.payload.on_notice}/{p.payload.nb})</span>
      </p>
    </div>
  );
};

export function QuestionResponsivenessPanel({ test }: { test: ResolvedTest }) {
  const { data, loading, error } = useData<QuestionResponsivenessData>(
    () => api.questionResponsiveness());
  // The evidence chain, loaded separately: a missing/unpublished evidence
  // file degrades gracefully to each row's legacy `quote` field (see PQRow)
  // rather than blocking the panel.
  const { data: evidence } = useData(() => api.evidenceQuestionResponsiveness());
  const [selectedEra, setSelectedEra] = useState<string | null>(null);

  if (loading) return <LoadingCard />;
  if (error || !data) return <BatteryTestBody test={test} cllrData={null} />;

  const evidenceById = new Map<number, EvidenceEntry>();
  if (evidence) {
    for (const e of evidence.entries) evidenceById.set(e.entity_id, e);
  }

  // year arc: from 1997 (first years are tiny); plot only rate-eligible points
  const yearData = data.by_year.filter((y) => y.year >= 1997);

  // Every era-bucketed figure below (the hero row, the objection callout,
  // the deferral-by-era bar chart) needs a configured scrutiny window to
  // mean anything — render that whole section only when there is one
  // (SECOND_COUNCIL_PLAN.md Phase 3.4); the year-by-year chart stays either way.
  const hasEra = data.inquiry_window != null;
  const window = hasEra ? (data.inquiry_window as [number, number]) : null;
  const labels = hasEra ? eraLabels(window!, data.era_label ?? "scrutiny window") : null;

  const eraByKey = Object.fromEntries(data.by_era.map((e) => [e.era, e]));
  const eraData = labels ? ERA_ORDER.map((era) => {
    const e = eraByKey[era];
    return {
      era,
      eraLabel: labels.short[era],
      on_notice_pct: e?.on_notice_pct ?? 0,
      on_notice: e?.on_notice ?? 0,
      nb: (e?.answered ?? 0) + (e?.on_notice ?? 0),
    };
  }) : [];

  const selectedCell = selectedEra ? eraByKey[selectedEra] : null;

  const pickEra = (e: unknown) => {
    const era = (e as { era?: string })?.era;
    if (era) setSelectedEra(era);
  };

  return (
    <>
      {hasEra && (
        <>
          <div className="planning-hero-row">
            <div className="planning-stat">
              <span className="planning-stat-num">{data.pre_pct}%</span>
              <span className="planning-stat-label">deferred before the {data.era_label} (pre-{window![0]})</span>
            </div>
            <div className="planning-stat-arrow">→</div>
            <div className="planning-stat">
              <span className="planning-stat-num planning-stat-peak">{data.inquiry_pct}%</span>
              <span className="planning-stat-label">deferred during the {data.era_label} ({window![0]}–{window![1]})</span>
            </div>
            <div className="planning-stat-arrow">→</div>
            <div className="planning-stat">
              <span className="planning-stat-num planning-stat-recent">{data.post_pct}%</span>
              <span className="planning-stat-label">deferred afterwards ({window![1] + 1}+)</span>
            </div>
            <div className="planning-stat-divider" />
            <div className="planning-stat">
              <span className="planning-stat-num">{data.answered_pct}%</span>
              <span className="planning-stat-label">answered in the meeting overall ({data.total.toLocaleString()} questions)</span>
            </div>
          </div>

          <div className="objection-callout">
            <span className="objection-callout-diff">{data.pre_pct}%→{data.inquiry_pct}%</span>
            <span className="objection-callout-text">
              The share of public questions <strong>"taken on notice"</strong> rather than answered live
              changed when this council came under its {data.era_label}
              {data.peak_year != null && <> , peaking at <strong>{data.peak_pct}% in {data.peak_year}</strong></>}
              , against a post-window rate of <strong>{data.post_pct}%</strong>. Most questions are still
              answered in the room — this tracks whether live accountability shifted under scrutiny.
            </span>
          </div>
        </>
      )}

      <p className="section-heading">
        Questions "taken on notice", year by year
      </p>
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={yearData} margin={{ top: 8, right: 24, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} interval={2} />
          <YAxis unit="%" domain={[0, 30]} tick={{ fontSize: 11 }} width={40} />
          {hasEra && (
            <ReferenceArea x1={window![0]} x2={window![1]} fill="#f59e0b" fillOpacity={0.08}
              label={{ value: data.era_label ?? undefined, position: "insideTop", fontSize: 10, fill: "#f59e0b" }} />
          )}
          <Tooltip content={<YearTooltip />} />
          <Line type="monotone" dataKey="on_notice_pct" stroke="#f87171"
            strokeWidth={2.5} connectNulls={false} name="Taken on notice %"
            dot={{ r: 2.5, fill: "#f87171" }} activeDot={{ r: 5 }} />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Red = share of that year's public questions recorded as deferred / "taken on notice" rather than
        answered in the meeting (of questions with a recorded response). Years with fewer than 15 such
        questions are left as gaps. The classifier counts a question as "answered" unless the minutes
        clearly mark it deferred, so this is a <em>floor</em> on the true deferral rate.
      </p>

      {hasEra && (
        <>
          <p className="section-heading">
            Deferral rate by era
            <span className="section-hint"> · click a bar to read the questions behind it</span>
          </p>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={eraData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="eraLabel" tick={{ fontSize: 10 }} interval={0} />
              <YAxis unit="%" domain={[0, 20]} tick={{ fontSize: 11 }} width={40} />
              <Tooltip content={<EraTooltip />} cursor={{ fill: "var(--cursor)" }} />
              <Bar dataKey="on_notice_pct" name="deferred" radius={[3, 3, 0, 0]}
                cursor="pointer" onClick={pickEra}>
                {eraData.map((e, i) => (
                  <Cell key={i} fill={e.era === "inquiry" ? "#f87171" : "#fb923c"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          {selectedCell && (
            <DrillDown
              title={`Public questions ${labels!.full[selectedCell.era] ?? selectedCell.era}`}
              subtitle={`${selectedCell.on_notice}/${(selectedCell.answered + selectedCell.on_notice)} deferred (${selectedCell.on_notice_pct}%)${selectedCell.n_shown < selectedCell.on_notice ? ` · showing ${selectedCell.n_shown}` : ""} · deferred first, then answered examples`}
              onClose={() => setSelectedEra(null)}
            >
              {selectedCell.questions.length === 0 && (
                <p className="chart-note">No itemised questions behind this era.</p>
              )}
              {selectedCell.questions.map((q, i) => (
                <PQRow key={i} q={q}
                  evidence={q.entity_id != null ? evidenceById.get(q.entity_id) : undefined} />
              ))}
            </DrillDown>
          )}
        </>
      )}

      <p className="chart-note bt-meta">
        <span className="sc-genre">{CATEGORY_LABEL[test.category]}</span>
        <Principles list={test.principles} />
        {" · "}{test.question_technical}
      </p>
    </>
  );
}
