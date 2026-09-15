import { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid
} from "recharts";
import { useData } from "../hooks/useData";
import { api, EvidenceEntry } from "../api";
import { useCorpusSpan } from "../councils";
import { LoadingCard, ErrorCard } from "./InterestsChart";
import { DrillDown, SourceQuote } from "./DrillDown";
import { CATEGORY_LABEL, type ResolvedTest } from "../registry/types";

const ITEM_LABEL: Record<string, string> = {
  public_questions: "Public question",
  deputations: "Deputation",
  petitions: "Petition",
};

function EngagementItemRow({ entry }: { entry: EvidenceEntry }) {
  return (
    <div className="decl-row">
      <div className="decl-row-head">
        <span className="decl-type decl-type-other">
          {ITEM_LABEL[entry.entity_table] ?? entry.entity_table}
        </span>
        <span className="decl-date">{entry.meeting_date ?? ""}</span>
      </div>
      <SourceQuote entry={entry} />
    </div>
  );
}

export function EngagementChart({ test }: { test: ResolvedTest }) {
  const { data, loading, error } = useData(() => api.engagement());
  // The evidence chain, loaded separately: this panel had no drill-down at
  // all before, so a missing/unpublished evidence file just means clicking
  // a bar does nothing, rather than blocking the chart itself.
  const { data: evidence } = useData(() => api.evidenceParticipation());
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const span = useCorpusSpan();

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const itemsByYear = new Map<number, EvidenceEntry[]>();
  if (evidence) {
    for (const y of evidence.years) itemsByYear.set(y.year, y.items);
  }

  const chartData = data.map((d) => ({
    year: d.year,
    "Public questions": d.public_questions,
    "Deputations": d.deputations,
    "Petitions": d.petitions,
  }));

  const selectedItems = selectedYear != null ? itemsByYear.get(selectedYear) ?? [] : [];

  // recharts types a Bar's onClick payload as BarRectangleItem (payload?: any),
  // not the row shape directly — the actual data row lives at .payload.
  const pickYear = (item: { payload?: { year?: number } }) => {
    const year = item?.payload?.year;
    if (year != null) setSelectedYear(year);
  };

  return (
    <>
      <ResponsiveContainer width="100%" height={340}>
        <BarChart data={chartData} margin={{ top: 8, right: 24, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="year" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6 }}
            labelStyle={{ color: "#f1f5f9" }}
          />
          <Legend />
          <Bar dataKey="Public questions" fill="#3b82f6" radius={[3, 3, 0, 0]} cursor="pointer"
            onClick={pickYear} />
          <Bar dataKey="Deputations" fill="#8b5cf6" radius={[3, 3, 0, 0]} cursor="pointer"
            onClick={pickYear} />
          <Bar dataKey="Petitions" fill="#ec4899" radius={[3, 3, 0, 0]} cursor="pointer"
            onClick={pickYear} />
        </BarChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Public engagement across the full corpus{span ? ` (${span})` : ""}.
        <span className="section-hint"> · click a bar to see that year's questions, deputations and petitions</span>
      </p>

      {selectedYear != null && (
        <DrillDown
          title={`${selectedYear} — public engagement`}
          subtitle={`${selectedItems.length} item(s) shown, newest first`}
          onClose={() => setSelectedYear(null)}
        >
          {selectedItems.length === 0 && (
            <p className="chart-note">No itemised engagement extracted for this year.</p>
          )}
          {selectedItems.map((entry, i) => (
            <EngagementItemRow key={i} entry={entry} />
          ))}
        </DrillDown>
      )}

      <p className="chart-note bt-meta">
        <span className="sc-genre">{CATEGORY_LABEL[test.category]}</span>
        {" · "}{test.principles.join(" · ")}
        {" · "}{test.question_technical}
      </p>
    </>
  );
}
