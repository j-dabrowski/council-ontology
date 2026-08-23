import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useData } from "../hooks/useData";
import { api, CouncillorProfile, CouncillorsData } from "../api";
import { SourceQuote } from "./DrillDown";

// ── Context ──────────────────────────────────────────────────────────────────

interface CouncillorCtxType { open: (name: string) => void; }
const CouncillorCtx = createContext<CouncillorCtxType>({ open: () => {} });
export function useCouncillor() { return useContext(CouncillorCtx); }

// ── CouncillorLink — inline clickable name ───────────────────────────────────

export function CouncillorLink({ name, className, children }: {
  name: string; className?: string; children?: React.ReactNode;
}) {
  const { open } = useCouncillor();
  return (
    <button
      className={["cllr-link", className].filter(Boolean).join(" ")}
      onClick={(e) => { e.stopPropagation(); open(name); }}
    >
      {children ?? name}
    </button>
  );
}

// ── CouncillorTick — recharts YAxis custom tick ──────────────────────────────
// Use as: <YAxis tick={(props) => <CouncillorTick {...props as never} />} />
// Expects payload.value = full councillor name; displays last name only.

export function CouncillorTick({ x, y, payload }: {
  x: number | string; y: number | string; payload: { value: string };
}) {
  const { open } = useCouncillor();
  const parts = (payload.value ?? "").trim().split(/\s+/);
  const label = parts.length > 1 ? parts[parts.length - 1] : parts[0];
  return (
    <text
      x={x} y={y} dy={4}
      textAnchor="end"
      fontSize={11}
      fill="var(--text-muted)"
      style={{ cursor: "pointer" }}
      onClick={() => open(payload.value)}
    >
      {label}
    </text>
  );
}

// ── Modal ────────────────────────────────────────────────────────────────────

const TYPE_LABEL: Record<string, string> = {
  financial: "Financial", proximity: "Proximity",
  impartiality: "Impartiality", other: "Other",
};

function pct(v: number) { return `${Math.round(v * 100)}%`; }

