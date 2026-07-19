import { useState } from "react";
import {
  ComposedChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceArea,
  BarChart, Bar, Cell,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, QuestionResponsivenessData, PQResponseDetail, PQYearPoint } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";
import { DrillDown, SourceQuote } from "./DrillDown";

const ERA_ORDER = ["pre", "inquiry", "post"] as const;
const ERA_LABEL: Record<string, string> = {
  pre: "Before Inquiry\n(pre-2018)",
  inquiry: "Inquiry\n(2018–21)",
  post: "After Inquiry\n(2022+)",
};
const ERA_FULL: Record<string, string> = {
  pre: "before the Inquiry (pre-2018)",
  inquiry: "during the Inquiry (2018–21)",
  post: "after the Inquiry (2022+)",
};

function PQRow({ q }: { q: PQResponseDetail }) {
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
      <SourceQuote quote={q.quote} />
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

export function QuestionResponsivenessPanel() {
  const { data, loading, error } = useData<QuestionResponsivenessData>(
    () => api.questionResponsiveness());
  const [selectedEra, setSelectedEra] = useState<string | null>(null);

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  // year arc: from 1997 (first years are tiny); plot only rate-eligible points
  const yearData = data.by_year.filter((y) => y.year >= 1997);

  const eraByKey = Object.fromEntries(data.by_era.map((e) => [e.era, e]));
  const eraData = ERA_ORDER.map((era) => {
    const e = eraByKey[era];
    return {
      era,
      eraLabel: ERA_LABEL[era],
      on_notice_pct: e?.on_notice_pct ?? 0,
      on_notice: e?.on_notice ?? 0,
      nb: (e?.answered ?? 0) + (e?.on_notice ?? 0),
    };
  });

  const selectedCell = selectedEra ? eraByKey[selectedEra] : null;

  const pickEra = (e: unknown) => {
    const era = (e as { era?: string })?.era;
    if (era) setSelectedEra(era);
  };

  return (
    <Card
      title="Answered in the Room — or Quietly Taken on Notice?"
      subtitle="Are residents' public questions answered in the meeting, or deferred? · 1995–2026"
      valence="critical"
      backTo="sc-question-responsiveness"
    >
      <div className="planning-hero-row">
        <div className="planning-stat">
          <span className="planning-stat-num">{data.pre_pct}%</span>
          <span className="planning-stat-label">deferred before the Inquiry (pre-2018)</span>
        </div>
        <div className="planning-stat-arrow">→</div>
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-peak">{data.inquiry_pct}%</span>
          <span className="planning-stat-label">deferred during the Inquiry (2018–21)</span>
        </div>
        <div className="planning-stat-arrow">→</div>
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-recent">{data.post_pct}%</span>
          <span className="planning-stat-label">deferred afterwards (2022+)</span>
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
          roughly <strong>tripled</strong> when Cambridge came under its state-appointed Authorised
          Inquiry, peaking at <strong>{data.peak_pct}% in {data.peak_year}</strong>, and never returned
          to its pre-2018 baseline ({data.post_pct}% after). Most questions are still answered in the
          room — but live accountability measurably dipped under scrutiny and stayed down.
        </span>
      </div>

      <p className="section-heading">
        Questions "taken on notice", year by year
      </p>
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={yearData} margin={{ top: 8, right: 24, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} interval={2} />
          <YAxis unit="%" domain={[0, 30]} tick={{ fontSize: 11 }} width={40} />
          <ReferenceArea x1={2018} x2={2021} fill="#f59e0b" fillOpacity={0.08}
            label={{ value: "Authorised Inquiry", position: "insideTop", fontSize: 10, fill: "#f59e0b" }} />
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
        clearly mark it deferred, so this is a <em>floor</em> on the true deferral rate. 2026 is a part-year.
      </p>

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
          title={`Public questions ${ERA_FULL[selectedCell.era] ?? selectedCell.era}`}
          subtitle={`${selectedCell.on_notice}/${(selectedCell.answered + selectedCell.on_notice)} deferred (${selectedCell.on_notice_pct}%)${selectedCell.n_shown < selectedCell.on_notice ? ` · showing ${selectedCell.n_shown}` : ""} · deferred first, then answered examples`}
          onClose={() => setSelectedEra(null)}
        >
          {selectedCell.questions.length === 0 && (
            <p className="chart-note">No itemised questions behind this era.</p>
          )}
          {selectedCell.questions.map((q, i) => <PQRow key={i} q={q} />)}
        </DrillDown>
      )}

      <p className="chart-note">
        A hostile reader would say: "nine in ten questions are still answered — there's no problem."
        The relevant number is the <em>shift</em>: deferral tripled ({data.pre_pct}%→{data.inquiry_pct}%)
        exactly when the council was under inquiry and never returned to baseline
        ({data.post_pct}% after), and the measure understates it. A councillor's defender would answer:
        "2020 was COVID — meetings went remote and detailed questions were reasonably answered in
        writing." The data concedes the {data.peak_year} peak is partly a remote-meeting artefact — but
        the rise began in 2018–19 <em>before</em> COVID and persisted through 2022–2025 after it, so the
        Inquiry-era caution, not the pandemic alone, carries the trend. "On notice" is lawful and often
        appropriate for complex questions, so this is a responsiveness concern (CIPFA-B), not impropriety.
      </p>
    </Card>
  );
}
