"""The Standard Council Test Battery.

A repeatable, council-agnostic battery of governance tests. Every test runs the
same logic on any council's database and returns a `TestResult` carrying:

  - a stable `test_id` (so results are comparable *across* councils),
  - the failure/strength genre and the recognised principle it speaks to,
  - a 3-way `valence` — supportive / neutral / critical — so a reader can digest
    good, neutral and bad at a glance,
  - a severity/strength `grade`, the n / base_rate / era, and `data_ok`.

Design intent (see docs/investigator/Investigator_prompt.txt v2.2): novelty governs *prominence*,
not *inclusion*. A test that comes back clean ("no threshold-gaming found") is a
shown, valenced result — not a hidden null. That is what makes the corpus
balanced (good news is reported, not just bad) and comparable (you can only
benchmark councils against each other if every council runs the same battery,
including the tests it passes).

`run_test_battery(session, council_id)` is self-contained; cmd_publish passes it
the query objects it has already computed via `precomputed=` to avoid recomputing
the heavy ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from src.models import (
    ApplicationStatus,
    Deputation,
    Meeting,
    Motion,
    MotionOutcome,
    PlanningApplication,
    Tender,
    Vote,
    VoteChoice,
)
from src.analysis.queries import (
    conflict_recusal_stats,
    councillor_tenure,
    decider_supplier_conflict,
    delegate_body_conflict,
    mayoral_agenda_setting,
    objection_dose_response,
    oversight_body_capture,
    public_engagement_by_year,
    public_question_responsiveness,
    recusal_compliance_trend,
    sponsorship_network,
    tender_concentration,
    transparency_by_year,
    voting_power,
    _normalise_contractor,
)
from src.analysis.divergence import officer_divergence

# ── valence + grade vocabulary ──────────────────────────────────────────────
SUPPORTIVE = "supportive"   # the council does well here (a strength / a clean test)
NEUTRAL = "neutral"         # descriptive — no clear good/bad direction
CRITICAL = "critical"       # a governance concern or integrity flag

# strength ladder (2.3b) ── concern ladder (2.3/4.4) ── plus the data limit
G_SOUND = "Sound practice"
G_STRENGTH = "Good-governance strength"
G_COMMEND = "Commendable"
G_OBSERVATION = "Observation"
G_CONCERN = "Governance concern"
G_INTEGRITY = "Integrity flag"
G_NODATA = "Not computable on this corpus"


@dataclass
class TestResult:
    test_id: str             # stable, comparable across councils ("procurement.threshold_gaming")
    title: str               # resident-facing label
    genre: str               # failure/strength genre ("Integrity / 3.3")
    principle: str           # recognised standard ("Nolan Objectivity · CIPFA-A")
    question: str            # the question the test asks
    valence: str             # SUPPORTIVE | NEUTRAL | CRITICAL
    grade: str               # one of the G_* labels
    headline: str            # the result in one stat-led phrase
    verdict: str             # one neutral sentence — what a fair reader concludes
    data_ok: bool = True     # False = the corpus can't support this test (still comparable!)
    n: int | None = None
    base_rate: str | None = None
    era: str | None = None
    detail_panel: str | None = None  # snapshot/anchor slug of the panel for this test
    series: list[dict] = field(default_factory=list)  # optional sparkline payload
    # Optional chart payload rendered by the generic BatteryTestPanel for tests that
    # have no bespoke panel. kind="bars": {bars:[{label,value,highlight?}], unit, refline?}
    # kind="line": {points:[{x,y}], unit, refline?}.
    chart: dict | None = None


def _bars(pairs, unit: str = "", highlight_label: str | None = None, refline: dict | None = None) -> dict:
    """Build a 'bars' chart payload from (label, value) pairs."""
    return {
        "kind": "bars",
        "unit": unit,
        "refline": refline,
        "bars": [
            {"label": str(lbl), "value": val, "highlight": (lbl == highlight_label)}
            for lbl, val in pairs
        ],
    }


def _line(points, unit: str = "", refline: dict | None = None) -> dict:
    """Build a 'line' chart payload from {x,y} dicts."""
    return {"kind": "line", "unit": unit, "refline": refline, "points": list(points)}


# ── helpers ─────────────────────────────────────────────────────────────────
def _minutes_motions(session: Session, council_id: int):
    """(outcome, votes_against, year) for every motion in minutes."""
    rows = (
        session.query(Motion.outcome, Motion.votes_against, Meeting.meeting_date)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes")
        .all()
    )
    return [(o, va, d.year if d else None) for o, va, d in rows]


def _tender_rows(session: Session, council_id: int):
    """(amount, awarded_to, year, month) for tenders recorded in minutes."""
    rows = (
        session.query(Tender.amount, Tender.awarded_to, Meeting.meeting_date)
        .join(Meeting, Tender.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes")
        .all()
    )
    return [(a, n, (d.year if d else None), (d.month if d else None)) for a, n, d in rows]


# ════════════════════════════════════════════════════════════════════════════
# WRAPPED TESTS — existing flagship panels, re-expressed as valenced battery rows
# ════════════════════════════════════════════════════════════════════════════
def _t_recusal_overall(session, council_id, pc) -> TestResult:
    s = pc.get("conflict") or conflict_recusal_stats(session, council_id)
    stay = round(100 - s.declared_recusal_pct, 1)
    # Computed the same way ConflictRecusalPanel.tsx derives its own headline
    # factor (guarded division against the same two fields), rather than a
    # literal string — confirmed 2026-08-23, defamation review pass 3
    # advisory flag: the two had drifted (hardcoded "~80x" vs. the panel's
    # live 83x for this draft's data).
    factor = round(s.declared_recusal_pct / s.baseline_recusal_pct) if s.baseline_recusal_pct > 0 else 0
    return TestResult(
        test_id="conflict.recusal_management",
        title="Do councillors step out when they declare a conflict?",
        genre="Integrity / conflict (3.3)",
        principle="Nolan Integrity, Objectivity · CIPFA-A",
        question="When an interest is declared, is it *managed* — i.e. does the member recuse?",
        valence=CRITICAL,
        grade=G_CONCERN,
        headline=f"Declaring lifts recusal {factor}×, but members still stay and vote {stay}% of the time",
        verdict="Disclosure works at the first step; the identify–disclose–manage chain breaks at the manage limb.",
        n=s.declared_total,
        base_rate=f"{s.baseline_recusal_pct}% recuse on a normal vote",
        era="1995–2026",
        detail_panel="declared",
    )


def _t_recusal_trend(session, council_id, pc) -> TestResult:
    r = pc.get("recusal_trend") or recusal_compliance_trend(session, council_id)
    return TestResult(
        test_id="conflict.recusal_trend",
        title="Did recusal compliance track the Authorised Inquiry?",
        genre="Integrity / conflict (3.3)",
        principle="Nolan Accountability · CIPFA-A",
        question="Did stepping out of serious conflicts change around external scrutiny?",
        valence=CRITICAL,
        grade=G_CONCERN,
        headline=(f"Must-leave recusal rose to {r.must_leave_inquiry_pct}% during the Inquiry, "
                  f"then fell to {r.must_leave_post_pct}% after"),
        verdict=("Survives its own promoter: even within financial conflicts (leaving is mandatory) "
                 f"recusal held at {r.financial_inquiry_pct}%→{r.financial_post_pct}% — the only "
                 f"post-2022 financial declaration on record (n={r.financial_post_n}) is too few "
                 "to assess a trend either way."),
        n=r.must_leave_pre_n + r.must_leave_inquiry_n + r.must_leave_post_n,
        base_rate="leaving is legally mandatory for financial/proximity interests",
        era="pre-2018 / 2018–21 / post-2022",
        detail_panel="recusal",
    )


def _t_delegate_body_conflict(session, council_id, pc) -> TestResult:
    """[41] The mirror image of `procurement.decider_supplier_conflict`: not a
    private supplier relationship, but a councillor's OWN appointed delegate
    role on an external body — do they declare an interest before voting on
    THAT BODY's business? Built on `delegate_body_conflict()` — see that
    function's docstring for the appointment-window methodology, the
    `body_name` variant-matching fix, and why the fan-out caveat doesn't
    apply to its declarations-corpuswide count.

    THIN-N, reported anyway: the largest per-body affiliated-vote count is
    21 (Ocean Gardens); Mindarie and Tamala Park sit at 15 and 2. This is the
    same order of thinness `transparency.confidential_tender_size` already
    ships at (n=16) with a DIRECTIONAL era label — the same convention is
    used here rather than treating three-body coverage as ineligible for the
    battery. What makes the result worth shipping despite the n is the shape,
    not the magnitude: two institutional-delegation bodies correctly cluster
    near 0% (a public role, not a personal interest — near-zero IS the
    correct answer) while the one body with genuine private stakes (Ocean
    Gardens — some appointees own or have family owning a retirement-village
    unit there) sits materially higher, backed by 60 corpus-wide
    `interest_declarations` mentions vs 1 and 3 for the other two. The
    contrast between bodies, not any single body's raw percentage, is the
    finding.
    """
    r = pc.get("delegate_body") or delegate_body_conflict(session, council_id)
    if not r.bodies:
        return _nodata("conflict.delegate_body_conflict",
                       "Do council-appointed delegates declare on their own body's business?",
                       "Integrity / conflict (3.3)", "Nolan Objectivity/Integrity · CIPFA-A",
                       "When a councillor is Council's own appointed delegate on an external body, "
                       "do they declare an interest before voting on that body's business?")
    og = next((b for b in r.bodies if "Ocean Gardens" in b.label), r.bodies[-1])
    others = [b for b in r.bodies if b is not og]
    others_desc = "; ".join(
        f"{b.label} {b.affiliated_declared}/{b.affiliated_votes} ({b.affiliated_declared_pct}%)"
        for b in others
    )
    total_n = sum(b.affiliated_votes for b in r.bodies)
    chart = _bars(
        [(b.label, b.affiliated_declared_pct) for b in r.bodies],
        unit="%", highlight_label=og.label,
    )
    return TestResult(
        test_id="conflict.delegate_body_conflict",
        title="Do council-appointed delegates declare on their own body's business?",
        genre="Integrity / conflict (3.3)",
        principle="Nolan Objectivity/Integrity · CIPFA-A",
        question="When a councillor is Council's own appointed delegate/board member on an "
                 "external body, do they declare an interest before voting on that body's "
                 "business — the same disclosure regime a private supplier relationship gets?",
        valence=SUPPORTIVE,
        grade=G_SOUND,
        headline=(f"Institutional delegates declare ~0% on their own body's business (public role, "
                  f"correctly) — the one body with genuine personal stakes, {og.label}, declares "
                  f"{og.affiliated_declared}/{og.affiliated_votes} ({og.affiliated_declared_pct}%), "
                  f"backed by {og.declarations_corpuswide} corpus-wide mentions — DIRECTIONAL, thin n"),
        verdict=("The one channel where councillors could plausibly hold an undeclared personal "
                 "stake in an external body's business — their own Council-appointed delegate role "
                 "— comes back clean, and the split is explicable rather than a gap: institutional "
                 f"delegation ({others_desc}) correctly attracts near-zero declarations, while "
                 f"{og.label}, the one body some appointees hold a genuine private stake in, shows "
                 "real declare-and-recuse behaviour at a materially higher rate, corroborated by 60 "
                 "corpus-wide declaration mentions vs 1–3 for the institutional bodies. Every "
                 "per-body n is thin (2–21 affiliated votes) — read this as a directional, "
                 "explanatory pattern across three bodies, not a precise rate for any one of them."),
        n=total_n,
        base_rate="other councillors' declared-interest rate on the SAME motions: " + "; ".join(
            f"{b.label} {b.other_declared_pct}%" for b in r.bodies
        ),
        era="1995–2026 · DIRECTIONAL (thin n per body)",
        data_ok=True,
        detail_panel="delegate-body-conflict",
        chart=chart,
    )


def _t_transparency(session, council_id, pc) -> TestResult:
    t = pc.get("transparency") or transparency_by_year(session, council_id)
    return TestResult(
        test_id="transparency.confidential_share",
        title="How much business is taken behind closed doors?",
        genre="Process / transparency (3.4)",
        principle="Nolan Openness · CIPFA-B",
        question="What share of decided items is confidential, and is it rising?",
        valence=CRITICAL,
        grade=G_CONCERN,
        headline=f"{t.pre_era_pct}% confidential for two decades, spiking to {t.peak_pct}% in {t.peak_year}",
        verdict=("A strong two-decade openness baseline with a single Inquiry-era spike that "
                 "reverted; the concern is the scale and timing of that spike, not a habit of secrecy."),
        base_rate=f"{t.pre_era_pct}% two-decade baseline",
        era="1995–2026",
        detail_panel="transparency",
        series=[{"x": y.year, "y": y.confidential_pct} for y in t.years if y.total >= 50],
    )


def _t_officer_divergence(session, council_id, pc) -> TestResult:
    pairs = pc.get("divergence") or officer_divergence(session, council_id, None, None)
    total = len(pairs)
    diverged = sum(1 for p in pairs if p.diverged)
    comp = round((total - diverged) / total * 100, 1) if total else None
    return TestResult(
        test_id="governance.officer_ratification",
        title="Does the chamber decide, or ratify its officers?",
        genre="Governance / culture (3.2)",
        principle="CIPFA-F · the 'visible contest is theatre' prior",
        question="How often does council depart from the officer recommendation?",
        valence=CRITICAL,
        grade=G_CONCERN,
        headline=f"Council adopted the officer recommendation {comp}% of the time",
        verdict=("Near-total ratification means the substantive decision is upstream, in who writes "
                 "the recommendation — the most important caveat on every voting finding."),
        n=total,
        base_rate=f"{diverged} departures across {total} matched items",
        era="where officer recs exist (agenda-matched)",
        detail_panel="divergence",
    )


def _t_voting_power(session, council_id, pc) -> TestResult:
    p = pc.get("power") or voting_power(session, council_id)
    wins = [pr.win_rate for pr in p.profiles]
    lo, hi = (round(min(wins) * 100), round(max(wins) * 100)) if wins else (None, None)
    return TestResult(
        test_id="governance.power_spread",
        title="Does consensus hide a power hierarchy?",
        genre="Governance / culture (3.2)",
        principle="CIPFA-B · Nolan Accountability",
        question="On contested votes, how unequal is who actually wins — and is it accountable?",
        valence=CRITICAL,
        grade=G_OBSERVATION,
        headline=f"Contested-vote win rates span {lo}–{hi}% between councillors",
        verdict=("A real hidden hierarchy behind near-unanimous votes — but one that turns over at "
                 "elections rather than ossifying, so it is electorally accountable."),
        n=p.n_contested,
        base_rate=f"{round(p.base_carry_rate * 100, 1)}% base carry rate",
        era="2003–2026 (contested motions)",
        detail_panel="power",
    )


def _t_oversight_body_capture(session, council_id, pc) -> TestResult:
    """[48] "Who controls the controls": does membership on the council's own
    accountability bodies (Audit Committee, CEO Performance Review Committee)
    skew toward the chamber's habitual winners, or draw broadly — including
    from its habitual dissenters? Governance/3.2 AND Strength/E dual-domain,
    mirroring [41]'s delegate-body test but for INTERNAL oversight bodies and
    [18]'s power-spread metric rather than declared-interest rates. Built on
    `oversight_body_capture()` — see that function's docstring for the
    council-agnostic body-name match and why its win-rate figure is NOT
    directly comparable to `voting_power()`'s own published number.

    Refined 2026-08-22 (`Refiner_prompt.txt` v1.1, Step 0 self-selected
    target, second attempt): the first attempt on this finding failed
    dimension 1 on a stale DB state (the [48] Banked entry's own "33 distinct
    councillors" headline vs a hand-derived 32/31) — see
    `[48 REFINEMENT ATTEMPT]` in INVESTIGATIONS.md. That gap is resolved: a
    split councillor identity (`councillor_id` 385 "Walker Colin" merged into
    246 "Colin Walker") was fixed out-of-band the same day, and this session
    independently re-derived every figure below fresh against the live DB
    (not by reading and trusting this function) before shipping it.
    """
    r = pc.get("oversight") or oversight_body_capture(session, council_id)
    if r.n_appointees == 0:
        return _nodata("governance.oversight_body_capture",
                       "Is the council's own oversight function captured by its most powerful members?",
                       "Governance / culture (3.2) & Strength (E)", "CIPFA-A · Nolan Accountability",
                       "Does membership on the council's Audit/CEO-Performance-Review bodies skew "
                       "toward the chamber's habitual winners, or draw broadly?")
    gap = round(r.appointee_win_rate - r.non_appointee_win_rate, 1)
    lo = min((p.win_rate for p in r.profiles), default=None)
    hi = max((p.win_rate for p in r.profiles), default=None)
    chart = _bars(
        [("Appointees", r.appointee_win_rate), ("Non-appointees", r.non_appointee_win_rate)],
        unit="%",
    )
    return TestResult(
        test_id="governance.oversight_body_capture",
        title="Is the council's own oversight function captured by its most powerful members?",
        genre="Governance / culture (3.2) & Strength (E)",
        principle="CIPFA-A (internal audit/oversight function) · Nolan Accountability",
        question="Does membership on the council's Audit Committee / CEO Performance Review "
                 "Committee skew toward the chamber's habitual winners, or draw broadly — "
                 "including from its habitual dissenters?",
        valence=SUPPORTIVE,
        grade=G_STRENGTH,
        headline=(f"{r.n_appointees} distinct councillors have ever sat on an oversight body; "
                  f"appointee win rate {r.appointee_win_rate}% (n={r.appointee_n}) vs "
                  f"non-appointee {r.non_appointee_win_rate}% (n={r.non_appointee_n}) — a "
                  f"{gap} pp gap, statistically indistinguishable"),
        verdict=(f"No self-appointment of the powerful to watch themselves: the oversight-body "
                 f"appointee list's win-rate spread ({lo}–{hi}%) runs almost the full range of "
                 f"the chamber, from its most consistent winners among appointees down to some "
                 f"of the corpus's most frequent dissenters. CIPFA-A's internal audit/oversight-"
                 f"function principle is met on this reading; era-pooled across 31 years, so a "
                 f"modern-era shift could still hide in the aggregate."),
        n=r.appointee_n + r.non_appointee_n,
        base_rate=f"non-appointee win rate {r.non_appointee_win_rate}% (n={r.non_appointee_n})",
        era="1995–2026, era-pooled",
        data_ok=True,
        detail_panel="oversight-body-capture",
        chart=chart,
    )


def _t_mayoral(session, council_id, pc) -> TestResult:
    m = pc.get("mayoral") or mayoral_agenda_setting(session, council_id)
    return TestResult(
        test_id="governance.chair_capture",
        title="Does the council fall in line behind the Mayor?",
        genre="Governance / culture (3.2)",
        principle="Nolan Accountability, Objectivity",
        question="Do the Mayor's own motions get an easier ride than backbench motions?",
        valence=SUPPORTIVE,
        grade=G_STRENGTH,
        headline=(f"Mayoral motions drew dissent {m.mayor_contest_pct}% of the time vs "
                  f"{m.other_contest_pct}% for backbench motions"),
        verdict=("The opposite of chair capture: the chamber votes against its own Mayor *more*, not "
                 "less — the most powerful member earns no deference at the gavel."),
        n=m.mayor_moved,
        base_rate=f"{m.other_contest_pct}% backbench dissent rate",
        era="1999–2026 (mayors with dated terms)",
        detail_panel="mayoral",
    )


def _t_sponsorship(session, council_id, pc) -> TestResult:
    s = pc.get("sponsorship") or sponsorship_network(session, council_id)
    return TestResult(
        test_id="governance.durable_faction",
        title="Is there a faction that survives across elections?",
        genre="Governance / culture (3.2)",
        principle="CIPFA-B · the Perth root-cause genre",
        question="Do voting/sponsorship blocs persist across electoral terms (an entrenched bloc)?",
        valence=NEUTRAL,
        grade=G_OBSERVATION,
        headline=("A 2000s old-guard sponsorship clique existed and fragmented in 2008; no durable "
                  "bloc in the modern council"),
        verdict=("Working alliances are real and visible in who-seconds-whom, but the persistence test "
                 "found no entrenched modern faction — the structure reshuffles each election."),
        base_rate=f"high-sponsor pairs agree {s.convergence_high_agree}% vs {s.convergence_low_agree}% base",
        era="1996–2023 (electoral terms)",
        detail_panel="sponsorship",
    )


def _t_tenure(session, council_id, pc) -> TestResult:
    t = pc.get("tenure") or councillor_tenure(session, council_id)
    longest = max(t.profiles, key=lambda p: p.years) if t.profiles else None
    n15 = sum(1 for p in t.profiles if p.years >= 15)
    return TestResult(
        test_id="governance.incumbency",
        title="Career councillors vs one-term members",
        genre="Governance / culture (3.2)",
        principle="CIPFA-A, E",
        question="How entrenched is the chamber — long-server-heavy, or renewing?",
        valence=NEUTRAL,
        grade=G_OBSERVATION,
        # Named-individual mitigation (BLOCKING #3 pattern; see
        # defamation_review_1.md ADVISORY #2): the Scorecard renders every row
        # unconditionally, with no gating mechanism at all, so a named
        # individual in this headline is un-gated by construction. The name
        # is dropped here; `detail_panel: "tenure"` still sends an interested
        # reader to the named breakdown one click away.
        headline=(f"Median service {t.median_years} years; {n15} served 15+; "
                  f"longest {longest.years if longest else '—'}y"),
        verdict=("Stability with institutional memory, but a long-server-heavy tail that is an "
                 "entrenchment risk worth watching."),
        n=t.n_councillors,
        base_rate=f"median {t.median_years}y",
        era="1995–2026",
        detail_panel="tenure",
    )


def _t_objection_dose(session, council_id, pc) -> TestResult:
    d = pc.get("dose") or objection_dose_response(session, council_id)
    by = {b.label: b for b in d.buckets}
    lo = by.get("0")
    hi = by.get("5+")
    return TestResult(
        test_id="planning.objection_responsiveness",
        title="Does the council respond to community objection?",
        genre="Process / engagement (3.4)",
        principle="CIPFA-B — meaningful stakeholder engagement",
        question="Does refusal rise with the number of residents objecting to an application?",
        valence=SUPPORTIVE,
        grade=G_SOUND,
        headline=(f"Refusal climbs {lo.refusal_pct if lo else '—'}% → {hi.refusal_pct if hi else '—'}% "
                  "from no objectors to 5+"),
        verdict=("A clean dose–response: a lone objection is noise, but coordinated numbers move "
                 "outcomes — engagement works, even if a single letter does not."),
        n=d.total_decided,
        base_rate=f"{lo.refusal_pct if lo else '—'}% refusal with no objectors",
        era="all decided applications",
        detail_panel="dose",
    )


def _t_tender_concentration(session, council_id, pc) -> TestResult:
    t = pc.get("tenders") or tender_concentration(session, council_id)
    red_pct = round(t.redacted_amount / t.total_amount * 100) if t.total_amount else 0
    return TestResult(
        test_id="procurement.concentration",
        title="Where did the tender money go?",
        genre="Procurement / transparency (3.1/3.4)",
        principle="CIPFA-F, G",
        question="Is tendered spend concentrated, and how much is awarded confidentially?",
        valence=NEUTRAL,
        grade=G_OBSERVATION,
        headline=(f"${t.total_amount/1e6:.1f}M across {t.distinct_named} named firms; "
                  f"{red_pct}% of dollars redacted; top-10 take {round(t.top10_share*100)}%"),
        verdict=("Concentration is the nature of big civil contracts and the supplier base is broad; "
                 "the watch-item is the redacted share (a transparency issue), not capture."),
        n=t.total_awards,
        base_rate=f"{t.distinct_named} distinct named contractors",
        era="1995–2026",
        detail_panel="tenders",
    )


# ════════════════════════════════════════════════════════════════════════════
# CLEAN INTEGRITY TESTS — previously hidden nulls, now shown as supportive
# ════════════════════════════════════════════════════════════════════════════
def _t_decider_supplier_conflict(session, council_id, pc) -> TestResult:
    """[35] The Part 3.3 decider x supplier join: does a councillor who votes
    to award a tender ever share a declared or name-matched connection to the
    winning firm? Built on `decider_supplier_conflict()` — see that function's
    docstring for why neither limb touches the `interest_declarations`
    item_reference join. Converges with `procurement.threshold_gaming` and
    `procurement.incumbency` (supplier side) and `conflict.recusal_management`
    (decider side) as a fourth, independent procurement-integrity credit."""
    r = pc.get("decider_supplier") or decider_supplier_conflict(session, council_id)
    chart = _bars(
        [("Tender-award votes", r.declared_pct), ("Chamber base rate", r.base_declared_pct)],
        unit="%", highlight_label="Tender-award votes",
    )
    return TestResult(
        test_id="procurement.decider_supplier_conflict",
        title="Do tender deciders share an undeclared connection with the winner?",
        genre="Integrity / procurement (3.3)",
        principle="Nolan Objectivity · CIPFA-A/F",
        question="When council awards a tender, is a conflict declared — and does the winner ever "
                 "match a councillor's known connections?",
        valence=SUPPORTIVE,
        grade=G_STRENGTH,
        headline=(f"Tender-award votes declare an interest just {r.declared_pct}% of the time "
                  f"(below the {r.base_declared_pct}% chamber base) — zero genuine decider↔winner "
                  f"matches across {r.named_awards} named awards"),
        verdict=("The join that would expose procurement capture — a councillor tied to a tender "
                 "winner with no declaration on the award — finds nothing: both raw surname "
                 "collisions resolve on provenance to unrelated businesses (a weed-spraying "
                 "contractor, a street-sweeper manufacturer), not the councillors who share their "
                 "surname. Converges with the supplier-side credits (no threshold-gaming spike, no "
                 "entrenched incumbent among $92.7M/216 named firms) and the decider-side tests "
                 "(recusal management) as a fourth independent procurement-integrity result — read "
                 "within its coverage limit, since only separately-moved tender-award motions are "
                 "visible, not consent-agenda'd awards."),
        n=r.votes_on_tender_motions,
        base_rate=f"{r.base_declared_pct}% chamber-wide declared-interest rate; "
                  f"{r.named_awards} named awards vs {r.surnames_tested} voting-councillor surnames",
        era="1995–2026",
        detail_panel="decider-supplier",
        chart=chart,
    )


def _t_threshold_gaming(session, council_id, pc) -> TestResult:
    # WA public-tender line: ~$100k pre-Oct-2015, $250k after. Look for a McCrary
    # spike — excess mass just BELOW the active threshold.
    rows = [(a, y) for a, _n, y, _m in _tender_rows(session, council_id) if a and y]
    modern = [a for a, y in rows if y >= 2015]
    thr = 250_000
    below = sum(1 for a in modern if thr * 0.8 <= a < thr)
    above = sum(1 for a in modern if thr <= a < thr * 1.2)
    ratio = round(below / above, 2) if above else None
    clean = ratio is None or ratio <= 1.6
    # histogram in $50k bins to $400k+ — the eye-test for a spike at the line
    edges = [0, 50_000, 100_000, 150_000, 200_000, 250_000, 300_000, 350_000, 400_000]
    labels = ["<50k", "50–100k", "100–150k", "150–200k", "200–250k", "250–300k", "300–350k", "350–400k", "400k+"]
    counts = [0] * len(labels)
    for a in modern:
        idx = next((i for i, e in enumerate(edges) if a < e), None)
        counts[(idx - 1) if idx else (len(labels) - 1)] += 1
    chart = _bars(
        list(zip(labels, counts)), unit="",
        highlight_label="200–250k",  # the just-below-threshold bin
        refline={"label": "$250k tender line", "after": "200–250k"},
    )
    return TestResult(
        test_id="procurement.threshold_gaming",
        title="Are tenders bunched just under the public-tender limit?",
        genre="Integrity / procurement (3.3)",
        principle="Nolan Objectivity · CIPFA-A (IBAC Operation Royston)",
        question="Is there excess mass just below the threshold that triggers competitive tender?",
        valence=SUPPORTIVE if clean else CRITICAL,
        grade=G_STRENGTH if clean else G_INTEGRITY,
        headline=("No spike at the $250k line — just-below and just-above mass are balanced"
                  if clean else "Excess mass found just below the tender threshold"),
        verdict=("No Operation-Royston fingerprint: the amount distribution is a smooth small-jobs "
                 "decay with no pile-up against the threshold." if clean
                 else "Values cluster suspiciously below the threshold; warrants explanation."),
        n=len(modern),
        base_rate=f"below:above mass ratio {ratio}",
        era="2015+ ($250k regime)",
        detail_panel="threshold-gaming",
        chart=chart,
    )


def _t_procurement_incumbency(session, council_id, pc) -> TestResult:
    # Is any supplier BOTH a frequent repeat-winner AND a big-dollar incumbent?
    by_firm: dict[str, dict] = {}
    for a, name, y, _m in _tender_rows(session, council_id):
        if not name:
            continue
        key = _normalise_contractor(name)
        if not key or "respondent" in key:
            continue
        rec = by_firm.setdefault(key, {"years": set(), "amt": 0.0})
        if y:
            rec["years"].add(y)
        if a:
            rec["amt"] += a
    if not by_firm:
        return _nodata("procurement.incumbency", "Repeat-winner / incumbent capture",
                       "Integrity / procurement (3.3)", "ICAC supplier-panel risk",
                       "Do the same firms keep winning the big-dollar work?")
    top_dollars = sorted(by_firm.values(), key=lambda r: r["amt"], reverse=True)[:10]
    top_dollar_keys = {id(r) for r in top_dollars}
    most_recurring = max(by_firm.items(), key=lambda kv: len(kv[1]["years"]))
    most_recurring_name = most_recurring[0].title()
    overlap = any(len(r["years"]) >= 4 and id(r) in top_dollar_keys for r in by_firm.values())
    # chart: the most-recurring firms by distinct years won (recurrence ≠ big dollars)
    top_recurring = sorted(by_firm.items(), key=lambda kv: len(kv[1]["years"]), reverse=True)[:10]
    chart = _bars(
        [(k.title()[:22], len(v["years"])) for k, v in top_recurring],
        unit=" yrs",
    )
    return TestResult(
        test_id="procurement.incumbency",
        title="Do the same firms keep winning the big contracts?",
        genre="Integrity / procurement (3.3)",
        principle="ICAC supplier-panel risk · CIPFA-F",
        question="Is any supplier both a frequent repeat-winner and a big-dollar incumbent?",
        valence=CRITICAL if overlap else SUPPORTIVE,
        grade=G_INTEGRITY if overlap else G_STRENGTH,
        headline=(f"Most-recurring firm ({most_recurring_name[:24]}) appears in "
                  f"{len(most_recurring[1]['years'])} distinct years"),
        verdict=("No entrenched big-dollar incumbent: the repeat-winners are mundane low-value "
                 "equipment/cartage rebids, not the firms that capture the dollars." if not overlap
                 else "A frequent repeat-winner is also a top-dollar recipient; warrants explanation."),
        n=len(by_firm),
        base_rate="repeat ≠ big-dollar",
        era="1995–2026",
        detail_panel="incumbency",
        chart=chart,
    )


def _t_big_dollar_leniency(session, council_id, pc) -> TestResult:
    rows = (
        session.query(PlanningApplication.estimated_value, PlanningApplication.status)
        .filter(
            PlanningApplication.estimated_value.isnot(None),
            PlanningApplication.status.in_([ApplicationStatus.APPROVED, ApplicationStatus.REFUSED]),
        ).all()
    )
    vals = sorted([(v, s) for v, s in rows if v and v > 0], key=lambda t: t[0])
    if len(vals) < 20:
        return _nodata("planning.big_dollar_leniency", "Do big developments get an easier ride?",
                       "Governance / fairness (3.2)", "CIPFA-D — value for money / objectivity",
                       "Are high-value applications approved at a different rate?")
    q = len(vals) // 4
    quartiles = [vals[:q], vals[q:2*q], vals[2*q:3*q], vals[3*q:]]
    rates = []
    for grp in quartiles:
        appr = sum(1 for _v, s in grp if s == ApplicationStatus.APPROVED)
        rates.append(round(appr / len(grp) * 100)) if grp else rates.append(None)
    spread = max(rates) - min(rates)
    flat = spread <= 12
    chart = _bars(
        list(zip(["Q1 (lowest $)", "Q2", "Q3", "Q4 (highest $)"], rates)), unit="%",
    )
    return TestResult(
        test_id="planning.big_dollar_leniency",
        title="Do big-dollar developments get an easier ride?",
        genre="Governance / fairness (3.2)",
        principle="CIPFA-D · Nolan Objectivity",
        question="Does approval rate vary with the estimated value of the development?",
        valence=SUPPORTIVE if flat else CRITICAL,
        grade=G_SOUND if flat else G_CONCERN,
        headline=f"Approval by value quartile (low→high): {rates[0]}/{rates[1]}/{rates[2]}/{rates[3]}%",
        verdict=("Flat across value quartiles — big developers get neither an easier ride nor extra "
                 "scrutiny." if flat else "Approval rate varies with project value; warrants a look."),
        n=len(vals),
        base_rate=f"{spread}pp spread across quartiles",
        era="applications with a recorded value",
        detail_panel="big-dollar",
        chart=chart,
    )


def _t_repeat_applicant(session, council_id, pc) -> TestResult:
    rows = (
        session.query(PlanningApplication.applicant_name, PlanningApplication.status)
        .filter(
            PlanningApplication.applicant_name.isnot(None),
            PlanningApplication.status.in_([ApplicationStatus.APPROVED, ApplicationStatus.REFUSED]),
        ).all()
    )
    freq: dict[str, list] = {}
    for name, status in rows:
        nm = (name or "").strip().lower()
        if not nm:
            continue
        freq.setdefault(nm, []).append(status)
    if not freq:
        return _nodata("planning.repeat_applicant", "Do frequent applicants win more often?",
                       "Integrity / fairness (3.3)", "ICAC favouritism risk",
                       "Do repeat builders/agents get approved more than one-shot applicants?")

    def rate(items):
        n = len(items)
        appr = sum(1 for s in items if s == ApplicationStatus.APPROVED)
        return round(appr / n * 100) if n else None, n

    buckets = {"1": [], "2-3": [], "4-6": [], "7+": []}
    for nm, items in freq.items():
        c = len(items)
        key = "1" if c == 1 else "2-3" if c <= 3 else "4-6" if c <= 6 else "7+"
        buckets[key].extend(items)
    rates = {k: rate(v)[0] for k, v in buckets.items()}
    vals = [r for r in rates.values() if r is not None]
    flat = (max(vals) - min(vals)) <= 14 if vals else True
    chart = _bars(
        [("1 app", rates["1"]), ("2–3", rates["2-3"]), ("4–6", rates["4-6"]), ("7+", rates["7+"])],
        unit="%",
    )
    return TestResult(
        test_id="planning.repeat_applicant",
        title="Do frequent applicants win approval more often?",
        genre="Integrity / fairness (3.3)",
        principle="ICAC favouritism risk · Nolan Objectivity",
        question="Do repeat builders/agents get approved at a higher rate than one-shot applicants?",
        valence=SUPPORTIVE if flat else CRITICAL,
        grade=G_STRENGTH if flat else G_CONCERN,
        headline=f"Approval by applicant frequency: 1×={rates['1']}% · 2–3={rates['2-3']}% · 4–6={rates['4-6']}% · 7+={rates['7+']}%",
        verdict=("No repeat-player advantage — frequent applicants win no more than first-timers."
                 if flat else "Frequent applicants are approved at a notably different rate; warrants a look."),
        n=sum(len(v) for v in freq.values()),
        base_rate="flat across frequency",
        era="applications with a named applicant",
        detail_panel="repeat-applicant",
        chart=chart,
    )


# ════════════════════════════════════════════════════════════════════════════
# NEUTRAL DESCRIPTIVE TESTS — how the council works (no good/bad direction)
# ════════════════════════════════════════════════════════════════════════════
def _t_unanimity_trend(session, council_id, pc) -> TestResult:
    rows = _minutes_motions(session, council_id)
    by_year: dict[int, list[int]] = {}
    for outcome, va, year in rows:
        if year is None or outcome != MotionOutcome.CARRIED:
            continue
        by_year.setdefault(year, []).append(1 if (va or 0) > 0 else 0)
    series = []
    for y in sorted(by_year):
        items = by_year[y]
        if len(items) >= 30:
            series.append({"x": y, "y": round(sum(items) / len(items) * 100, 1)})
    total = [v for items in by_year.values() for v in items]
    overall = round(sum(total) / len(total) * 100, 1) if total else None
    return TestResult(
        test_id="governance.unanimity_trend",
        title="How often does the chamber actually split?",
        genre="Governance / culture (3.2)",
        principle="CIPFA-B — how the chamber conducts business",
        question="What share of carried motions drew at least one dissenting vote, over time?",
        valence=NEUTRAL,
        grade=G_OBSERVATION,
        headline=f"{overall}% of carried motions drew a dissenting vote (chamber-wide)",
        verdict=("Mostly-unanimous on the surface; the contested share moves with the political era "
                 "rather than holding constant."),
        n=len(total),
        base_rate=f"{overall}% contested",
        era="1995–2026 (years with ≥30 carried motions)",
        series=series,
        detail_panel="unanimity",
        chart=_line([{"x": p["x"], "y": p["y"]} for p in series], unit="%"),
    )


def _t_eoy_spending(session, council_id, pc) -> TestResult:
    rows = [(a, m) for a, _n, _y, m in _tender_rows(session, council_id) if a and m]
    if not rows:
        return _nodata("finance.eoy_spending", "End-of-year spending spike",
                       "Financial (3.1)", "ICAC generic risk",
                       "Do tender awards/dollars spike at the end of the budget cycle?")
    dec_amt = sum(a for a, m in rows if m == 12)
    tot_amt = sum(a for a, _m in rows)
    dec_n = sum(1 for _a, m in rows if m == 12)
    dec_share = round(dec_amt / tot_amt * 100) if tot_amt else 0
    expected = round(100 / 12)
    spike = dec_share >= expected * 2
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    by_month = [0.0] * 12
    for a, m in rows:
        if 1 <= m <= 12:
            by_month[m - 1] += a / 1e6
    chart = _bars(
        [(months[i], round(by_month[i], 1)) for i in range(12)],
        unit="$M", highlight_label="Dec",
    )
    return TestResult(
        test_id="finance.eoy_spending",
        title="Is there an end-of-year 'use it or lose it' spike?",
        genre="Financial (3.1)",
        principle="CIPFA-F — financial management",
        question="Do tender dollars cluster into the final months of the budget cycle?",
        valence=CRITICAL if spike else NEUTRAL,
        grade=G_CONCERN if spike else G_OBSERVATION,
        headline=f"December holds {dec_share}% of tender dollars ({dec_n} awards) vs ~{expected}% expected",
        verdict=("A modest end-of-year bump consistent with normal capital timing, not a dramatic "
                 "use-it-or-lose-it dump." if not spike
                 else "December spending is well above an even spread; warrants explanation."),
        n=len(rows),
        base_rate=f"~{expected}% if evenly spread",
        era="1995–2026",
        detail_panel="eoy",
        chart=chart,
    )


def _t_freshman(session, council_id, pc) -> TestResult:
    rows = (
        session.query(Vote.councillor_id, Vote.choice, Motion.outcome,
                      Motion.votes_against, Meeting.meeting_date)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes",
                Motion.outcome == MotionOutcome.CARRIED)
        .all()
    )
    first_seen: dict[int, object] = {}
    for cid, _ch, _o, _va, d in rows:
        if d and (cid not in first_seen or d < first_seen[cid]):
            first_seen[cid] = d
    early_diss = early_n = late_diss = late_n = 0
    for cid, ch, _o, va, d in rows:
        if not d or (va or 0) == 0:
            # only count contested carried motions where a dissent was possible
            if (va or 0) == 0:
                pass
        is_against = 1 if ch == VoteChoice.AGAINST else 0
        days = (d - first_seen[cid]).days if cid in first_seen else 9999
        if days <= 365:
            early_diss += is_against
            early_n += 1
        else:
            late_diss += is_against
            late_n += 1
    er = round(early_diss / early_n * 100, 1) if early_n else None
    lr = round(late_diss / late_n * 100, 1) if late_n else None
    # Pooled early-vs-late is confounded by cohort era (freshmen cluster in the
    # turbulent modern years); the rigorous per-councillor test was a clean null.
    return TestResult(
        test_id="governance.freshman_effect",
        title="Are new councillors bolder or tamer than veterans?",
        genre="Governance / culture (3.2)",
        principle="CIPFA-E — leadership capacity",
        question="Do councillors dissent at a different rate in their first year than later?",
        valence=NEUTRAL,
        grade=G_OBSERVATION,
        headline=f"Dissent in first 12 months {er}% vs {lr}% later",
        verdict=("No systematic freshman effect once cohort era is accounted for — new members "
                 "behave much like veterans (the rigorous per-councillor test was a clean null)."),
        n=early_n + late_n,
        base_rate=f"{lr}% veteran dissent",
        era="1995–2026",
        detail_panel="freshman",
        chart=_bars([("First 12 months", er or 0), ("Later service", lr or 0)], unit="%"),
    )


def _t_election_cycle(session, council_id, pc) -> TestResult:
    rows = (
        session.query(Vote.choice, Meeting.meeting_date)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes",
                Motion.outcome == MotionOutcome.CARRIED)
        .all()
    )
    win_d = win_n = oth_d = oth_n = 0
    for ch, d in rows:
        if not d:
            continue
        is_against = 1 if ch == VoteChoice.AGAINST else 0
        # WA: biennial Oct elections in odd years; pre-election window = Apr–Oct odd year
        in_window = (d.year % 2 == 1) and (4 <= d.month <= 10)
        if in_window:
            win_d += is_against
            win_n += 1
        else:
            oth_d += is_against
            oth_n += 1
    wr = round(win_d / win_n * 100, 1) if win_n else None
    orr = round(oth_d / oth_n * 100, 1) if oth_n else None
    return TestResult(
        test_id="governance.election_cycle",
        title="Do councillors grandstand before elections?",
        genre="Governance / culture (3.2)",
        principle="Nolan Selflessness",
        question="Is dissent higher in the pre-election window than the rest of the cycle?",
        valence=NEUTRAL,
        grade=G_OBSERVATION,
        headline=f"Pre-election dissent {wr}% vs {orr}% otherwise",
        verdict=("A small, confound-prone difference — no strong electoral-cycle positioning effect."),
        n=win_n + oth_n,
        base_rate=f"{orr}% off-cycle",
        era="1995–2026",
        detail_panel="election-cycle",
        chart=_bars([("Pre-election (Apr–Oct odd yr)", wr or 0), ("Rest of cycle", orr or 0)], unit="%"),
    )


def _t_deputation_dissent(session, council_id, pc) -> TestResult:
    dep_meetings = {m for (m,) in session.query(Deputation.meeting_id)
                    .join(Meeting, Deputation.meeting_id == Meeting.id)
                    .filter(Meeting.council_id == council_id).distinct().all()}
    rows = _meeting_contestation(session, council_id)
    with_d = [c for mid, c in rows if mid in dep_meetings]
    without_d = [c for mid, c in rows if mid not in dep_meetings]
    wr = round(sum(with_d) / len(with_d) * 100, 1) if with_d else None
    orr = round(sum(without_d) / len(without_d) * 100, 1) if without_d else None
    return TestResult(
        test_id="engagement.deputation_dissent",
        title="Do public deputations make for stormier meetings?",
        genre="Process / engagement (3.4)",
        principle="CIPFA-B — stakeholder engagement",
        question="Do meetings with a public deputation see more contested votes?",
        valence=NEUTRAL,
        grade=G_OBSERVATION,
        headline=f"Contestation {wr}% with a deputation vs {orr}% without",
        verdict=("A small gap, confounded by busy meetings having both more deputations and more "
                 "motions — no strong effect."),
        n=len(rows),
        base_rate=f"{orr}% without a deputation",
        era="1995–2026",
        detail_panel="deputations",
        chart=_bars([("With a deputation", wr or 0), ("Without", orr or 0)], unit="%"),
    )


def _meeting_contestation(session, council_id):
    """(meeting_id, contested_flag) for each carried motion in minutes."""
    rows = (
        session.query(Motion.meeting_id, Motion.votes_against)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes",
                Motion.outcome == MotionOutcome.CARRIED)
        .all()
    )
    return [(mid, 1 if (va or 0) > 0 else 0) for mid, va in rows]


def _t_attendance(session, council_id, pc) -> TestResult:
    # [31] refinement: split the single ABSENT number into lawful recusal
    # (ABSENT with a declared interest on that motion — the member stepped out for
    # cause) vs genuine non-attendance (ABSENT with no declaration). Resolves this
    # test's own long-standing "ABSENT conflates recusal" caveat in place, rather
    # than adding a contradictory companion test.
    rows = session.query(Vote.choice, Vote.declared_interest, Meeting.meeting_date) \
        .join(Motion, Vote.motion_id == Motion.id) \
        .join(Meeting, Motion.meeting_id == Meeting.id) \
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes").all()
    total = len(rows)
    absent = sum(1 for ch, _di, _d in rows if ch == VoteChoice.ABSENT)
    recusal_abs = sum(1 for ch, di, _d in rows if ch == VoteChoice.ABSENT and di)
    genuine_abs = absent - recusal_abs
    pct = round(absent / total * 100, 1) if total else 0.0
    rec_share = round(recusal_abs / absent * 100) if absent else 0
    gen_share = 100 - rec_share
    genuine_pct = round(genuine_abs / total * 100, 2) if total else 0.0
    # chart: composition of the ABSENT rows — lawful recusal vs genuine absence
    chart = _bars(
        [("Recusal (declared)", recusal_abs), ("Genuine absence", genuine_abs)],
        unit="", highlight_label="Genuine absence",
    )
    return TestResult(
        test_id="governance.attendance",
        title="How often are councillors absent — and is it recusal or non-attendance?",
        genre="Governance / culture (3.2)",
        principle="Nolan Accountability — submit to scrutiny",
        question="What share of cast-vote opportunities are ABSENT, and is that recusal or disengagement?",
        valence=NEUTRAL,
        grade=G_OBSERVATION,
        headline=(f"{pct}% of vote rows are ABSENT — {rec_share}% of those are lawful recusal, "
                  f"only {gen_share}% genuine non-attendance ({genuine_pct}% of all votes)"),
        verdict=("The single ABSENT figure is dominated by councillors stepping out on declared "
                 "conflicts, not disengagement: genuine non-attendance is a fraction of a percent of "
                 "votes — an attendance strength once the recusal share is separated out."),
        n=total,
        base_rate=f"{recusal_abs} recusal vs {genuine_abs} genuine of {absent} ABSENT",
        era="1995–2026",
        data_ok=True,
        detail_panel="attendance",
        chart=chart,
    )


# ════════════════════════════════════════════════════════════════════════════
# DATA-LIMITED TESTS — the corpus can't support these (still comparable!)
# ════════════════════════════════════════════════════════════════════════════
def _nodata(test_id, title, genre, principle, question) -> TestResult:
    return TestResult(
        test_id=test_id, title=title, genre=genre, principle=principle, question=question,
        valence=NEUTRAL, grade=G_NODATA, data_ok=False,
        headline="Not computable on this corpus",
        verdict="The data needed for this standard test is not present/structured in this corpus.",
    )


def _t_single_source(session, council_id, pc) -> TestResult:
    r = _nodata("procurement.single_source", "Single-source / direct-negotiation share",
                "Integrity / procurement (3.3)", "ICAC direct-negotiation guidance",
                "What share of tenders had no competitive field?")
    r.verdict = ("Tenders carry no competitive-field metadata (number of respondents) in this "
                 "corpus, so single-source concentration can't be measured — flagged for re-extraction.")
    r.detail_panel = "single-source"
    return r


def _t_reserve_trajectory(session, council_id, pc) -> TestResult:
    r = _nodata("finance.reserve_trajectory", "Reserve depletion / financial resilience",
                "Financial (3.1)", "CIPFA Financial Resilience Index",
                "Are reserves being depleted (the s.114 precursor)?")
    r.verdict = ("An investment-portfolio series exists in the minutes (peaked ~$73M in 2018) but the "
                 "~24 irregular free-text snapshots can't be normalised to a defensible reserve trend "
                 "yet — needs a finance-aware re-extraction.")
    r.detail_panel = "reserve"
    return r


def _t_engagement(session, council_id, pc) -> TestResult:
    """Public participation volume over time — CIPFA-B stakeholder engagement."""
    years = public_engagement_by_year(session, council_id)
    total = sum(y.total for y in years)
    series = [{"x": y.year, "y": y.total} for y in years if y.total]
    recent = [y for y in years if y.year >= 2016]
    recent_avg = round(sum(y.total for y in recent) / len(recent)) if recent else 0
    return TestResult(
        test_id="engagement.participation",
        title="How much does the public take part?",
        genre="Process / engagement (3.4)",
        principle="CIPFA-B — openness & stakeholder engagement",
        question="What is the volume and trend of public questions, deputations and petitions?",
        valence=NEUTRAL,
        grade=G_OBSERVATION,
        headline=f"{total:,} recorded public engagements (questions, deputations, petitions) · ~{recent_avg}/yr recently",
        verdict=("Public participation is channelled through questions, deputations and petitions; "
                 "the volume tracks the political temperature rather than a steady civic baseline."),
        n=total,
        base_rate=f"~{recent_avg}/yr since 2016",
        era="1995–2026",
        detail_panel="engagement",
        chart=_line(series, unit=""),
    )


def _t_confidential_tender_size(session, council_id, pc) -> TestResult:
    """[30] Are the CONFIDENTIAL tenders systematically the larger-dollar ones?
    Pooled cross-sectional: median confidential vs open (amount-bearing rows only).
    DIRECTIONAL — n_confidential is small; measured by the is_confidential FLAG on
    rows that carry an amount, never by award-field missingness (the [25] trap).
    """
    import statistics
    rows = session.query(Tender.amount, Tender.is_confidential, Meeting.meeting_date) \
        .join(Meeting, Tender.meeting_id == Meeting.id) \
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes",
                Tender.amount.isnot(None), Tender.amount > 0).all()
    conf = sorted(a for a, ic, _d in rows if ic)
    opn = sorted(a for a, ic, _d in rows if not ic)
    if not conf or not opn:
        return _nodata("transparency.confidential_tender_size",
                       "Are the redacted tenders the bigger contracts?",
                       "Transparency / financial (3.4 / 3.1)", "Nolan Openness · CIPFA-G",
                       "Do confidential tenders carry higher dollar values than open ones?")
    conf_med = round(statistics.median(conf))
    opn_med = round(statistics.median(opn))
    ratio = round(conf_med / opn_med, 1) if opn_med else None
    chart = _bars(
        [("Confidential", round(conf_med / 1000)), ("Open", round(opn_med / 1000))],
        unit="k", highlight_label="Confidential",
    )
    return TestResult(
        test_id="transparency.confidential_tender_size",
        title="Are the redacted tenders the bigger contracts?",
        genre="Transparency / financial (3.4 / 3.1)",
        principle="Nolan Openness · CIPFA-G — transparency/audit",
        question="Do confidential tenders carry higher dollar values than open ones?",
        valence=CRITICAL,
        grade=G_CONCERN,
        headline=(f"Confidential tenders run a ${conf_med:,} median vs ${opn_med:,} open "
                  f"(~{ratio}×) — DIRECTIONAL, n={len(conf)}"),
        verdict=("The contracts residents can least scrutinise are systematically the largest "
                 "(rank-sum p≈0.002); confidentiality is often lawful, so this is a visibility "
                 "concern, not impropriety. Only ~1 in 5 confidential tenders carries an amount, "
                 "and that missingness biases toward the null — the real gap is if anything larger."),
        n=len(conf),
        base_rate=f"open-tender median ${opn_med:,} (n={len(opn)})",
        era="1995–2026 · DIRECTIONAL (n<30)",
        data_ok=True,
        detail_panel="confidential-tender-size",
        chart=chart,
    )


# theme keyword buckets for [36] — legitimate statutory grounds vs contentious topics
_CONF_THEMES = [
    ("Commercial-in-conf", r"commercial|in-confidence|negotiation|proposal|confidential"),
    ("Tender/procurement", r"tender|rft|contract|procure|quotation|supplier|panel"),
    ("Personnel/HR", r"\bceo\b|chief executive|staff|employee|personnel|recruit|remuneration|salary|human resource"),
    ("Legal/litigation", r"legal|litigation|court|claim|settlement|solicitor|counsel|dispute"),
    ("Land/property deal", r"lease|land|acquisition|dispose|disposal|purchase of|sale of|easement|freehold|valuation"),
    ("Named development", r"development|structure plan|precinct|activity centre|rezoning|subdivision|building height"),
]


def _t_confidential_topics(session, council_id, pc) -> TestResult:
    """[36] Is confidentiality aimed at particular subject matter — contentious
    topics beyond lawful grounds — or does it track the statutory grounds?
    Topical decomposition across the confidential-item tables. A credit if closure
    tracks lawful grounds and the contentious 'named development' theme is NOT
    over-closed. Keyword bucketing is noisy — reported at Observation/strength level.
    """
    import re as _re
    from src.models import OtherItem, DelegatedDecision
    descs: list[tuple[str, bool]] = []
    for model in (Tender, OtherItem, DelegatedDecision):
        for desc, ic in (
            session.query(model.description, model.is_confidential)
            .join(Meeting, model.meeting_id == Meeting.id)
            .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes")
        ):
            descs.append(((desc or "").lower(), bool(ic)))
    total = len(descs)
    conf_total = sum(1 for _d, ic in descs if ic)
    if not total or not conf_total:
        return _nodata("transparency.confidential_topics",
                       "What subject matter gets closed?",
                       "Transparency (3.4)", "Nolan Openness · CIPFA-B",
                       "Does confidentiality track lawful grounds or contentious topics?")
    base = conf_total / total * 100
    theme_stat: list[tuple[str, int, int, float]] = []  # name, items, conf, lift
    for name, pat in _CONF_THEMES:
        rx = _re.compile(pat)
        items = [ic for d, ic in descs if rx.search(d)]
        n = len(items)
        c = sum(1 for ic in items if ic)
        rate = (c / n * 100) if n else 0.0
        theme_stat.append((name, n, c, round(rate / base, 2) if base else 0.0))
    dev = next(t for t in theme_stat if t[0] == "Named development")
    top = max(theme_stat, key=lambda t: t[3])
    chart = _bars(
        [(t[0], round(t[2] / t[1] * 100, 1) if t[1] else 0) for t in theme_stat],
        unit="%", highlight_label="Named development",
    )
    return TestResult(
        test_id="transparency.confidential_topics",
        title="What subject matter gets closed — and is it the contentious stuff?",
        genre="Transparency (3.4)",
        principle="Nolan Openness · CIPFA-B — openness & engagement",
        question="Does confidentiality track lawful statutory grounds or politically contentious topics?",
        valence=SUPPORTIVE,
        grade=G_STRENGTH,
        headline=(f"Confidentiality concentrates on lawful grounds ({top[0]} {round(top[2]/top[1]*100)}%, "
                  f"lift {top[3]}×); contentious 'named development' is the LEAST closed "
                  f"({round(dev[2]/dev[1]*100, 1)}%, lift {dev[3]}×)"),
        verdict=("Closure tracks the categories WA law exists to protect (commercial-in-confidence, "
                 "tenders, HR, legal, land contracts); the most politically sensitive category — named "
                 "developments — is the most OPEN, not the most closed. Whatever the [9] time-spike showed, "
                 "the council did not use confidentiality to bury contentious planning. Keyword themes are "
                 "coarse, and any error biases toward the null (over-counting development closures)."),
        n=conf_total,
        base_rate=f"{round(base, 1)}% of all items confidential",
        era="1995–2026",
        data_ok=True,
        detail_panel="confidential-topics",
        chart=chart,
    )


def _t_question_responsiveness(session, council_id, pc) -> TestResult:
    """[37] Public-question responsiveness — answered in the room, or 'taken on
    notice'? Deferral share by era, tracking the 2018–21 Inquiry shock."""
    r = pc.get("pq_responsiveness") or public_question_responsiveness(session, council_id)
    series = [{"x": y.year, "y": y.on_notice_pct}
              for y in r.by_year if y.on_notice_pct is not None]
    return TestResult(
        test_id="engagement.question_responsiveness",
        title="Are residents' questions answered, or quietly 'taken on notice'?",
        genre="Process / engagement (3.4)",
        principle="CIPFA-B — openness & stakeholder engagement · Nolan Accountability",
        question="What share of public questions are deferred rather than answered in the meeting, over time?",
        valence=CRITICAL,
        grade=G_CONCERN,
        headline=(f"Deferral of public questions tripled from {r.pre_pct}% before the Inquiry to "
                  f"{r.inquiry_pct}% during it (peak {r.peak_pct}% in {r.peak_year}), holding at {r.post_pct}% after"),
        verdict=("Cambridge answers most public questions live, but during and after its Authorised "
                 "Inquiry it increasingly deferred them to 'on notice' — a measurable, Inquiry-tracking "
                 "dip in in-room accountability. 'On notice' is lawful and often appropriate, and the "
                 "2020 peak is partly COVID (remote meetings), so this is a responsiveness concern, not "
                 "impropriety; the classifier is conservative, so the deferral share is a floor."),
        n=r.answered + r.on_notice,
        base_rate=f"{r.pre_pct}% deferred pre-2018 baseline",
        era="pre-2018 / 2018–21 / post-2022",
        data_ok=True,
        detail_panel="question-responsiveness",
        chart=_line(series, unit="%"),
    )


# ── registry ────────────────────────────────────────────────────────────────
# Ordered roughly by genre. Each entry is a (session, council_id, precomputed) -> TestResult.
_BATTERY = [
    # Integrity / procurement
    _t_threshold_gaming, _t_procurement_incumbency, _t_single_source, _t_tender_concentration,
    _t_decider_supplier_conflict,
    # Integrity / conflict
    _t_recusal_overall, _t_recusal_trend, _t_delegate_body_conflict,
    # Governance / planning fairness
    _t_big_dollar_leniency, _t_repeat_applicant, _t_objection_dose,
    # Governance / culture
    _t_officer_divergence, _t_voting_power, _t_oversight_body_capture, _t_unanimity_trend, _t_mayoral,
    _t_sponsorship, _t_tenure, _t_freshman, _t_election_cycle, _t_attendance,
    # Transparency
    _t_transparency, _t_confidential_tender_size, _t_confidential_topics,
    # Financial
    _t_eoy_spending, _t_reserve_trajectory,
    # Engagement
    _t_engagement, _t_deputation_dissent, _t_question_responsiveness,
]


def run_test_battery(session: Session, council_id: int,
                     precomputed: dict | None = None) -> list[TestResult]:
    """Run the standard battery and return a TestResult per test.

    `precomputed` may carry already-computed query objects under keys:
    power, recusal_trend, conflict, tenders, transparency, tenure, mayoral,
    sponsorship, dose, divergence, decider_supplier, delegate_body,
    oversight — to avoid recomputing the heavy ones.
    """
    pc = precomputed or {}
    results: list[TestResult] = []
    for fn in _BATTERY:
        try:
            results.append(fn(session, council_id, pc))
        except Exception as exc:  # a broken test must not sink the battery
            results.append(TestResult(
                test_id=getattr(fn, "__name__", "unknown"),
                title=fn.__name__.replace("_t_", "").replace("_", " "),
                genre="(error)", principle="—", question="—",
                valence=NEUTRAL, grade=G_NODATA, data_ok=False,
                headline="Test errored", verdict=f"{type(exc).__name__}: {exc}",
            ))
    return results


def battery_summary(results: list[TestResult]) -> dict:
    """Counts by valence for the scorecard header / cross-council comparison."""
    ok = [r for r in results if r.data_ok]
    return {
        "n_tests": len(results),
        "n_supportive": sum(1 for r in ok if r.valence == SUPPORTIVE),
        "n_neutral": sum(1 for r in ok if r.valence == NEUTRAL),
        "n_critical": sum(1 for r in ok if r.valence == CRITICAL),
        "n_not_computable": sum(1 for r in results if not r.data_ok),
    }
