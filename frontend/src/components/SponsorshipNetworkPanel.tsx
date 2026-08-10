import { useData } from "../hooks/useData";
import { api, SponsorshipData, SponsorEdge, SponsorNode } from "../api";
import { Card, LoadingCard, ErrorCard } from "./InterestsChart";
import { CouncillorLink, useCouncillor } from "./CouncillorModal";
import { Reveal } from "./DrillDown";

const KIND_COLOR: Record<string, string> = {
  alliance: "#22c55e",   // sponsor AND vote together — a real working bloc
  procedural: "#f87171", // sponsor, but vote oppositely — "courtesy" seconding
  mixed: "#94a3b8",
};

function lastName(n: string): string {
  const p = n.trim().split(/\s+/);
  return p.length > 1 ? p[p.length - 1] : n;
}

// ── Part 2: deterministic circular node-link diagram of the 2000s network ──
function OldGuardNetwork({ nodes, edges }: { nodes: SponsorNode[]; edges: SponsorEdge[] }) {
  const { open } = useCouncillor();
  const core = nodes.filter((n) => n.in_core);
  const idx = new Map(core.map((n, i) => [n.name, i] as const));
  const W = 720, H = 470, cx = W / 2, cy = H / 2 + 6, R = 168;
  const pos = (name: string) => {
    const i = idx.get(name) ?? 0;
    const ang = (i / core.length) * 2 * Math.PI - Math.PI / 2;
    return { x: cx + R * Math.cos(ang), y: cy + R * Math.sin(ang), ang };
  };
  const maxAct = Math.max(...core.map((n) => n.moved + n.seconded), 1);
  const maxLift = Math.max(...edges.map((e) => e.lift), 1);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxHeight: 480 }}>
      {/* edges */}
      {edges.map((e, i) => {
        if (!idx.has(e.name_a) || !idx.has(e.name_b)) return null;
        const a = pos(e.name_a), b = pos(e.name_b);
        const w = 1 + (e.lift / maxLift) * 5;
        return (
          <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
            stroke={KIND_COLOR[e.kind]} strokeWidth={w}
            strokeOpacity={e.kind === "alliance" ? 0.7 : 0.5}
            strokeDasharray={e.kind === "procedural" ? "5 4" : undefined} />
        );
      })}
      {/* nodes */}
      {core.map((n) => {
        const p = pos(n.name);
        const r = 5 + ((n.moved + n.seconded) / maxAct) * 11;
        const right = Math.cos(p.ang) >= -0.01;
        const lx = p.x + (right ? 1 : -1) * (r + 5);
        return (
          <g key={n.name}>
            <circle cx={p.x} cy={p.y} r={r} fill="#1e293b" stroke="#64748b" strokeWidth={1.5} />
            <text x={lx} y={p.y + 4} fontSize={12} fill="#cbd5e1"
              textAnchor={right ? "start" : "end"}
              style={{ cursor: "pointer" }} onClick={() => open(n.name)}>{lastName(n.name)}</text>
          </g>
        );
      })}
    </svg>
  );
}

function EdgeRow({ e, denom }: { e: SponsorEdge; denom: number }) {
  return (
    <div className="spon-edge-row">
      <span className="spon-edge-names">
        <CouncillorLink name={e.name_a}>{lastName(e.name_a)}</CouncillorLink>
        {" "}<span className="spon-amp">&amp;</span>{" "}
        <CouncillorLink name={e.name_b}>{lastName(e.name_b)}</CouncillorLink>
        <span className="spon-edge-era"> · {e.era_label}</span>
      </span>
      <div className="spon-edge-bar-track">
        <div className="spon-edge-bar"
          style={{ width: `${Math.min(100, (e.lift / denom) * 100)}%`, background: KIND_COLOR[e.kind] }} />
      </div>
      <span className="spon-edge-stat">×{e.lift.toFixed(1)} lift</span>
      <span className="spon-edge-agree" style={{ color: KIND_COLOR[e.kind] }}>
        {e.agree_pct === null ? "—" : `${Math.round(e.agree_pct)}%`} agree
        <span className="spon-edge-n"> (n={e.agree_n})</span>
      </span>
    </div>
  );
}

