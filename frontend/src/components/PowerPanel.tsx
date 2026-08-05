import { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  Cell, LabelList, ReferenceLine, ScatterChart, Scatter, ZAxis,
  LineChart, Line, Legend,
} from "recharts";
import { useData } from "../hooks/useData";
import { api, PowerProfile, ContestedVoteDetail } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";
import { DrillDown, SourceQuote } from "./DrillDown";
import { CouncillorLink, CouncillorTick } from "./CouncillorModal";

const pct = (v: number) => `${Math.round(v * 100)}%`;

function ContestedVoteRow({ v }: { v: ContestedVoteDetail }) {
  return (
    <div className="decl-row">
      <div className="decl-row-head">
        <span className={`decl-type decl-type-${v.won ? "impartiality" : "financial"}`}>
          Voted {v.choice} · {v.outcome}
        </span>
        <span className="decl-date">
          {v.date}{v.item ? ` · item ${v.item}` : ""}
        </span>
        <span className="decl-action">
          {v.won ? "on the winning side" : "outvoted"}
          {v.margin !== null ? ` · ${v.margin > 0 ? "+" : ""}${v.margin}` : ""}
        </span>
      </div>
      <div className="decl-title">{v.title || <em>untitled motion</em>}</div>
      <SourceQuote quote={v.quote} />
    </div>
  );
}

const LINE_COLORS = ["#60a5fa", "#f59e0b", "#22c55e", "#f87171", "#8b5cf6", "#e879f9"];

const WinTooltip = ({ active, payload }: {
  active?: boolean; payload?: { payload: PowerProfile }[];
}) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{d.name}{d.is_active ? " ●" : ""}</p>
      <p style={{ color: "var(--link)" }}>on the winning side <strong>{pct(d.win_rate)}</strong> of {d.n} contested votes</p>
      <p style={{ color: "var(--text-muted)" }}>
        votes AGAINST {pct(d.dissent_rate)} of the time
        {d.dissent_effectiveness !== null && <> · those objections prevail <strong>{pct(d.dissent_effectiveness)}</strong></>}
      </p>
    </div>
  );
};

const ScatterTooltip = ({ active, payload }: {
  active?: boolean; payload?: { payload: PowerProfile }[];
}) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="tooltip">
      <p className="tooltip-title">{d.name}</p>
      <p style={{ color: "var(--text-muted)" }}>dissents on <strong>{pct(d.dissent_rate)}</strong> of contested votes ({d.dissent_n})</p>
      <p style={{ color: (d.dissent_effectiveness ?? 0) >= 0.241 ? "#22c55e" : "#f87171" }}>
        of those, <strong>{pct(d.dissent_effectiveness ?? 0)}</strong> succeed (motion lost)
      </p>
    </div>
  );
};

