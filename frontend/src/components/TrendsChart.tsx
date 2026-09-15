import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend
} from "recharts";
import { useData } from "../hooks/useData";
import { api, CouncillorsData } from "../api";
import { useCorpusSpan } from "../councils";
import { LoadingCard, ErrorCard } from "./InterestsChart";
import { Reveal } from "./DrillDown";
import { RedactedText } from "../guardrail";
import { CATEGORY_LABEL, type ResolvedTest } from "../registry/types";

export function ContestationChart({ test }: { test: ResolvedTest }) {
  const { data, loading, error } = useData(() => api.trends());
  const span = useCorpusSpan();
  // most_contested is a motion title — free text, computed per run, not a
  // registry-authored string — so it goes through the same guardrail every
  // other computed claim field does (ScorecardPanel/BatteryTestPanel):
  // a councillor's surname can land in a title ("Motion for Cr Pinerua")
  // with no other check catching it before render.
  const { data: cllrData } = useData<CouncillorsData>(() => api.councillors());
  const councillorNames = cllrData ? Object.keys(cllrData.by_name) : [];

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const chartData = data.contestation.map((r) => ({
    year: r.year,
    "Contestation %": +(r.contestation_rate * 100).toFixed(1),
    "Total motions": r.total_carried,
  }));

  return (
    <>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData} margin={{ top: 8, right: 24, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="year" tick={{ fontSize: 12 }} />
          <YAxis yAxisId="left" unit="%" tick={{ fontSize: 12 }} domain={[0, 20]} />
          <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12 }} />
          <Tooltip
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6 }}
            labelStyle={{ color: "#f1f5f9" }}
          />
          <Legend />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="Contestation %"
            stroke="#f59e0b"
            strokeWidth={2}
            dot={{ r: 5 }}
          />
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="Total motions"
            stroke="#64748b"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Contestation rate across the full corpus{span ? ` (${span})` : ""}.
      </p>
      <Reveal label="see the most contested motion per year">
        <h3 className="section-heading" style={{ marginTop: 12 }}>Most contested motion per year</h3>
        <div className="contested-list">
          {data.contestation.map((r) => (
            <div key={r.year} className="contested-row">
              <span className="contested-year">{r.year}</span>
              <span className="contested-title">
                {r.most_contested[0] ? (
                  <>
                    <RedactedText
                      text={r.most_contested[0]}
                      names={councillorNames}
                      testId={test.id}
                      field="most_contested"
                    />
                    <span style={{ color: "var(--text-muted)" }}>
                      {" "}({r.total_with_dissent} of {r.total_carried} motions had any dissent that year)
                    </span>
                  </>
                ) : "—"}
              </span>
            </div>
          ))}
        </div>
      </Reveal>
      <p className="chart-note bt-meta">
        <span className="sc-genre">{CATEGORY_LABEL[test.category]}</span>
        {" · "}{test.principles.join(" · ")}
        {" · "}{test.question_technical}
      </p>
    </>
  );
}