function ProfileModal({ profile, onClose }: { profile: CouncillorProfile; onClose: () => void }) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const hasVoting = profile.win_rate !== null;
  const hasDecls  = profile.n_declarations > 0;
  const hasSpon   = profile.moved > 0 || profile.top_partners.length > 0;

  return (
    <div className="cllr-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div className="cllr-drawer" onClick={(e) => e.stopPropagation()}>

        {/* Header */}
        <div className="cllr-head">
          <div className="cllr-head-left">
            <span className="cllr-name">{profile.name}</span>
            <span className={`cllr-badge ${profile.is_active ? "cllr-active" : "cllr-retired"}`}>
              {profile.is_active ? "Active" : "Retired"}
            </span>
          </div>
          <button className="drill-close" onClick={onClose} aria-label="Close profile">✕</button>
        </div>

        <div className="cllr-body">

          {/* Service overview */}
          <div className="cllr-section">
            <div className="cllr-section-title">Service</div>
            <div className="cllr-facts">
              {profile.tenure_years != null && (
                <div className="cllr-fact">
                  <span className="cllr-fact-num">{profile.tenure_years}y</span>
                  <span className="cllr-fact-label">on record</span>
                </div>
              )}
              {profile.n_votes != null && (
                <div className="cllr-fact">
                  <span className="cllr-fact-num">{profile.n_votes.toLocaleString()}</span>
                  <span className="cllr-fact-label">votes cast</span>
                </div>
              )}
              {profile.moved > 0 && (
                <div className="cllr-fact">
                  <span className="cllr-fact-num">{profile.moved}</span>
                  <span className="cllr-fact-label">moved</span>
                </div>
              )}
              {profile.seconded > 0 && (
                <div className="cllr-fact">
                  <span className="cllr-fact-num">{profile.seconded}</span>
                  <span className="cllr-fact-label">seconded</span>
                </div>
              )}
            </div>
            {(profile.first_vote || profile.last_vote) && (
              <p className="cllr-meta">
                {profile.first_vote} → {profile.last_vote}
                {profile.roles.length > 0 && <> · {profile.roles.join(", ")}</>}
              </p>
            )}
          </div>

          {/* Voting power */}
          {hasVoting && (
            <div className="cllr-section">
              <div className="cllr-section-title">Voting power</div>
              <div className="cllr-facts">
                <div className="cllr-fact">
                  <span className="cllr-fact-num">{pct(profile.win_rate!)}</span>
                  <span className="cllr-fact-label">win rate</span>
                </div>
                <div className="cllr-fact">
                  <span className="cllr-fact-num">{profile.n_contested?.toLocaleString()}</span>
                  <span className="cllr-fact-label">contested votes</span>
                </div>
                <div className="cllr-fact">
                  <span className="cllr-fact-num">{pct(profile.dissent_rate ?? 0)}</span>
                  <span className="cllr-fact-label">dissent rate</span>
                </div>
                {profile.dissent_effectiveness != null && (
                  <div className="cllr-fact">
                    <span className="cllr-fact-num">{pct(profile.dissent_effectiveness)}</span>
                    <span className="cllr-fact-label">dissents that won</span>
                  </div>
                )}
              </div>

              {profile.dissent_votes.length > 0 && (
                <>
                  <p className="cllr-sub-heading">Recent dissents</p>
                  {profile.dissent_votes.map((v, i) => (
                    <div key={i} className="cllr-vote-row">
                      <div className="decl-row-head">
                        <span className="decl-type decl-type-impartiality">
                          Against · {v.outcome}
                        </span>
                        <span className="decl-date">
                          {v.date}{v.item ? ` · item ${v.item}` : ""}
                        </span>
                        {v.margin != null && (
                          <span className="decl-action">margin {v.margin > 0 ? "+" : ""}{v.margin}</span>
                        )}
                      </div>
                      {v.title && <div className="decl-title">{v.title}</div>}
                      <SourceQuote quote={v.quote} />
                    </div>
                  ))}
                </>
              )}
            </div>
          )}

          {/* Declared interests */}
          {hasDecls && (
            <div className="cllr-section">
              <div className="cllr-section-title">
                Declared interests
                <span className="cllr-section-meta">
                  {" "}{profile.n_recused} of {profile.n_declarations} recused
                  {profile.recusal_rate != null && ` (${Math.round(profile.recusal_rate * 100)}%)`}
                </span>
              </div>
              <p className="cllr-meta">
                Blends every declared-interest type — legally-mandatory ("must
                leave") conflicts and lawful "impartiality" interests a
                councillor is entitled to stay and vote on — see the "must
                leave" tag on each row below for which is which.
              </p>
              {profile.declarations.map((d, i) => {
                const t = d.interest_type ?? "other";
                return (
                  <div key={i} className={`decl-row${d.must_leave ? " decl-mustleave" : ""}`}>
                    <div className="decl-row-head">
                      <span className={`decl-type decl-type-${t}`}>
                        {TYPE_LABEL[t] ?? "Declared"}
                        {d.must_leave && <span className="decl-mustleave-tag"> · must leave</span>}
                      </span>
                      <span className="decl-date">{d.date}{d.item ? ` · ${d.item}` : ""}</span>
                      <span className="decl-action">{d.action}</span>
                    </div>
                    {d.title && <div className="decl-title">{d.title}</div>}
                    <div className="decl-what">{d.what || <em>no description</em>}</div>
                    <SourceQuote quote={d.quote} />
                  </div>
                );
              })}
              {profile.declarations.length < profile.n_declarations && (
                <p className="cllr-truncated">
                  Showing {profile.declarations.length} of {profile.n_declarations} (most recent first)
                </p>
              )}
            </div>
          )}

          {/* Sponsorship */}
          {hasSpon && (
            <div className="cllr-section">
              <div className="cllr-section-title">Sponsorship ties</div>
              {profile.top_partners.length > 0 && (
                <p className="cllr-meta">
                  Top co-sponsors:{" "}
                  {profile.top_partners.map((p, i) => (
                    <span key={i}>
                      {i > 0 && " · "}
                      <CouncillorLink name={p.name} />
                      <span className="cllr-partner-count"> ({p.count})</span>
                    </span>
                  ))}
                </p>
              )}
              <p className="cllr-meta">
                Moved {profile.moved} motions · seconded {profile.seconded}
              </p>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}

// ── Provider — wraps the whole app ───────────────────────────────────────────

export function CouncillorProvider({ children }: { children: React.ReactNode }) {
  const [name, setName] = useState<string | null>(null);
  const { data } = useData<CouncillorsData>(() => api.councillors());
  const open = useCallback((n: string) => setName(n), []);

  const profile = name && data ? (data.by_name[name] ?? null) : null;

  return (
    <CouncillorCtx.Provider value={{ open }}>
      {children}
      {profile && <ProfileModal profile={profile} onClose={() => setName(null)} />}
    </CouncillorCtx.Provider>
  );
}