export function SponsorshipNetworkPanel() {
  const { data, loading, error } = useData<SponsorshipData>(() => api.sponsorship());
  if (loading) return <LoadingCard />;
  if (error || !data) return <ErrorCard msg={error} />;

  const maxAllyLift = Math.max(...data.alliances.map((e) => e.lift), 3);
  const maxEras = Math.max(...data.eras.map((e) => e.cluster_size), 1);
  const lift = data.convergence_high_agree;
  const base = data.convergence_low_agree;

  // The strongest validated alliances by lift, for the worked example below —
  // computed from data, never hardcoded (must hold for any dataset this loads).
  const topAlliances = [...data.alliances].sort((a, b) => b.lift - a.lift).slice(0, 2);

  return (
    <Card
      title="Who Backed Whom — the Sponsorship Network a Unanimous Vote Hides"
      subtitle="Cambridge votes together ~90% of the time. Who SECONDS whose motions reveals the working blocs the vote record can't · 1996–2023"
      valence="neutral"
      backTo="sc-sponsorship"
    >
      {/* convergence hero */}
      <div className="planning-hero-row">
        <div className="planning-stat">
          <span className="planning-stat-num planning-stat-recent">{lift}%</span>
          <span className="planning-stat-label">contested-vote agreement among heavy mutual sponsors</span>
        </div>
        <div className="planning-stat-divider" />
        <div className="planning-stat">
          <span className="planning-stat-num">{base}%</span>
          <span className="planning-stat-label">agreement among everyone else (the base rate)</span>
        </div>
      </div>
      <div className="objection-callout">
        <span className="objection-callout-text">
          In a chamber where <strong>{data.oldguard_unanimous_pct}%</strong> of carried motions passed
          with no dissent, the recorded vote can't tell allies apart. But councillors who sponsor each
          other's motions far above chance also vote together far more than the rest — so sponsorship
          surfaces real working structure. This is an <strong>Observation</strong>: backing an ally's
          motion is ordinary politics, not impropriety.
        </span>
      </div>

      {/* ── Part 1 — validated alliances ── */}
      <p className="section-heading">1 · The validated alliances — sponsor <em>and</em> vote together</p>
      <div className="spon-edge-list">
        {data.alliances.map((e, i) => <EdgeRow key={i} e={e} denom={maxAllyLift} />)}
      </div>
      <p className="chart-note">
        Each pair seconded each other's motions far more than their activity predicts (lift = observed ÷
        expected; ×2 means twice as often as chance), <em>and</em> sided together on contested votes well
        above the {base}% chamber base rate. These are genuine working blocs. Lift controls for volume,
        so a busy chair who seconds everything does not top the list. Bars scaled to the strongest lift.
        {topAlliances.length > 0 && (
          <> <Reveal label="the strongest validated pairs">
            e.g. {topAlliances.map((e, i) => (
              <span key={i}>
                {i > 0 && " and "}
                {lastName(e.name_a)}–{lastName(e.name_b)}
              </span>
            ))}
          </Reveal></>
        )}
      </p>

      {data.procedural.length > 0 && (
        <>
          <p className="section-heading" style={{ marginTop: 18 }}>
            …but seconding isn't always support — the "courtesy second"
          </p>
          <div className="spon-edge-list">
            {data.procedural.map((e, i) => <EdgeRow key={i} e={e} denom={maxAllyLift} />)}
          </div>
          <p className="chart-note">
            These pairs <em>also</em> sponsor each other heavily, yet vote <strong>oppositely</strong> on most
            divisive items (agreement at or below the {base}% base rate). Seconding is partly a procedural
            courtesy — putting a motion on the floor so it can be debated and voted — not an endorsement. It is
            why the network must be validated against votes before any pair is called an "alliance."
          </p>
        </>
      )}

      {/* ── Part 2 — the 2000s old-guard network ── */}
      <p className="section-heading" style={{ marginTop: 20 }}>
        2 · The 2000s "old guard" — Cambridge's most entrenched sponsorship web ({data.oldguard_label})
      </p>
      <OldGuardNetwork nodes={data.oldguard_nodes} edges={data.oldguard_edges} />
      <div className="spon-legend">
        <span><i style={{ background: KIND_COLOR.alliance }} /> alliance (also votes together)</span>
        <span><i style={{ background: KIND_COLOR.procedural }} className="dashed" /> procedural (votes oppositely)</span>
        <span><i style={{ background: KIND_COLOR.mixed }} /> mixed / few contested votes</span>
        <span className="spon-legend-note">node size = how active · line weight = sponsorship lift</span>
      </div>
      <p className="chart-note">
        Through 2000–2007 a stable group of long-servers preferentially backed each other's motions. It is the
        densest sponsorship cluster in 30 years. But it is <em>not</em> a single voting bloc: several of the
        strongest ties are <span style={{ color: KIND_COLOR.procedural }}>procedural</span> — members who
        sponsored deep into the network yet voted against those same colleagues on divisive items.
        "Old guard" describes a working establishment, not a unified faction.
      </p>

      {/* ── Part 3 — structural history ── */}
      <p className="section-heading" style={{ marginTop: 20 }}>
        3 · The structural history — consolidation, collapse, and a modern reshuffle
      </p>
      <div className="spon-era-strip">
        {data.eras.map((e) => (
          <div key={e.label} className="spon-era">
            <div className="spon-era-bar-wrap">
              <div className="spon-era-bar"
                style={{
                  height: `${20 + (e.cluster_size / maxEras) * 90}px`,
                  background: e.cluster_size >= 8 ? "#22c55e"
                    : e.cluster_size >= 5 ? "#eab308" : "#64748b",
                }}>
                <span className="spon-era-size">{e.cluster_size}</span>
              </div>
            </div>
            <div className="spon-era-label">{e.label}</div>
            <div className="spon-era-struct">{e.structure}</div>
          </div>
        ))}
      </div>
      <p className="chart-note">
        Bars show the size of the largest mutually-sponsoring cluster in each ~4-year electoral term. The old
        guard <strong>consolidated</strong> across 2000–07 (clusters of 10–11), then <strong>fragmented</strong>
        {" "}after the 2007 election (down to 4). No comparably durable bloc has formed since: the 2016–19
        figure is a small hyperactive chamber where nearly everyone sponsored everyone, and 2020–23 reshuffles
        again. <em>Note: descriptive structural history, not a significance test — cross-term persistence is
        visible but, on this corpus, rests on too few high-lift edges per term to prove statistically.</em>
        {" "}Severity: Observation · maps to CIPFA principle B (how the chamber conducts its business).
      </p>
    </Card>
  );
}