export function PowerPanel() {
  const { data, loading, error } = useData(() => api.power());
  const [selected, setSelected] = useState<string | null>(null);

  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const selectedProfile = selected
    ? data.profiles.find((p) => p.name === selected) ?? null
    : null;

  const carry = data.base_carry_rate;     // ~0.76 — pure-FOR baseline
  const fail = data.base_fail_rate;       // ~0.24 — dissent chance baseline

  // Win-rate spectrum: backend sorts ascending, so most-outvoted appear at top.
  const spectrum = data.profiles;
  const spectrumHeight = Math.max(360, spectrum.length * 21);
  const winColor = (w: number) =>
    w < 0.5 ? "#f87171" : w < carry ? "#f59e0b" : "#22c55e";

  const bottom = spectrum[0];                       // most outvoted
  const topWinner = spectrum[spectrum.length - 1];  // most dominant
  const losers = spectrum.filter((p) => p.win_rate < 0.5);

  // Councillors worth labelling directly on the scatter (the rest get a tooltip) —
  // the most active by contested-vote count, computed from data. Never hardcode
  // specific names here: this panel (and any dataset it loads) must work
  // unmodified for a placeholder run, a real reviewed run, or a second council.
  const HIGHLIGHT = new Set(
    [...data.profiles].sort((a, b) => b.n - a.n).slice(0, 6).map((p) => p.name)
  );

  // Most prolific dissenter (by AGAINST-vote count) and, separately, whoever
  // converts objections into actual losses most often — both computed from
  // the loaded data, not hardcoded, so the callout is accurate for any corpus.
  const byDissentN = [...data.profiles]
    .filter((p) => p.dissent_n > 0)
    .sort((a, b) => b.dissent_n - a.dissent_n);
  const mostProlific = byDissentN[0] ?? null;
  const mostEffective = [...data.profiles]
    .filter((p) => p.dissent_effectiveness !== null && p.name !== mostProlific?.name)
    .sort((a, b) => (b.dissent_effectiveness ?? 0) - (a.dissent_effectiveness ?? 0))[0] ?? null;

  // Dissent effectiveness scatter (only councillors with enough AGAINST votes).
  const eff = data.profiles
    .filter((p) => p.dissent_effectiveness !== null)
    .map((p) => ({ ...p, x: p.dissent_rate * 100, y: (p.dissent_effectiveness ?? 0) * 100 }));
  const effHi = eff.filter((p) => HIGHLIGHT.has(p.name));
  const effLo = eff.filter((p) => !HIGHLIGHT.has(p.name));

  // Power over time: reshape to one row per term, one column per councillor.
  const termOrder = ["2003-07", "2007-11", "2011-15", "2015-19", "2019-23", "2023-27"];
  const otNames = data.over_time.map((o) => o.name);
  const otRows = termOrder
    .map((term) => {
      const row: Record<string, number | string | null> = { term };
      data.over_time.forEach((o) => {
        const pt = o.points.find((p) => p.term === term);
        row[o.name] = pt ? Math.round(pt.win_rate * 100) : null;
      });
      return row;
    })
    .filter((row) => otNames.some((n) => row[n] !== null));

  // The single lowest term-by-term win rate across the whole over_time series,
  // for the closing chart-note — computed, not hardcoded, same reasoning as above.
  const allTermPoints = data.over_time.flatMap((o) =>
    o.points.map((p) => ({ name: o.name, term: p.term, win_rate: p.win_rate }))
  );
  const lowestTermPoint = allTermPoints.length
    ? allTermPoints.reduce((min, p) => (p.win_rate < min.win_rate ? p : min))
    : null;

  return (
    <Card
      title="Who Wins — Power on a Split Council"
      subtitle={`Every motion that drew a dissenting vote and carried or was lost · ${data.n_contested.toLocaleString()} contested decisions, 1995–2026`}
      valence="critical"
      backTo="sc-power"
    >
      <div className="planning-hero-row">
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-peak">{pct(topWinner.win_rate)}</span>
          <span className="planning-stat-label">top win rate (<CouncillorLink name={topWinner.name} />)</span>
        </div>
        <div className="planning-stat-divider" />
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-recent">{pct(bottom.win_rate)}</span>
          <span className="planning-stat-label">most outvoted (<CouncillorLink name={bottom.name} />)</span>
        </div>
        <div className="planning-stat-divider" />
        <div className="planning-stat">
          <span className="planning-stat-num">{pct(fail)}</span>
          <span className="planning-stat-label">of contested motions actually fail</span>
        </div>
      </div>

      {mostProlific && (
        <div className="objection-callout">
          <span className="objection-callout-diff">
            {pct(1 - (mostProlific.dissent_effectiveness ?? 0))}
          </span>
          <span className="objection-callout-text">
            of <strong><CouncillorLink name={mostProlific.name} /></strong>'s objections failed —
            the chamber's most prolific dissenter by AGAINST-vote count ({mostProlific.dissent_n}),
            yet only <strong>{pct(mostProlific.dissent_effectiveness ?? 0)}</strong> of those
            objections actually sank a motion.
            {mostEffective && (
              <> <strong><CouncillorLink name={mostEffective.name} /></strong> dissents far less
              often but converts <strong>{pct(mostEffective.dissent_effectiveness ?? 0)}</strong> of
              objections into losses — same chamber, very different leverage.</>
            )}
          </span>
        </div>
      )}

      <p className="section-heading">
        The permanent majority — and minority
        <span className="section-hint"> · click a bar to see that councillor's contested votes</span>
      </p>
      <ResponsiveContainer width="100%" height={spectrumHeight}>
        <BarChart data={spectrum} layout="vertical" margin={{ top: 4, right: 44, bottom: 4, left: 96 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" horizontal={false} />
          <XAxis type="number" domain={[0, 1]} tickFormatter={pct} tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="name" width={120} interval={0}
            tick={({ x, y, payload }: { x: number | string; y: number | string; payload: { value: string } }) => (
              <CouncillorTick x={x} y={y} payload={payload} />
            )} />
          <Tooltip content={<WinTooltip />} cursor={{ fill: "var(--cursor)" }} />
          <ReferenceLine x={carry} stroke="#64748b" strokeDasharray="4 4"
            label={{ value: "vote-yes baseline", fill: "#94a3b8", fontSize: 10, position: "top" }} />
          <ReferenceLine x={0.5} stroke="#475569" strokeDasharray="2 2" />
          <Bar dataKey="win_rate" name="Win rate" radius={[0, 3, 3, 0]}
            cursor="pointer"
            onClick={(entry: { name?: string }) => entry?.name && setSelected(entry.name)}>
            {spectrum.map((e, i) => <Cell key={i} fill={winColor(e.win_rate)} />)}
            <LabelList dataKey="win_rate" position="right" formatter={(v) => pct(Number(v))}
              style={{ fill: "#94a3b8", fontSize: 10 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {selectedProfile && (
        <DrillDown
          title={<><CouncillorLink name={selectedProfile.name} /> — contested votes</>}
          subtitle={`on the winning side ${pct(selectedProfile.win_rate)} of ${selectedProfile.n} contested votes${selectedProfile.n_shown < selectedProfile.n ? ` · showing ${selectedProfile.n_shown} most recent` : ""}`}
          onClose={() => setSelected(null)}
        >
          {selectedProfile.votes.length === 0 && (
            <p className="chart-note">No itemised contested votes extracted for this councillor.</p>
          )}
          {selectedProfile.votes.map((v, i) => (
            <ContestedVoteRow key={i} v={v} />
          ))}
        </DrillDown>
      )}

      <p className="chart-note">
        Share of a councillor's contested votes cast on the winning side (FOR a motion that carried,
        or AGAINST one that was lost). The dashed line at {pct(carry)} is what a councillor who simply
        voted yes on everything would score — the carry rate of contested motions. Red = lost more
        contested votes than they won ({losers.length} councillors); amber = net winner but below the
        rubber-stamp baseline; green = above it. ● = still active.
      </p>

      <p className="section-heading">When they break ranks, does the council follow?</p>
      <ResponsiveContainer width="100%" height={380}>
        <ScatterChart margin={{ top: 16, right: 24, bottom: 36, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
          <XAxis type="number" dataKey="x" name="Dissent rate" unit="%" domain={[0, "dataMax + 5"]}
            tick={{ fontSize: 11 }}
            label={{ value: "how often they vote AGAINST →", position: "bottom", offset: 16, fill: "#94a3b8", fontSize: 11 }} />
          <YAxis type="number" dataKey="y" name="Dissent success" unit="%" domain={[0, 100]}
            tick={{ fontSize: 11 }}
            label={{ value: "↑ % of objections that prevail", angle: -90, position: "insideLeft", fill: "#94a3b8", fontSize: 11 }} />
          <ZAxis type="number" dataKey="n" range={[40, 420]} name="contested votes" />
          <Tooltip content={<ScatterTooltip />} cursor={{ strokeDasharray: "3 3" }} />
          <ReferenceLine y={fail * 100} stroke="#64748b" strokeDasharray="4 4"
            label={{ value: `chance (${pct(fail)})`, fill: "#94a3b8", fontSize: 10, position: "insideTopRight" }} />
          <Scatter data={effLo} fillOpacity={0.55}>
            {effLo.map((e, i) => <Cell key={i} fill={e.y >= fail * 100 ? "#22c55e" : "#f87171"} />)}
          </Scatter>
          <Scatter data={effHi} fillOpacity={0.95} stroke="#e2e8f0" strokeWidth={1}>
            {effHi.map((e, i) => <Cell key={i} fill={e.y >= fail * 100 ? "#22c55e" : "#f87171"} />)}
            <LabelList dataKey="name" position="top" style={{ fill: "#e2e8f0", fontSize: 10 }} />
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Each bubble is a councillor (size = contested votes cast). Horizontal axis: how often they
        dissent. Vertical axis: of those dissents, how often the motion actually failed. The dashed
        line is the chance baseline ({pct(fail)} — the overall failure rate). Bubbles low and to the
        right are <strong>lone wolves</strong> who object often but rarely win; high and to the right
        are <strong>insurgent leaders</strong> the chamber follows. Green sits above chance, red below.
      </p>

      <p className="section-heading">Power shifts with every election</p>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={otRows} margin={{ top: 8, right: 24, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
          <XAxis dataKey="term" tick={{ fontSize: 11 }} />
          <YAxis domain={[20, 100]} unit="%" tick={{ fontSize: 11 }} width={36} />
          <Tooltip cursor={{ stroke: "#334155" }}
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 12 }} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <ReferenceLine y={Math.round(carry * 100)} stroke="#64748b" strokeDasharray="4 4" />
          {otNames.map((n, i) => (
            <Line key={n} type="monotone" dataKey={n} stroke={LINE_COLORS[i % LINE_COLORS.length]}
              strokeWidth={2} dot={{ r: 3 }} connectNulls />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Win rate per four-year council term for the six longest-serving members (≥10 contested votes
        in a term).
        {lowestTermPoint && (
          <> <CouncillorLink name={lowestTermPoint.name} /> hit the lowest single-term win rate on
          record — {pct(lowestTermPoint.win_rate)} in {lowestTermPoint.term} — a reminder that no
          seat is safe from an election reshaping the majority.</>
        )}
        {" "}Reading the lines sideways shows who rose and who fell as each election reshaped the
        chamber.
      </p>
    </Card>
  );
}
