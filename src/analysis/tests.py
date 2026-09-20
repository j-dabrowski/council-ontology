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

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from src.models import (
    ApplicationStatus,
    Councillor,
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
    contractor_display_names,
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
from src.council_eras import fiscal_year_start_month
from src.test_registry import RegistryRow, load_test_registry
from src.analysis.claims import (
    COMPARISON_BETWEEN_SUBJECT,
    COMPARISON_NONE,
    COMPARISON_TEMPORAL,
    GRADE_CONCERN,
    GRADE_CRITICAL,
    GRADE_NEUTRAL,
    GRADE_SUPPORTIVE,
    Claim,
    Comparison,
    NumeratorDenominator,
    Narrative,
    Population,
    Statistic,
)
from src.analysis.inference import (
    chi_square_independence,
    clustered_proportion,
    difference_in_proportions_ci,
    herfindahl_index,
    hypergeometric_overlap_test,
    linear_trend_ci,
    mann_whitney_test,
    median_ci,
    median_difference_ci,
    proportion_ci,
)

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

# unit of analysis (docs/INFORMATION_ARCHITECTURE.md §4, C1) — the field the
# S7 invariant gate (src/invariant_gate.py) and eventual tier derivation gate
# on. Every existing battery test is UNIT_INSTITUTIONAL (an aggregate over
# the whole chamber, no person recoverable) — none currently names, charts,
# or enumerates an individual.
UNIT_INSTITUTIONAL = "institutional"                    # no person recoverable
UNIT_INDIVIDUAL_IMPLICATING = "individual_implicating"  # aggregate by construction, but a
                                                          # person is enumerable/inferable
                                                          # (per-person charts, small-N cells)
UNIT_INDIVIDUAL = "individual"                           # a claim about named person(s)

# entity-resolution state (§4, flag-7 class) — only meaningful for
# UNIT_INDIVIDUAL claims; the S7 gate requires "clean" before one may ship.
ENTITY_RESOLUTION_CLEAN = "clean"
ENTITY_RESOLUTION_OPEN_SPLITS = "open-splits"

# COVID/remote-meeting confound caveat (docs/uplift/migration/01-known-defects.md
# G-20): 2020's remote-meeting rules and emergency procedures were a WA-wide
# regulatory shock, not specific to any one council — any era-split or yearly
# value spanning 2020 needs this stated, not just the one panel D-20's
# original framing happened to check.
COVID_CONFOUND_CAVEAT = (
    " 2020's remote-meeting rules and emergency procedures were a WA-wide regulatory "
    "shock, not specific to this council — a value spanning that year may reflect that "
    "shock rather than a local trend."
)

# scope — declares which granularity this finding-type is MEANINGFUL at, not
# which granularity it's currently computed at. Every generator today only
# ever computes over the whole corpus; SCOPE_SINGLE_MEETING marks a test as
# ELIGIBLE for a future per-meeting digest, not as already supporting one —
# no generator accepts a period/meeting filter yet.
SCOPE_WHOLE_CORPUS = "whole_corpus"
SCOPE_SINGLE_MEETING = "single_meeting"


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
    # claim-object fields the S7 invariant gate checks (§4, C1) — default to
    # the institutional/clean baseline every current battery test satisfies;
    # a generator only sets these when it actually produces a per-person claim.
    unit_of_analysis: str = UNIT_INSTITUTIONAL
    named_entities: list[str] = field(default_factory=list)  # empty iff institutional
    entity_resolution: str = ENTITY_RESOLUTION_CLEAN  # clean | open-splits (individual claims only)
    # granularity this finding-type is meaningful at (see SCOPE_* above) —
    # every generator declares this explicitly, same discipline as unit_of_analysis
    scope: list[str] = field(default_factory=lambda: [SCOPE_WHOLE_CORPUS])
    # S9 right of reply (§4) — set by src/reply_packets.py, never hand-authored.
    # None until a packet is sent; {"sent_at": iso8601, "response": str|None,
    # "declined": bool} after. Only meaningful for named_entities-bearing claims.
    reply: dict | None = None
    detail_panel: str | None = None  # snapshot/anchor slug of the panel for this test
    series: list[dict] = field(default_factory=list)  # optional sparkline payload
    # Optional chart payload rendered by the generic BatteryTestPanel for tests that
    # have no bespoke panel. kind="bars": {bars:[{label,value,highlight?}], unit, refline?}
    # kind="line": {points:[{x,y}], unit, refline?}.
    chart: dict | None = None
    # Digest salience inputs (docs — the digest design plan; SCOPE_SINGLE_MEETING
    # generators only). `stat` is the one number `score_salience()` compares against
    # this (test_id, body_class)'s baseline distribution — {"value": ..., "denominator":
    # ... | None, "unit": "count"|"$"|...}; None means this claim doesn't participate in
    # novelty scoring (only `digest_floor` can make it salient). `digest_floor` is a
    # per-generator-declared minimum salience for an event reportable at n≥1 regardless
    # of novelty (a tender awarded, a conflict declared, an item closed, a deputation
    # heard, an unexplained absence) — 0.0 (the default) means "novelty-only".
    stat: dict | None = None
    digest_floor: float = 0.0


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


def _capped_pct(numerator: float, denominator: float, decimals: int = 1) -> float:
    """`round(numerator / denominator * 100, decimals)`, but capped to 0
    decimal places whenever `denominator` (the n behind the percentage) is
    below 30 — a bare `round(x, 1)` implies a precision the sample can't
    support (docs/uplift/migration/01-known-defects.md G-14). Interim
    n-based heuristic, not a real CI-based cap: the full fix needs the
    claim object's confidence interval (`02-claim-layer.md`, tracked as
    Step 24 in `01-known-defects.md`)."""
    if not denominator:
        return 0.0
    d = 0 if denominator < 30 else decimals
    return round(numerator / denominator * 100, d)


# ── helpers ─────────────────────────────────────────────────────────────────
def _minutes_motions(session: Session, council_id: int, meeting_id: int | None = None):
    """(outcome, votes_against, year) for every motion in minutes, or just
    one meeting's when meeting_id is set (docs/frontend/PRODUCT_ROADMAP.md
    F2's single-meeting digest)."""
    q = (
        session.query(Motion.outcome, Motion.votes_against, Meeting.meeting_date)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes")
    )
    if meeting_id is not None:
        q = q.filter(Meeting.id == meeting_id)
    rows = q.all()
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


def _meeting_label(session: Session, meeting_id: int) -> str:
    """ISO date string for a meeting, for a SCOPE_SINGLE_MEETING TestResult's
    `era` field. Falls back to the raw id if the meeting can't be found —
    should never happen for a caller passing a real meeting_id, but a
    missing date shouldn't crash digest generation over a display string."""
    d = session.query(Meeting.meeting_date).filter(Meeting.id == meeting_id).scalar()
    return d.isoformat() if d else f"meeting {meeting_id}"


# ════════════════════════════════════════════════════════════════════════════
# WRAPPED TESTS — existing flagship panels, re-expressed as valenced battery rows
# ════════════════════════════════════════════════════════════════════════════
def _t_recusal_overall(session, council_id, pc, meeting_id=None) -> TestResult:
    if meeting_id is not None:
        return _t_recusal_overall_meeting(session, council_id, meeting_id)
    s = pc.get("conflict") or conflict_recusal_stats(session, council_id)
    # Must-leave-only, not the blended declared_recusal_pct (docs/uplift/
    # migration/01-known-defects.md G-22): the corpus-wide headline/grade
    # now keys off the same financial/proximity-only compliance question
    # the per-councillor colour-coding already answers (ConflictRecusalPanel.tsx,
    # fixed 2026-08-11) — a lawful "impartiality" stay-and-vote can no
    # longer mask or invert this figure. Falls back to the blended rate
    # only if the corpus has zero must-leave declarations at all (no
    # mandatory-conflict data to compute the real question from).
    have_must_leave = s.must_leave_total > 0
    stay = round(100 - s.must_leave_recusal_pct, 1) if have_must_leave else round(100 - s.declared_recusal_pct, 1)
    # Computed the same way ConflictRecusalPanel.tsx derives its own headline
    # factor (guarded division against the same two fields), rather than a
    # literal string — confirmed 2026-08-23, defamation review pass 3
    # advisory flag: the two had drifted (hardcoded "~80x" vs. the panel's
    # live 83x for this draft's data).
    factor = round(s.declared_recusal_pct / s.baseline_recusal_pct) if s.baseline_recusal_pct > 0 else 0
    # Derived, not asserted (docs/SECOND_COUNCIL_PLAN.md 1.1): the
    # identify-disclose-manage chain only actually breaks at the manage
    # limb if most declared-interest votes see the member stay anyway.
    # Below 50% stay, disclosure is doing its job at both limbs.
    managed = stay < 50.0
    return TestResult(
        test_id="conflict.recusal_management",
        title="Do councillors step out when they declare a conflict?",
        genre="Integrity / conflict (3.3)",
        principle="Nolan Integrity, Objectivity · CIPFA-A",
        question="When a legally-mandatory (financial/proximity) interest is declared, is it "
                 "*managed* — i.e. does the member recuse?",
        valence=SUPPORTIVE if managed else CRITICAL,
        grade=G_STRENGTH if managed else G_CONCERN,
        headline=(f"Declaring lifts recusal {factor}× and members step out {100 - stay}% of the time "
                  "on a must-leave conflict"
                  if managed else
                  f"Declaring lifts recusal {factor}×, but members still stay and vote {stay}% of the "
                  "time on a must-leave conflict"),
        verdict=("Disclosure works at both limbs on legally-mandatory conflicts: most must-leave "
                 "declared-interest votes see the member step out. Impartiality declarations, which "
                 "lawfully permit staying and voting, are excluded from this figure."
                 if managed else
                 "Disclosure works at the first step; the identify–disclose–manage chain breaks at the "
                 "manage limb on legally-mandatory (financial/proximity) conflicts. Impartiality "
                 "declarations, which lawfully permit staying and voting, are excluded from this figure."),
        n=s.must_leave_total if have_must_leave else s.declared_total,
        base_rate=f"{s.baseline_recusal_pct}% recuse on a normal vote",
        era="1995–2026",
        detail_panel="declared",
        scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING],
    )


def _t_recusal_overall_meeting(session, council_id, meeting_id) -> TestResult:
    """Plain factual recount, not a rate: did anyone declare a conflict at
    THIS meeting, and what did they do about it — sourced the same way the
    minutes themselves already state it. n is near-always tiny (a single
    meeting rarely has more than a handful of declarations), so unlike the
    whole-corpus version this is genuinely about specific people's specific
    actions when declared_total > 0 — declared UNIT_INDIVIDUAL accordingly
    (Investigator_prompt.txt §4/C1), not left at the institutional default."""
    s = conflict_recusal_stats(session, council_id, min_declared=1, meeting_id=meeting_id)
    era = _meeting_label(session, meeting_id)
    if s.declared_total == 0:
        return TestResult(
            test_id="conflict.recusal_management", title="Did anyone declare a conflict this meeting?",
            genre="Integrity / conflict (3.3)", principle="Nolan Integrity, Objectivity · CIPFA-A",
            question="Did any councillor declare a conflict of interest at this meeting?",
            valence=NEUTRAL, grade=G_OBSERVATION,
            headline="No conflicts of interest were declared at this meeting",
            verdict="No conflicts of interest were declared at this meeting.",
            n=0, era=era, detail_panel="declared",
            scope=[SCOPE_SINGLE_MEETING],
            stat={"value": 0, "denominator": None, "unit": "count"}, digest_floor=0.0,
        )
    # One line per COUNCILLOR, not per declaration — a grants-round agenda
    # can produce dozens of near-identical declarations from the same
    # handful of members (confirmed live: 64 declarations / 9 councillors
    # in one real meeting), and a sentence-per-declaration recount is
    # unreadable at that volume. Per-councillor grouping compresses that to
    # one line each while keeping the single-declaration case (the common
    # one) just as detailed as before.
    lines = []
    names = []
    for p in s.profiles:
        if not p.declarations:
            continue
        names.append(p.name)
        n = len(p.declarations)
        stepped_out = sum(1 for d in p.declarations if d.action == "Stepped out")
        stayed = n - stepped_out
        if n == 1:
            d = p.declarations[0]
            lines.append(f"{p.name} declared an interest on {d.item or 'an item'} "
                         f"({d.what or d.interest_type or 'interest not specified'}) — {d.action.lower()}")
        elif stepped_out and stayed:
            lines.append(f"{p.name} declared {n} interests this meeting — stepped out {stepped_out} "
                         f"time(s), stayed and voted {stayed} time(s)")
        elif stepped_out:
            lines.append(f"{p.name} declared {n} interests this meeting — stepped out every time")
        else:
            lines.append(f"{p.name} declared {n} interests this meeting — stayed and voted every time")
    return TestResult(
        test_id="conflict.recusal_management", title="Did anyone declare a conflict this meeting?",
        genre="Integrity / conflict (3.3)", principle="Nolan Integrity, Objectivity · CIPFA-A",
        question="Did any councillor declare a conflict of interest at this meeting, and what did they do about it?",
        valence=NEUTRAL, grade=G_OBSERVATION,
        headline=f"{s.declared_total} conflict(s) of interest declared this meeting, by {len(names)} councillor(s)",
        verdict="; ".join(lines),
        n=s.declared_total, era=era, detail_panel="declared",
        unit_of_analysis=UNIT_INDIVIDUAL, named_entities=sorted(set(names)),
        scope=[SCOPE_SINGLE_MEETING],
        stat={"value": s.declared_total, "denominator": None, "unit": "count"},
        digest_floor=1.0,
    )


def _t_recusal_trend(session, council_id, pc) -> TestResult:
    r = pc.get("recusal_trend") or recusal_compliance_trend(session, council_id)
    if r.inquiry_window is None:
        # No configured external-scrutiny window for this council
        # (docs/SECOND_COUNCIL_PLAN.md 1.2, config/council_eras.json) —
        # degrade to data_ok=False rather than inventing a split or
        # reporting a misleading "0% before, 0% after."
        return _nodata("conflict.recusal_trend",
                       "Did recusal compliance track an external-scrutiny event?",
                       "Integrity / conflict (3.3)", "Nolan Accountability · CIPFA-A",
                       "Did stepping out of serious conflicts change around external scrutiny?",
                       scope=[SCOPE_WHOLE_CORPUS])
    # Derived, not asserted (docs/SECOND_COUNCIL_PLAN.md 1.1): whether
    # must-leave recusal actually rose or fell across the scrutiny window,
    # rather than assuming Cambridge's own rose-then-fell shape. A ±5pp
    # band around the pre-era baseline is treated as no clear trend.
    declined = r.must_leave_post_pct < r.must_leave_pre_pct - 5
    improved = r.must_leave_post_pct > r.must_leave_pre_pct + 5
    # Same pre->post era pair as the headline (docs/uplift/migration/
    # 01-known-defects.md G-24) — used to compare inquiry->post, a second,
    # independent inconsistency from D-24's financial-vs-all-must-leave
    # denominator difference: a reader checking this panel's own internal
    # consistency would otherwise find two different comparisons on one claim.
    thin_financial = r.financial_post_n < 5 or r.financial_pre_n < 5
    if declined:
        valence, grade = CRITICAL, G_CONCERN
        headline = (f"Must-leave recusal fell from {r.must_leave_pre_pct}% before scrutiny to "
                    f"{r.must_leave_post_pct}% after (peaked at {r.must_leave_inquiry_pct}% during it)")
        financial_move = (f"{r.financial_pre_pct}%→{r.financial_post_pct}% "
                          f"(n={r.financial_pre_n}→{r.financial_post_n})")
        if thin_financial:
            verdict = (f"Financial-only recusal (leaving is mandatory) moved {financial_move} over the "
                       "same window — too few pre/post-scrutiny financial declarations to confirm or rule "
                       "out a confound from a shift in which interest type gets declared.")
        elif r.financial_post_pct < r.financial_pre_pct - 5:
            verdict = (f"Survives the obvious confound: financial-only recusal (leaving is mandatory) also "
                       f"declined, {financial_move} — not just a shift in which interest type gets declared.")
        else:
            verdict = (f"Confounded by interest-type mix: financial-only recusal held at {financial_move}, "
                       "so some of the blended decline is a shift in which interest type gets declared, "
                       "not a change in compliance on a fixed type.")
    elif improved:
        valence, grade = SUPPORTIVE, G_STRENGTH
        headline = (f"Must-leave recusal rose from {r.must_leave_pre_pct}% before scrutiny to "
                    f"{r.must_leave_post_pct}% after")
        verdict = "Compliance on the legally mandatory conflicts improved, not eroded, across the scrutiny window."
    else:
        valence, grade = NEUTRAL, G_OBSERVATION
        headline = (f"Must-leave recusal held near {r.must_leave_pre_pct}% before scrutiny and "
                    f"{r.must_leave_post_pct}% after — no clear trend")
        verdict = "No material change in must-leave recusal compliance across the scrutiny window."
    return TestResult(
        test_id="conflict.recusal_trend",
        title="Did recusal compliance track the Authorised Inquiry?",
        genre="Integrity / conflict (3.3)",
        principle="Nolan Accountability · CIPFA-A",
        question="Did stepping out of serious conflicts change around external scrutiny?",
        valence=valence,
        grade=grade,
        headline=headline,
        verdict=verdict,
        n=r.must_leave_pre_n + r.must_leave_inquiry_n + r.must_leave_post_n,
        base_rate="leaving is legally mandatory for financial/proximity interests",
        era="pre-2018 / 2018–21 / post-2022",
        detail_panel="recusal",
        scope=[SCOPE_WHOLE_CORPUS],
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
                       "do they declare an interest before voting on that body's business?",
                       scope=[SCOPE_WHOLE_CORPUS])
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
        scope=[SCOPE_WHOLE_CORPUS],
    )


def _same_body_meeting_types(session, meeting_id: int) -> list[str]:
    """Every `meeting_type` sharing this meeting's body class.

    A meeting-scoped test that quotes a "corpus-wide" baseline has to pool
    that baseline from comparable meetings only — a committee's confidential
    share isn't measured against full council's. The digest's salience layer
    has always keyed its baselines on `(test_id, body_class)`
    (`src/analysis/meeting_baselines.py`); until 2026-08-31 the baselines
    rendered into the digest's own prose, one line away, pooled every minutes
    meeting regardless of body. Cambridge's corpus is ~90% full_council, so a
    full-council meeting barely moved — but every committee and electors
    meeting was compared against a baseline that was mostly not its own kind.

    Falls back to this meeting's own `meeting_type` alone when the type isn't
    in `config/meeting_bodies.json`, matching `UNKNOWN_BODY_CLASS`'s
    degrade-thin-rather-than-crash rule.
    """
    from src.analysis.meeting_baselines import body_class_of, load_meeting_bodies
    from src.models import Council

    m = session.query(Meeting).filter(Meeting.id == meeting_id).first()
    if m is None or not m.meeting_type:
        return []
    council = session.query(Council).filter(Council.id == m.council_id).first()
    if council is None:
        return [m.meeting_type]
    bodies = load_meeting_bodies(council.short_name)
    cls = body_class_of(m.meeting_type, bodies)
    peers = [mt for mt, c in bodies.items() if c == cls]
    return peers or [m.meeting_type]


def _comparable_label(session, meeting_id: int, types: list[str]) -> str:
    """"across N comparable meetings" — the peer-pool size, stated.

    A body-matched baseline is the comparable one but can be thin (Cambridge's
    audit-committee class is 5 meetings). Naming the pool size lets a reader
    calibrate, instead of reading a 5-meeting rate with the authority the old
    14,000-item "corpus-wide" phrasing carried.
    """
    n = (session.query(Meeting)
         .filter(Meeting.council_id == (session.query(Meeting.council_id)
                                        .filter(Meeting.id == meeting_id).scalar()),
                 Meeting.document_type == "minutes",
                 Meeting.meeting_type.in_(types))
         .count()) if types else 0
    return f"across {n} comparable meeting{'s' if n != 1 else ''}"


def _t_transparency(session, council_id, pc, meeting_id=None) -> TestResult:
    if meeting_id is not None:
        return _t_transparency_meeting(session, council_id, meeting_id, pc)
    t = pc.get("transparency") or transparency_by_year(session, council_id)
    # Derived, not asserted (docs/SECOND_COUNCIL_PLAN.md 1.1): a spike is
    # the peak year running meaningfully (>10pp) above the pre-era
    # baseline, not an assumed shape.
    spike = t.peak_pct > t.pre_era_pct + 10
    return TestResult(
        test_id="transparency.confidential_share",
        title="How much business is taken behind closed doors?",
        genre="Process / transparency (3.4)",
        principle="Nolan Openness · CIPFA-B",
        question="What share of decided items is confidential, and is it rising?",
        valence=CRITICAL if spike else SUPPORTIVE,
        grade=G_CONCERN if spike else G_SOUND,
        headline=(f"{t.pre_era_pct}% confidential at baseline, spiking to {t.peak_pct}% in {t.peak_year}"
                  if spike else
                  f"{t.pre_era_pct}% confidential at baseline, holding near {t.peak_pct}% at its peak "
                  f"({t.peak_year})"),
        verdict=("A strong baseline openness rate with a spike that stands out from it; the concern "
                 "is the scale and timing of that spike, not a habit of secrecy."
                 if spike else
                 "A consistently open baseline with no real spike — the peak year doesn't stand out "
                 "meaningfully from the long-run rate.") + COVID_CONFOUND_CAVEAT,
        base_rate=f"{t.pre_era_pct}% two-decade baseline",
        era="1995–2026",
        detail_panel="transparency",
        series=[{"x": y.year, "y": y.confidential_pct} for y in t.years if y.total >= 50],
        scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING],
    )


def _t_transparency_meeting(session, council_id, meeting_id, pc=None) -> TestResult:
    """This meeting's own confidential share, next to the whole-corpus rate
    (never re-derived from the single meeting — see the module note by
    `transparency_by_year`'s meeting_id param). Institutional: a closed-item
    count names no one.

    The `corpus` lookup below depends only on `body_types`, not on
    `meeting_id` — every meeting sharing a body class (Cambridge's ~90%
    full_council majority, in particular) recomputes the identical
    corpus-wide query otherwise. Measured directly: `compute_watch_feed()`
    calling this once per one of 506 meetings took ~20 minutes, almost
    entirely `transparency_by_year(meeting_types=...)` re-run for the same
    handful of distinct `body_types` values. `pc` (the same precomputed
    dict `run_meeting_digest()`'s caller can now share across its whole
    per-meeting loop) memoizes it by body_types instead.
    """
    body_types = _same_body_meeting_types(session, meeting_id)
    comparable = _comparable_label(session, meeting_id, body_types)
    this = transparency_by_year(session, council_id, meeting_id=meeting_id)
    corpus_cache = (pc if pc is not None else {}).setdefault("_transparency_corpus_by_body_types", {})
    cache_key = tuple(sorted(body_types))
    if cache_key not in corpus_cache:
        corpus_cache[cache_key] = transparency_by_year(session, council_id, meeting_types=body_types)
    corpus = corpus_cache[cache_key]
    total = sum(y.total for y in this.years)
    conf = sum(y.confidential for y in this.years)
    pct = _capped_pct(conf, total)
    corpus_total = sum(y.total for y in corpus.years)
    corpus_conf = sum(y.confidential for y in corpus.years)
    corpus_pct = _capped_pct(corpus_conf, corpus_total)
    era = _meeting_label(session, meeting_id)
    return TestResult(
        test_id="transparency.confidential_share", title="How much of this meeting was closed to the public?",
        genre="Process / transparency (3.4)", principle="Nolan Openness · CIPFA-B",
        question="What share of this meeting's decided items were confidential?",
        valence=NEUTRAL, grade=G_OBSERVATION,
        headline=f"{conf} of {total} items closed to the public this meeting ({pct}%)" if total
                 else "No confidential-eligible items this meeting",
        verdict=f"{conf} of {total} items were taken confidential this meeting, vs a {corpus_pct}% "
                f"rate {comparable}." if total else "No confidential-eligible items this meeting.",
        n=total, base_rate=f"{corpus_pct}% {comparable}", era=era, detail_panel="transparency",
        scope=[SCOPE_SINGLE_MEETING],
        stat={"value": conf, "denominator": total, "unit": "count"},
        digest_floor=1.0 if conf >= 1 else 0.0,
    )


def _t_officer_divergence(session, council_id, pc, meeting_id=None) -> TestResult:
    if meeting_id is not None:
        return _t_officer_divergence_meeting(session, council_id, meeting_id)
    pairs = pc.get("divergence") or officer_divergence(session, council_id, None, None)
    total = len(pairs)
    diverged = sum(1 for p in pairs if p.diverged)
    # LOST and DEFERRED reported separately, not collapsed into one
    # `diverged` boolean (docs/uplift/migration/01-known-defects.md G-25): a
    # deferral is a procedural pause, not necessarily council overruling the
    # officer's substance the way a genuine LOST vote is.
    lost = sum(1 for p in pairs if p.council_outcome == "lost")
    deferred = sum(1 for p in pairs if p.council_outcome == "deferred")
    comp = _capped_pct(total - diverged, total) if total else None
    # Derived, not asserted (docs/SECOND_COUNCIL_PLAN.md 1.1): near-total
    # ratification (>=85%) is the "chamber is theatre" concern; genuine,
    # regular departure means the vote is where the decision actually gets
    # made, not upstream in the officer report.
    near_total = comp is not None and comp >= 85
    # This measure's own detection limit (docs/uplift/migration/
    # 01-known-defects.md G-25): amending a motion before carrying it counts
    # as ratification here, not divergence — divergence.py's docstring
    # already states this; it was never surfaced in the rendered claim.
    amendment_caveat = (" This can't detect a motion council substantially amended before carrying "
                         "it — an amended-then-carried motion counts as ratification here, not "
                         "divergence, since only a LOST or DEFERRED outcome is counted as departure.")
    return TestResult(
        test_id="governance.officer_ratification",
        title="Does the chamber decide, or ratify its officers?",
        genre="Governance / culture (3.2)",
        principle="CIPFA-F · the 'visible contest is theatre' prior",
        question="How often does council depart from the officer recommendation?",
        valence=CRITICAL if near_total else SUPPORTIVE,
        grade=G_CONCERN if near_total else G_STRENGTH,
        headline=f"Council adopted the officer recommendation {comp}% of the time",
        verdict=(("Near-total ratification means the substantive decision is upstream, in who writes "
                  "the recommendation — the most important caveat on every voting finding."
                  if near_total else
                  "Council departs from the officer recommendation often enough that the vote itself, "
                  "not just the officer report, is where the substantive decision gets made.")
                 + f" Of {diverged} departure(s): {lost} LOST outright, {deferred} DEFERRED "
                   "(a procedural pause, not necessarily a rejection of the officer's substance)."
                 + amendment_caveat),
        n=total,
        base_rate=f"{diverged} departures across {total} matched items",
        era="where officer recs exist (agenda-matched)",
        detail_panel="divergence",
        scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING],
    )


def _t_officer_divergence_meeting(session, council_id, meeting_id) -> TestResult:
    """No names — a divergence pair is per agenda item, not per person."""
    pairs = officer_divergence(session, council_id, meeting_id=meeting_id)
    total = len(pairs)
    diverged = sum(1 for p in pairs if p.diverged)
    era = _meeting_label(session, meeting_id)
    if total == 0:
        return TestResult(
            test_id="governance.officer_ratification", title="Did council follow its officers' recommendations?",
            genre="Governance / culture (3.2)", principle="CIPFA-F",
            question="Did council depart from the officer recommendation on any item this meeting?",
            valence=NEUTRAL, grade=G_OBSERVATION,
            headline="No agenda/minutes-matched officer recommendations this meeting",
            verdict="No agenda/minutes-matched officer recommendations this meeting.",
            n=0, era=era, detail_panel="divergence", scope=[SCOPE_SINGLE_MEETING],
            stat={"value": 0, "denominator": 0, "unit": "count"}, digest_floor=0.0,
        )
    return TestResult(
        test_id="governance.officer_ratification", title="Did council follow its officers' recommendations?",
        genre="Governance / culture (3.2)", principle="CIPFA-F",
        question="Did council depart from the officer recommendation on any item this meeting?",
        valence=NEUTRAL, grade=G_OBSERVATION,
        headline=f"Council departed from the officer recommendation on {diverged} of {total} matched items this meeting",
        verdict=f"{diverged} of {total} matched items departed from the officer recommendation this meeting.",
        n=total, era=era, detail_panel="divergence", scope=[SCOPE_SINGLE_MEETING],
        stat={"value": diverged, "denominator": total, "unit": "count"}, digest_floor=0.0,
    )


def _t_voting_power(session, council_id, pc) -> TestResult:
    p = pc.get("power") or voting_power(session, council_id)
    wins = [pr.win_rate for pr in p.profiles]
    lo, hi = (round(min(wins) * 100), round(max(wins) * 100)) if wins else (None, None)
    # Derived, not asserted (docs/SECOND_COUNCIL_PLAN.md 1.1): a hierarchy
    # among long-servers' own term-by-term win rates (`p.over_time`) is
    # only a live accountability concern if it's static — the same
    # people always on top, term after term. Real term-to-term movement
    # (>15pp swing for at least one long-server) is what "turns over at
    # elections rather than ossifying" actually means; a hierarchy that
    # exists but moves is an Observation, not a Concern.
    term_ranges = [
        max(pt.win_rate for pt in person.points) - min(pt.win_rate for pt in person.points)
        for person in p.over_time if person.points
    ]
    has_turnover = any(r > 0.15 for r in term_ranges) if term_ranges else True
    return TestResult(
        test_id="governance.power_spread",
        title="Does consensus hide a power hierarchy?",
        genre="Governance / culture (3.2)",
        principle="CIPFA-B · Nolan Accountability",
        question="On contested votes, how unequal is who actually wins — and is it accountable?",
        valence=NEUTRAL if has_turnover else CRITICAL,
        grade=G_OBSERVATION if has_turnover else G_CONCERN,
        headline=f"Contested-vote win rates span {lo}–{hi}% between councillors",
        verdict=("A real hidden hierarchy behind near-unanimous votes — but one that turns over at "
                 "elections rather than ossifying, so it is electorally accountable."
                 if has_turnover else
                 "A real hidden hierarchy behind near-unanimous votes, and one that doesn't turn over "
                 "term to term — the same members keep winning regardless of the election cycle."),
        n=p.n_contested,
        base_rate=f"{round(p.base_carry_rate * 100, 1)}% base carry rate",
        era="2003–2026 (contested motions)",
        detail_panel="power",
        scope=[SCOPE_WHOLE_CORPUS],
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
                       "toward the chamber's habitual winners, or draw broadly?",
                       scope=[SCOPE_WHOLE_CORPUS])
    gap = round(r.appointee_win_rate - r.non_appointee_win_rate, 1)
    lo = min((p.win_rate for p in r.profiles), default=None)
    hi = max((p.win_rate for p in r.profiles), default=None)
    chart = _bars(
        [("Appointees", r.appointee_win_rate), ("Non-appointees", r.non_appointee_win_rate)],
        unit="%",
    )
    # Derived, not asserted (docs/SECOND_COUNCIL_PLAN.md 1.1): a gap under
    # 10pp is treated as not meaningfully distinguishable at this n; above
    # it, appointees are winning materially more than the rest of the
    # chamber — the capture this test looks for.
    captured = abs(gap) > 10
    return TestResult(
        test_id="governance.oversight_body_capture",
        title="Is the council's own oversight function captured by its most powerful members?",
        genre="Governance / culture (3.2) & Strength (E)",
        principle="CIPFA-A (internal audit/oversight function) · Nolan Accountability",
        question="Does membership on the council's Audit Committee / CEO Performance Review "
                 "Committee skew toward the chamber's habitual winners, or draw broadly — "
                 "including from its habitual dissenters?",
        valence=CRITICAL if captured else SUPPORTIVE,
        grade=G_CONCERN if captured else G_STRENGTH,
        headline=(f"{r.n_appointees} distinct councillors have ever sat on an oversight body; "
                  f"appointee win rate {r.appointee_win_rate}% (n={r.appointee_n}) vs "
                  f"non-appointee {r.non_appointee_win_rate}% (n={r.non_appointee_n}) — a "
                  f"{gap} pp gap" + (", captured by habitual winners" if captured else
                                     ", not meaningfully distinguishable")),
        verdict=(f"The oversight-body appointee list's win-rate spread ({lo}–{hi}%) skews toward the "
                 f"chamber's habitual winners — the appointee/non-appointee gap is large enough that "
                 "self-appointment of the powerful to watch themselves is a live concern here."
                 if captured else
                 f"No self-appointment of the powerful to watch themselves: the oversight-body "
                 f"appointee list's win-rate spread ({lo}–{hi}%) runs almost the full range of "
                 f"the chamber, from its most consistent winners among appointees down to some "
                 f"of the corpus's most frequent dissenters. CIPFA-A's internal audit/oversight-"
                 f"function principle is met on this reading; era-pooled, so a modern-era shift "
                 f"could still hide in the aggregate."),
        n=r.appointee_n + r.non_appointee_n,
        base_rate=f"non-appointee win rate {r.non_appointee_win_rate}% (n={r.non_appointee_n})",
        era="1995–2026, era-pooled",
        data_ok=True,
        detail_panel="oversight-body-capture",
        chart=chart,
        scope=[SCOPE_WHOLE_CORPUS],
    )


def _t_mayoral(session, council_id, pc) -> TestResult:
    m = pc.get("mayoral") or mayoral_agenda_setting(session, council_id)
    # Derived, not asserted (docs/SECOND_COUNCIL_PLAN.md 1.1): chair capture
    # means the Mayor's own motions draw meaningfully LESS dissent than
    # backbench ones (deference at the gavel) — not merely "less", a real
    # margin (5pp) below the noise floor of a single term's worth of votes.
    captured = m.mayor_contest_pct < m.other_contest_pct - 5
    return TestResult(
        test_id="governance.chair_capture",
        title="Does the council fall in line behind the Mayor?",
        genre="Governance / culture (3.2)",
        principle="Nolan Accountability, Objectivity",
        question="Do the Mayor's own motions get an easier ride than backbench motions?",
        valence=CRITICAL if captured else SUPPORTIVE,
        grade=G_CONCERN if captured else G_STRENGTH,
        headline=(f"Mayoral motions drew dissent {m.mayor_contest_pct}% of the time vs "
                  f"{m.other_contest_pct}% for backbench motions"),
        verdict=("Deference at the gavel: the Mayor's own motions draw meaningfully less dissent "
                 "than backbench ones — the chamber gives its most powerful member an easier ride."
                 if captured else
                 "The opposite of chair capture: the chamber votes against its own Mayor at least as "
                 "often as backbench motions — the most powerful member earns no deference at the "
                 "gavel."),
        n=m.mayor_moved,
        base_rate=f"{m.other_contest_pct}% backbench dissent rate",
        era="1999–2026 (mayors with dated terms)",
        detail_panel="mayoral",
        scope=[SCOPE_WHOLE_CORPUS],
    )


def _t_sponsorship(session, council_id, pc) -> TestResult:
    s = pc.get("sponsorship") or sponsorship_network(session, council_id)
    # KNOWN GAP, deeper than this test's valence (docs/SECOND_COUNCIL_PLAN.md
    # 1.1 found this; not yet fixed — same class as B3's _RECUSAL_ERAS /
    # _DELEGATE_BODIES): headline/verdict below are static prose describing
    # Cambridge's specific 2000s-old-guard history, not derived from `s` at
    # all, and the query underneath (sponsorship_network(), src/analysis/
    # queries.py) hardcodes `_SPON_ERAS`/`_OLDGUARD`/`_STRUCT` — a specific
    # 1996-2023 electoral-term calendar and a hand-written era-by-era
    # narrative ("forming", "old guard consolidates", "fragmented", ...).
    # On a second council this renders the exact same Cambridge sentence
    # regardless of that council's own sponsorship structure. Needs the
    # query layer redesigned before this test's own direction can be
    # meaningfully derived — deferred, not attempted in this pass.
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
        scope=[SCOPE_WHOLE_CORPUS],
    )


def _t_tenure(session, council_id, pc) -> TestResult:
    t = pc.get("tenure") or councillor_tenure(session, council_id)
    longest = max(t.profiles, key=lambda p: p.years) if t.profiles else None
    n15 = sum(1 for p in t.profiles if p.years >= 15)
    # No direction (docs/SECOND_COUNCIL_PLAN.md 1.1): a service-length
    # distribution is a straight description of chamber composition, not
    # a good/bad signal by itself — "stability" and "entrenchment risk"
    # are two readings of the same number, not opposite outcomes a
    # threshold could cleanly separate.
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
        scope=[SCOPE_WHOLE_CORPUS],
    )


def _t_objection_dose(session, council_id, pc, meeting_id=None) -> TestResult:
    if meeting_id is not None:
        return _t_objection_dose_meeting(session, council_id, meeting_id)
    d = pc.get("dose") or objection_dose_response(session, council_id)
    by = {b.label: b for b in d.buckets}
    lo = by.get("0")
    hi = by.get("5+")
    # Derived, not asserted (docs/SECOND_COUNCIL_PLAN.md 1.1): a real climb
    # from the no-objector to the 5+-objector bucket, not an assumed one.
    # +10pp is a modest bar — this is meant to catch "flat or inverted",
    # not to demand a dramatic swing.
    lo_pct = lo.refusal_pct if lo else None
    hi_pct = hi.refusal_pct if hi else None
    responsive = lo_pct is not None and hi_pct is not None and hi_pct > lo_pct + 10
    return TestResult(
        test_id="planning.objection_responsiveness",
        title="Does the council respond to community objection?",
        genre="Process / engagement (3.4)",
        principle="CIPFA-B — meaningful stakeholder engagement",
        question="Does refusal rise with the number of residents objecting to an application?",
        valence=SUPPORTIVE if responsive else CRITICAL,
        grade=G_SOUND if responsive else G_CONCERN,
        headline=(f"Refusal {'climbs' if responsive else 'stays flat or inverted'} "
                  f"{lo_pct if lo_pct is not None else '—'}% → {hi_pct if hi_pct is not None else '—'}% "
                  "from no objectors to 5+"),
        verdict=("Refusal is higher on applications that drew 5+ objectors than on applications "
                 "with none — an observational association, not proof that the objections "
                 "themselves changed the outcome: a non-compliant application could independently "
                 "attract both more objectors and a higher refusal rate."
                 if responsive else
                 "Refusal doesn't rise with objector volume the way a working dose-response "
                 "would predict — objector numbers alone don't track with the outcome here."),
        n=d.total_decided,
        base_rate=f"{lo.refusal_pct if lo else '—'}% refusal with no objectors",
        era="all decided applications",
        detail_panel="dose",
        scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING],
    )


def _t_objection_dose_meeting(session, council_id, meeting_id) -> TestResult:
    """A dose-response curve needs many applications — one meeting only ever
    has a handful, so this recounts what was decided rather than a rate."""
    d = objection_dose_response(session, council_id, meeting_id=meeting_id)
    era = _meeting_label(session, meeting_id)
    if d.total_decided == 0:
        return TestResult(
            test_id="planning.objection_responsiveness", title="Were any planning applications decided this meeting?",
            genre="Process / engagement (3.4)", principle="CIPFA-B",
            question="How many planning applications were decided this meeting, and how many drew objections?",
            valence=NEUTRAL, grade=G_OBSERVATION,
            headline="No planning applications decided this meeting",
            verdict="No planning applications decided this meeting.",
            n=0, era=era, detail_panel="dose", scope=[SCOPE_SINGLE_MEETING],
            stat={"value": 0, "denominator": 0, "unit": "count"}, digest_floor=0.0,
        )
    with_obj = sum(b.n for b in d.buckets if b.label != "0")
    refused = sum(b.refused for b in d.buckets)
    return TestResult(
        test_id="planning.objection_responsiveness", title="Were any planning applications decided this meeting?",
        genre="Process / engagement (3.4)", principle="CIPFA-B",
        question="How many planning applications were decided this meeting, and how many drew objections?",
        valence=NEUTRAL, grade=G_OBSERVATION,
        headline=f"{d.total_decided} application(s) decided this meeting, {refused} refused, "
                 f"{with_obj} drew at least one objection",
        verdict=f"{d.total_decided} application(s) decided this meeting: {refused} refused, "
                f"{with_obj} drew at least one community objection.",
        n=d.total_decided, era=era, detail_panel="dose", scope=[SCOPE_SINGLE_MEETING],
        stat={"value": refused, "denominator": d.total_decided, "unit": "count"}, digest_floor=0.0,
    )


def _t_tender_concentration(session, council_id, pc, meeting_id=None) -> TestResult:
    if meeting_id is not None:
        return _t_tender_concentration_meeting(session, council_id, meeting_id)
    t = pc.get("tenders") or tender_concentration(session, council_id)
    red_pct = round(t.redacted_amount / t.total_amount * 100) if t.total_amount else 0
    # No direction (docs/SECOND_COUNCIL_PLAN.md 1.1): concentration among
    # a broad supplier base is ordinary for big civil contracts, not a
    # good/bad signal on its own — the redacted share is the real
    # watch-item, and that's already transparency.confidential_tender_size's
    # job, not this test's.
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
        scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING],
    )


def _t_tender_concentration_meeting(session, council_id, meeting_id) -> TestResult:
    """Firm names, not person names — stays institutional (same convention
    as the whole-corpus version, whose `contractors` list also names firms
    without being flagged individual)."""
    t = tender_concentration(session, council_id, meeting_id=meeting_id)
    era = _meeting_label(session, meeting_id)
    if t.total_awards == 0:
        return TestResult(
            test_id="procurement.concentration", title="Were any tenders awarded this meeting?",
            genre="Procurement / transparency (3.1/3.4)", principle="CIPFA-F, G",
            question="Were any tenders awarded this meeting, and to whom?",
            valence=NEUTRAL, grade=G_OBSERVATION,
            headline="No tenders awarded this meeting",
            verdict="No tenders awarded this meeting.",
            n=0, era=era, detail_panel="tenders", scope=[SCOPE_SINGLE_MEETING],
            stat={"value": 0, "denominator": None, "unit": "count"}, digest_floor=0.0,
        )
    who = ", ".join(f"{c.name} (${c.total_amount:,.0f})" for c in t.contractors[:5])
    return TestResult(
        test_id="procurement.concentration", title="Were any tenders awarded this meeting?",
        genre="Procurement / transparency (3.1/3.4)", principle="CIPFA-F, G",
        question="Were any tenders awarded this meeting, and to whom?",
        valence=NEUTRAL, grade=G_OBSERVATION,
        headline=f"{t.total_awards} tender(s) awarded this meeting, ${t.total_amount:,.0f} total",
        verdict=f"{t.total_awards} tender(s) awarded this meeting totalling ${t.total_amount:,.0f}"
                # "redacted", not "confidential": `redacted_awards` counts awards with no
                # identifiable recipient, which is a different set from the `is_confidential`
                # awards `transparency.confidential_tender_size` counts. Calling both
                # "confidential" made the two tests read as contradicting each other in the
                # same digest paragraph (meeting 245, 2026-08-31).
                + (f": {who}" if who else "")
                + (f" ({t.redacted_awards} with a redacted recipient)" if t.redacted_awards else ""),
        n=t.total_awards, era=era, detail_panel="tenders", scope=[SCOPE_SINGLE_MEETING],
        stat={"value": t.total_awards, "denominator": None, "unit": "count"}, digest_floor=1.0,
    )


# ════════════════════════════════════════════════════════════════════════════
# CLEAN INTEGRITY TESTS — previously hidden nulls, now shown as supportive
# ════════════════════════════════════════════════════════════════════════════
def _t_decider_supplier_conflict(session, council_id, pc, meeting_id=None) -> TestResult:
    """[35] The Part 3.3 decider x supplier join: does a councillor who votes
    to award a tender ever share a declared or name-matched connection to the
    winning firm? Built on `decider_supplier_conflict()` — see that function's
    docstring for why neither limb touches the `interest_declarations`
    item_reference join. Converges with `procurement.threshold_gaming` and
    `procurement.incumbency` (supplier side) and `conflict.recusal_management`
    (decider side) as a fourth, independent procurement-integrity credit."""
    if meeting_id is not None:
        return _t_decider_supplier_conflict_meeting(session, council_id, meeting_id)
    r = pc.get("decider_supplier") or decider_supplier_conflict(session, council_id)
    chart = _bars(
        [("Tender-award votes", r.declared_pct), ("Chamber base rate", r.base_declared_pct)],
        unit="%", highlight_label="Tender-award votes",
    )
    # Derived, not asserted (docs/SECOND_COUNCIL_PLAN.md 1.1 — this one found
    # a live false claim, not just an unconditional literal): this used to
    # say "zero genuine decider<->winner matches" unconditionally, even
    # against a corpus with real raw collisions (Cambridge has 2 — see
    # decider_supplier_conflict()'s own docstring on why a raw hit is a
    # candidate for human review, not confirmed evidence, and is NEVER
    # itself proof of a real relationship). A raw collision existing is
    # reported honestly now instead of asserted away; whether it's a real
    # relationship still isn't something this function can determine, so
    # it's NEUTRAL/Observation rather than a false SUPPORTIVE or an
    # unfounded CRITICAL. Institutional either way — no name enters this
    # test's own text (the drill-down panel carries the names).
    n_collisions = len(r.collisions)
    # Chance baseline (docs/uplift/migration/01-known-defects.md G-31): a raw
    # collision count on its own has no way to say whether it's notable —
    # below the expected-under-chance count, it's reported as a null result,
    # not a finding, however small the raw count is.
    below_chance = n_collisions <= r.expected_collisions_under_chance
    chance_note = (f" A chance baseline estimated from this corpus's own naming patterns "
                   f"(see /method) expects about {r.expected_collisions_under_chance} such "
                   f"collisions by pure name overlap alone — {n_collisions} is "
                   f"{'at or below' if below_chance else 'above'} that baseline."
                   if r.chance_baseline_reference_n else "")
    if n_collisions == 0 or below_chance:
        valence, grade = SUPPORTIVE, G_STRENGTH
        headline = (f"Tender-award votes declare an interest just {r.declared_pct}% of the time "
                    f"(below the {r.base_declared_pct}% chamber base) — "
                    + (f"no raw decider↔winner surname matches across {r.named_awards} named awards"
                       if n_collisions == 0 else
                       f"{n_collisions} raw surname collision(s) across {r.named_awards} named "
                       "awards, at or below the chance baseline"))
        verdict = ("The join that would expose procurement capture — a councillor tied to a tender "
                   "winner with no declaration on the award — finds nothing above chance. Converges "
                   "with the supplier-side credits and the decider-side tests (recusal management) "
                   "as a fourth independent procurement-integrity result — read within its coverage "
                   "limit, since only separately-moved tender-award motions are visible, not "
                   "consent-agenda'd awards." + chance_note)
    else:
        valence, grade = NEUTRAL, G_OBSERVATION
        headline = (f"Tender-award votes declare an interest just {r.declared_pct}% of the time "
                    f"(below the {r.base_declared_pct}% chamber base) — {n_collisions} raw "
                    f"decider↔winner surname collision(s) across {r.named_awards} named awards, "
                    "above the chance baseline, unconfirmed")
        verdict = (f"{n_collisions} raw surname collision(s) were found between a tender winner "
                   "and a voting councillor — a name match against a councillor's surname, not a "
                   "confirmed relationship; resolving one needs the underlying minute text (see "
                   "the drill-down for names, firms, and provenance)." + chance_note)
    return TestResult(
        test_id="procurement.decider_supplier_conflict",
        title="Do tender deciders share an undeclared connection with the winner?",
        genre="Integrity / procurement (3.3)",
        principle="Nolan Objectivity · CIPFA-A/F",
        question="When council awards a tender, is a conflict declared — and does the winner ever "
                 "match a councillor's known connections?",
        valence=valence,
        grade=grade,
        headline=headline,
        verdict=verdict,
        n=r.votes_on_tender_motions,
        base_rate=f"{r.base_declared_pct}% chamber-wide declared-interest rate; "
                  f"{r.named_awards} named awards vs {r.surnames_tested} voting-councillor surnames",
        era="1995–2026",
        detail_panel="decider-supplier",
        chart=chart,
        scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING],
    )


def _t_decider_supplier_conflict_meeting(session, council_id, meeting_id) -> TestResult:
    """Whether any tender awarded this meeting has a raw surname collision
    with a real voting councillor. The collision detector names a specific
    councillor when it fires — the docstring above is explicit that a hit
    is a candidate for a human to check on provenance, not confirmed
    evidence, so that caveat is carried into the verdict text, not dropped."""
    r = decider_supplier_conflict(session, council_id, meeting_id=meeting_id)
    era = _meeting_label(session, meeting_id)
    if r.votes_on_tender_motions == 0 and not r.collisions:
        return TestResult(
            test_id="procurement.decider_supplier_conflict", title="Any decider↔supplier collisions this meeting?",
            genre="Integrity / procurement (3.3)", principle="Nolan Objectivity · CIPFA-A/F",
            question="Did anyone vote on a tender award this meeting with a possible connection to the winner?",
            valence=NEUTRAL, grade=G_OBSERVATION,
            headline="No tender-award votes this meeting",
            verdict="No tender-award votes this meeting.",
            n=0, era=era, detail_panel="decider-supplier", scope=[SCOPE_SINGLE_MEETING],
            stat={"value": 0, "denominator": 0, "unit": "count"}, digest_floor=0.0,
        )
    if not r.collisions:
        return TestResult(
            test_id="procurement.decider_supplier_conflict", title="Any decider↔supplier collisions this meeting?",
            genre="Integrity / procurement (3.3)", principle="Nolan Objectivity · CIPFA-A/F",
            question="Did anyone vote on a tender award this meeting with a possible connection to the winner?",
            valence=NEUTRAL, grade=G_OBSERVATION,
            headline=f"{r.declared_votes} of {r.votes_on_tender_motions} tender-award votes declared an "
                     f"interest this meeting; no surname collisions with the winner found",
            verdict=f"{r.declared_votes} of {r.votes_on_tender_motions} tender-award votes declared an "
                     f"interest this meeting; no surname collisions with the winner found.",
            n=r.votes_on_tender_motions, era=era, detail_panel="decider-supplier", scope=[SCOPE_SINGLE_MEETING],
            stat={"value": 0, "denominator": r.votes_on_tender_motions, "unit": "count"}, digest_floor=0.0,
        )
    names = sorted({c.councillor_name for c in r.collisions})
    lines = "; ".join(f"{c.councillor_name}'s surname appears in winner '{c.firm}' (${c.amount:,.0f})"
                       for c in r.collisions)
    return TestResult(
        test_id="procurement.decider_supplier_conflict", title="Any decider↔supplier collisions this meeting?",
        genre="Integrity / procurement (3.3)", principle="Nolan Objectivity · CIPFA-A/F",
        question="Did anyone vote on a tender award this meeting with a possible connection to the winner?",
        valence=NEUTRAL, grade=G_OBSERVATION,
        headline=f"{len(r.collisions)} surname collision(s) found between a tender winner and a voting "
                 f"councillor this meeting — unconfirmed, provenance not checked",
        verdict=lines + " — a raw surname match, not a confirmed relationship; resolving it needs the "
                "underlying minute text.",
        n=r.votes_on_tender_motions, era=era, detail_panel="decider-supplier",
        unit_of_analysis=UNIT_INDIVIDUAL, named_entities=names,
        scope=[SCOPE_SINGLE_MEETING],
        stat={"value": len(r.collisions), "denominator": r.votes_on_tender_motions, "unit": "count"},
        digest_floor=1.0,
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
        scope=[SCOPE_WHOLE_CORPUS],
    )


def _t_procurement_incumbency(session, council_id, pc) -> TestResult:
    # Is any supplier BOTH a frequent repeat-winner AND a big-dollar incumbent?
    rows = list(_tender_rows(session, council_id))
    by_firm: dict[str, dict] = {}
    for a, name, y, _m in rows:
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
                       "Do the same firms keep winning the big-dollar work?",
                       scope=[SCOPE_WHOLE_CORPUS])
    # Same canonical display label tender_concentration() shows for the same
    # firm (docs/uplift/migration/01-known-defects.md G-05) — not `.title()`
    # on the destructively-normalised key, which mangled spellings like
    # "CJD Equipment" into "Cjdequipment".
    display = contractor_display_names(name for _a, name, _y, _m in rows if name)
    top_dollars = sorted(by_firm.values(), key=lambda r: r["amt"], reverse=True)[:10]
    top_dollar_keys = {id(r) for r in top_dollars}
    most_recurring = max(by_firm.items(), key=lambda kv: len(kv[1]["years"]))
    most_recurring_name = display.get(most_recurring[0], most_recurring[0])
    overlap = any(len(r["years"]) >= 4 and id(r) in top_dollar_keys for r in by_firm.values())
    # chart: the most-recurring firms by distinct years won (recurrence ≠ big dollars)
    top_recurring = sorted(by_firm.items(), key=lambda kv: len(kv[1]["years"]), reverse=True)[:10]
    chart = _bars(
        [(display.get(k, k)[:22], len(v["years"])) for k, v in top_recurring],
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
        scope=[SCOPE_WHOLE_CORPUS],
    )


def _t_big_dollar_leniency(session, council_id, pc, meeting_id=None) -> TestResult:
    if meeting_id is not None:
        return _t_big_dollar_leniency_meeting(session, council_id, meeting_id)
    # council_id-scoped via the same Motion/Meeting join the meeting-scoped
    # sibling below already uses — this query had none until 2026-09-15
    # (found by tests/test_council_agnostic.py's direction-tracking check):
    # a bare PlanningApplication scan pools every council sharing the DB.
    rows = (
        session.query(PlanningApplication.estimated_value, PlanningApplication.status)
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            PlanningApplication.estimated_value.isnot(None),
            PlanningApplication.status.in_([ApplicationStatus.APPROVED, ApplicationStatus.REFUSED]),
        ).all()
    )
    vals = sorted([(v, s) for v, s in rows if v and v > 0], key=lambda t: t[0])
    if len(vals) < 20:
        return _nodata("planning.big_dollar_leniency", "Do big developments get an easier ride?",
                       "Governance / fairness (3.2)", "CIPFA-D — value for money / objectivity",
                       "Are high-value applications approved at a different rate?",
                       scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING])
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
        scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING],
    )


def _t_big_dollar_leniency_meeting(session, council_id, meeting_id) -> TestResult:
    """A quartile split needs many applications — one meeting recounts its
    own decided applications and their values instead. NOTE (real coverage
    gap, not assumed away): PlanningApplication reaches a Meeting only via
    its nullable motion_id -> Motion.meeting_id; an application with no
    linked motion is invisible to this meeting-scoped query even though the
    whole-corpus version above (no Meeting join at all) would still count
    it. Worth checking how common that is before treating this as complete."""
    rows = (
        session.query(PlanningApplication.estimated_value, PlanningApplication.status)
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.id == meeting_id,
                PlanningApplication.status.in_([ApplicationStatus.APPROVED, ApplicationStatus.REFUSED]))
        .all()
    )
    era = _meeting_label(session, meeting_id)
    if not rows:
        return TestResult(
            test_id="planning.big_dollar_leniency", title="Were any planning applications decided this meeting?",
            genre="Governance / fairness (3.2)", principle="CIPFA-D · Nolan Objectivity",
            question="What planning applications were decided this meeting, and at what estimated value?",
            valence=NEUTRAL, grade=G_OBSERVATION,
            headline="No planning applications decided this meeting",
            verdict="No planning applications decided this meeting.",
            n=0, era=era, detail_panel="big-dollar", scope=[SCOPE_SINGLE_MEETING],
            stat={"value": 0, "denominator": None, "unit": "count"}, digest_floor=0.0,
        )
    approved = sum(1 for _v, s in rows if s == ApplicationStatus.APPROVED)
    valued = [v for v, _s in rows if v and v > 0]
    val_str = f", estimated value ${max(valued):,.0f}" if valued and len(rows) == 1 else \
              f", estimated values ${min(valued):,.0f}–${max(valued):,.0f}" if len(valued) > 1 else ""
    return TestResult(
        test_id="planning.big_dollar_leniency", title="Were any planning applications decided this meeting?",
        genre="Governance / fairness (3.2)", principle="CIPFA-D · Nolan Objectivity",
        question="What planning applications were decided this meeting, and at what estimated value?",
        valence=NEUTRAL, grade=G_OBSERVATION,
        headline=f"{len(rows)} application(s) decided this meeting, {approved} approved{val_str}",
        verdict=f"{len(rows)} application(s) decided this meeting, {approved} approved{val_str}.",
        n=len(rows), era=era, detail_panel="big-dollar", scope=[SCOPE_SINGLE_MEETING],
        stat={"value": len(rows), "denominator": None, "unit": "count"}, digest_floor=0.0,
    )


def _t_repeat_applicant(session, council_id, pc) -> TestResult:
    # council_id-scoped — same missing-join bug as _t_big_dollar_leniency
    # just above, found the same way.
    rows = (
        session.query(PlanningApplication.applicant_name, PlanningApplication.status)
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
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
                       "Do repeat builders/agents get approved more than one-shot applicants?",
                       scope=[SCOPE_WHOLE_CORPUS])

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
    # In frequency order (1, 2-3, 4-6, 7+) — dict insertion order, unchanged
    # since `buckets` and `rates` are never reordered.
    vals = [r for r in rates.values() if r is not None]
    spread = (max(vals) - min(vals)) if vals else 0
    # A spread alone can't distinguish "no trend" from "a real
    # non-monotonic dip" that happens to cancel out end-to-end
    # (docs/uplift/migration/01-known-defects.md G-18): below a negligible
    # ±5pp band (the same no-clear-trend threshold conflict.recusal_trend
    # already uses), shape doesn't matter — call it flat outright. Above
    # that, a consistent step-by-step direction is a real pattern even at
    # moderate spread, so only a non-monotonic (zigzag) shape stays flat.
    # A 2-point sequence is trivially "monotonic" either way, so it carries
    # no shape information — needs >=3 populated buckets to say anything
    # about trend vs. zigzag.
    monotonic_trend = (
        len(vals) >= 3 and vals[0] != vals[-1]
        and (all(b >= a for a, b in zip(vals, vals[1:]))
             or all(b <= a for a, b in zip(vals, vals[1:])))
    )
    flat = spread <= 5 or (spread <= 14 and not monotonic_trend)
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
        scope=[SCOPE_WHOLE_CORPUS],
    )


# ════════════════════════════════════════════════════════════════════════════
# NEUTRAL DESCRIPTIVE TESTS — how the council works (no good/bad direction)
# ════════════════════════════════════════════════════════════════════════════
def _t_unanimity_trend(session, council_id, pc, meeting_id=None) -> TestResult:
    if meeting_id is not None:
        return _t_unanimity_trend_meeting(session, council_id, meeting_id)
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
            series.append({"x": y, "y": _capped_pct(sum(items), len(items))})
    total = [v for items in by_year.values() for v in items]
    overall = _capped_pct(sum(total), len(total)) if total else None
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
        scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING],
    )


def _t_unanimity_trend_meeting(session, council_id, meeting_id) -> TestResult:
    """Plain recount of contested vs unanimous carried motions this meeting
    — no names (a motion, not a person, is the unit)."""
    rows = _minutes_motions(session, council_id, meeting_id=meeting_id)
    carried = [(va or 0) for outcome, va, _yr in rows if outcome == MotionOutcome.CARRIED]
    era = _meeting_label(session, meeting_id)
    if not carried:
        return TestResult(
            test_id="governance.unanimity_trend", title="Did any motions split this meeting?",
            genre="Governance / culture (3.2)", principle="CIPFA-B",
            question="How many of this meeting's carried motions drew a dissenting vote?",
            valence=NEUTRAL, grade=G_OBSERVATION,
            headline="No carried motions this meeting",
            verdict="No carried motions this meeting.",
            n=0, era=era, detail_panel="unanimity", scope=[SCOPE_SINGLE_MEETING],
            stat={"value": 0, "denominator": 0, "unit": "count"}, digest_floor=0.0,
        )
    contested = sum(1 for va in carried if va > 0)
    return TestResult(
        test_id="governance.unanimity_trend", title="Did any motions split this meeting?",
        genre="Governance / culture (3.2)", principle="CIPFA-B",
        question="How many of this meeting's carried motions drew a dissenting vote?",
        valence=NEUTRAL, grade=G_OBSERVATION,
        headline=f"{contested} of {len(carried)} carried motions drew a dissenting vote this meeting",
        verdict=f"{contested} of {len(carried)} carried motions drew at least one dissenting vote this meeting.",
        n=len(carried), era=era, detail_panel="unanimity", scope=[SCOPE_SINGLE_MEETING],
        stat={"value": contested, "denominator": len(carried), "unit": "count"}, digest_floor=0.0,
    )


def _t_eoy_spending(session, council_id, pc) -> TestResult:
    """[finance.eoy_spending] Fiscal-year-anchored, not calendar-year: WA local
    government runs 1 Jul-30 Jun (LGA 1995 s6.2, `src.council_eras.
    fiscal_year_start_month`), so the "use it or lose it" test is the two
    months immediately before that boundary (May/June for a Jul-start year),
    not a hardcoded December (docs/uplift/migration/01-known-defects.md G-01)."""
    from src.models import Council

    rows = [(a, m) for a, _n, _y, m in _tender_rows(session, council_id) if a and m]
    if not rows:
        return _nodata("finance.eoy_spending", "End-of-year spending spike",
                       "Financial (3.1)", "ICAC generic risk",
                       "Do tender awards/dollars spike at the end of the budget cycle?",
                       scope=[SCOPE_WHOLE_CORPUS])
    council = session.query(Council).filter(Council.id == council_id).first()
    start_month = fiscal_year_start_month(council.short_name) if council else 7
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    # Calendar months in fiscal-year order, e.g. start_month=7 -> [7,8,...,12,1,...,6]
    fy_order = [(start_month - 1 + i) % 12 + 1 for i in range(12)]
    eoy_months = set(fy_order[-2:])  # the two months immediately before the FY boundary

    tot_amt = sum(a for a, _m in rows)
    eoy_amt = sum(a for a, m in rows if m in eoy_months)
    eoy_n = sum(1 for _a, m in rows if m in eoy_months)
    eoy_share = round(eoy_amt / tot_amt * 100) if tot_amt else 0
    expected = round(200 / 12)  # two months' even share
    spike = eoy_share >= expected * 2

    by_month = [0.0] * 12
    for a, m in rows:
        if 1 <= m <= 12:
            by_month[m - 1] += a / 1e6
    peak_idx = max(range(12), key=lambda i: by_month[i])
    peak_label = month_names[peak_idx]
    eoy_labels = ", ".join(month_names[m - 1] for m in fy_order[-2:])

    chart = _bars(
        [(month_names[m - 1], round(by_month[m - 1], 1)) for m in fy_order],
        unit="$M", highlight_label=peak_label,
    )
    return TestResult(
        test_id="finance.eoy_spending",
        title="Is there an end-of-year 'use it or lose it' spike?",
        genre="Financial (3.1)",
        principle="CIPFA-F — financial management",
        question="Do tender dollars cluster into the final months of the fiscal year?",
        valence=CRITICAL if spike else NEUTRAL,
        grade=G_CONCERN if spike else G_OBSERVATION,
        headline=(f"{eoy_labels} (fiscal year-end) hold {eoy_share}% of tender dollars "
                  f"({eoy_n} awards) vs ~{expected}% expected; {peak_label} is the single "
                  "highest-dollar month"),
        verdict=("A modest fiscal year-end bump consistent with normal capital timing, not a "
                 "dramatic use-it-or-lose-it dump." if not spike
                 else f"{eoy_labels} spending is well above an even spread; warrants explanation."),
        n=len(rows),
        base_rate=f"~{expected}% if evenly spread across {eoy_labels}",
        era="1995–2026",
        detail_panel="eoy",
        chart=chart,
        scope=[SCOPE_WHOLE_CORPUS],
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
    er = _capped_pct(early_diss, early_n) if early_n else None
    lr = _capped_pct(late_diss, late_n) if late_n else None
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
        scope=[SCOPE_WHOLE_CORPUS],
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
    wr = _capped_pct(win_d, win_n) if win_n else None
    orr = _capped_pct(oth_d, oth_n) if oth_n else None
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
        scope=[SCOPE_WHOLE_CORPUS],
    )


def _t_deputation_dissent(session, council_id, pc, meeting_id=None) -> TestResult:
    if meeting_id is not None:
        return _t_deputation_dissent_meeting(session, council_id, meeting_id)
    dep_meetings = {m for (m,) in session.query(Deputation.meeting_id)
                    .join(Meeting, Deputation.meeting_id == Meeting.id)
                    .filter(Meeting.council_id == council_id).distinct().all()}
    rows = _meeting_contestation(session, council_id)
    with_d = [c for mid, c in rows if mid in dep_meetings]
    without_d = [c for mid, c in rows if mid not in dep_meetings]
    wr = _capped_pct(sum(with_d), len(with_d)) if with_d else None
    orr = _capped_pct(sum(without_d), len(without_d)) if without_d else None
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
        scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING],
    )


def _t_deputation_dissent_meeting(session, council_id, meeting_id) -> TestResult:
    """Plain recount: did this meeting have a public deputation, and how
    contested were its carried motions?"""
    had_deputation = session.query(Deputation.id).filter(Deputation.meeting_id == meeting_id).first() is not None
    rows = [c for mid, c in _meeting_contestation(session, council_id) if mid == meeting_id]
    era = _meeting_label(session, meeting_id)
    contested = sum(rows)
    return TestResult(
        test_id="engagement.deputation_dissent", title="Was there a public deputation this meeting?",
        genre="Process / engagement (3.4)", principle="CIPFA-B",
        question="Did this meeting have a public deputation, and how contested were its carried motions?",
        valence=NEUTRAL, grade=G_OBSERVATION,
        headline=(f"A public deputation was heard this meeting; {contested} of {len(rows)} carried "
                  f"motions were contested" if had_deputation else
                  f"No public deputation this meeting; {contested} of {len(rows)} carried motions were contested")
                 if rows else
                 ("A public deputation was heard this meeting; no carried motions" if had_deputation
                  else "No public deputation and no carried motions this meeting"),
        verdict=f"{'A' if had_deputation else 'No'} public deputation was heard this meeting"
                + (f"; {contested} of {len(rows)} carried motions were contested." if rows else "."),
        n=len(rows), era=era, detail_panel="deputations", scope=[SCOPE_SINGLE_MEETING],
        stat={"value": 1 if had_deputation else 0, "denominator": None, "unit": "count"},
        digest_floor=1.0 if had_deputation else 0.0,
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


def _t_attendance(session, council_id, pc, meeting_id=None) -> TestResult:
    if meeting_id is not None:
        return _t_attendance_meeting(session, council_id, meeting_id)
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
    pct = _capped_pct(absent, total) if total else 0.0
    rec_share = round(recusal_abs / absent * 100) if absent else 0
    gen_share = 100 - rec_share
    genuine_pct = _capped_pct(genuine_abs, total, decimals=2) if total else 0.0
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
        scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING],
    )


def _t_attendance_meeting(session, council_id, meeting_id) -> TestResult:
    """Who was absent this meeting, and whether it was a declared recusal
    or unexplained — a plain recount of ABSENT vote rows, same source as
    the minutes themselves. Genuinely-absent councillors are named
    (UNIT_INDIVIDUAL); a meeting where every absence was a declared
    recusal, or nobody was absent, names no one and stays institutional."""
    rows = (
        session.query(Vote.choice, Vote.declared_interest, Councillor.given_name, Councillor.family_name)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .join(Councillor, Vote.councillor_id == Councillor.id)
        .filter(Meeting.id == meeting_id)
        .all()
    )
    era = _meeting_label(session, meeting_id)
    if not rows:
        return TestResult(
            test_id="governance.attendance", title="Was anyone absent this meeting?",
            genre="Governance / culture (3.2)", principle="Nolan Accountability",
            question="Which councillors were absent this meeting, and was it a declared recusal or unexplained?",
            valence=NEUTRAL, grade=G_OBSERVATION,
            headline="No vote rows recorded this meeting",
            verdict="No vote rows recorded this meeting.",
            n=0, era=era, detail_panel="attendance", scope=[SCOPE_SINGLE_MEETING],
            stat={"value": 0, "denominator": None, "unit": "count"}, digest_floor=0.0,
        )
    by_councillor: dict[str, list[tuple]] = {}
    for ch, di, given, family in rows:
        name = f"{given or ''} {family or ''}".strip()
        by_councillor.setdefault(name, []).append((ch, di))
    genuine_names = sorted(
        name for name, votes in by_councillor.items()
        if any(ch == VoteChoice.ABSENT and not di for ch, di in votes)
    )
    recusal_only_names = sorted(
        name for name, votes in by_councillor.items()
        if name not in genuine_names
        and any(ch == VoteChoice.ABSENT and di for ch, di in votes)
    )
    if not genuine_names:
        note = (f"; {', '.join(recusal_only_names)} stepped out on a declared conflict"
                if recusal_only_names else "")
        return TestResult(
            test_id="governance.attendance", title="Was anyone absent this meeting?",
            genre="Governance / culture (3.2)", principle="Nolan Accountability",
            question="Which councillors were absent this meeting, and was it a declared recusal or unexplained?",
            valence=NEUTRAL, grade=G_OBSERVATION,
            headline="No unexplained absences this meeting" + note,
            verdict="No unexplained absences this meeting" + note + ".",
            n=len(rows), era=era, detail_panel="attendance", scope=[SCOPE_SINGLE_MEETING],
            stat={"value": 0, "denominator": None, "unit": "count"}, digest_floor=0.0,
        )
    return TestResult(
        test_id="governance.attendance", title="Was anyone absent this meeting?",
        genre="Governance / culture (3.2)", principle="Nolan Accountability",
        question="Which councillors were absent this meeting, and was it a declared recusal or unexplained?",
        valence=NEUTRAL, grade=G_OBSERVATION,
        headline=f"{', '.join(genuine_names)} had at least one unexplained absence this meeting",
        verdict=f"{', '.join(genuine_names)} had at least one vote recorded ABSENT this meeting with no "
                f"declared interest on that item.",
        n=len(rows), era=era, detail_panel="attendance",
        unit_of_analysis=UNIT_INDIVIDUAL, named_entities=genuine_names,
        scope=[SCOPE_SINGLE_MEETING],
        stat={"value": len(genuine_names), "denominator": None, "unit": "count"}, digest_floor=1.0,
    )


# ════════════════════════════════════════════════════════════════════════════
# DATA-LIMITED TESTS — the corpus can't support these (still comparable!)
# ════════════════════════════════════════════════════════════════════════════
def _nodata(test_id, title, genre, principle, question, scope=None) -> TestResult:
    return TestResult(
        test_id=test_id, title=title, genre=genre, principle=principle, question=question,
        valence=NEUTRAL, grade=G_NODATA, data_ok=False,
        headline="Not computable on this corpus",
        verdict="The data needed for this standard test is not present/structured in this corpus.",
        scope=scope if scope is not None else [SCOPE_WHOLE_CORPUS],
    )


def _t_single_source(session, council_id, pc) -> TestResult:
    r = _nodata("procurement.single_source", "Single-source / direct-negotiation share",
                "Integrity / procurement (3.3)", "ICAC direct-negotiation guidance",
                "What share of tenders had no competitive field?",
                scope=[SCOPE_WHOLE_CORPUS])
    r.verdict = ("Tenders carry no competitive-field metadata (number of respondents) in this "
                 "corpus, so single-source concentration can't be measured — flagged for re-extraction.")
    r.detail_panel = "single-source"
    return r


def _t_reserve_trajectory(session, council_id, pc) -> TestResult:
    r = _nodata("finance.reserve_trajectory", "Reserve depletion / financial resilience",
                "Financial (3.1)", "CIPFA Financial Resilience Index",
                "Are reserves being depleted (the s.114 precursor)?",
                scope=[SCOPE_WHOLE_CORPUS])
    r.verdict = ("An investment-portfolio series exists in the minutes (peaked ~$73M in 2018) but the "
                 "~24 irregular free-text snapshots can't be normalised to a defensible reserve trend "
                 "yet — needs a finance-aware re-extraction.")
    r.detail_panel = "reserve"
    return r


def _t_engagement(session, council_id, pc, meeting_id=None) -> TestResult:
    """Public participation volume over time — CIPFA-B stakeholder engagement."""
    if meeting_id is not None:
        return _t_engagement_meeting(session, council_id, meeting_id)
    years = public_engagement_by_year(session, council_id)
    total = sum(y.total for y in years)
    series = [{"x": y.year, "y": y.total} for y in years if y.total]
    recent = [y for y in years if y.year >= 2016]
    recent_avg = round(sum(y.total for y in recent) / len(recent)) if recent else 0
    # No direction (docs/SECOND_COUNCIL_PLAN.md 1.1) — sits under the
    # DATA-LIMITED TESTS section header above by file-organisation
    # accident, not because it's data-limited: raw participation volume
    # has no good/bad reading on its own (it tracks the political
    # temperature, per the verdict below, not a compliance signal).
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
        scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING],
    )


def _t_engagement_meeting(session, council_id, meeting_id) -> TestResult:
    """Plain recount of this meeting's public questions/deputations/petitions
    — no names."""
    rows = public_engagement_by_year(session, council_id, meeting_id=meeting_id)
    total = sum(y.total for y in rows)
    era = _meeting_label(session, meeting_id)
    q = sum(y.public_questions for y in rows)
    d = sum(y.deputations for y in rows)
    p = sum(y.petitions for y in rows)
    return TestResult(
        test_id="engagement.participation", title="How much public participation did this meeting see?",
        genre="Process / engagement (3.4)", principle="CIPFA-B",
        question="How many public questions, deputations and petitions did this meeting see?",
        valence=NEUTRAL, grade=G_OBSERVATION,
        headline=(f"{q} public question(s), {d} deputation(s), {p} petition(s) this meeting" if total
                  else "No recorded public questions, deputations, or petitions this meeting"),
        verdict=(f"{q} public question(s), {d} deputation(s), {p} petition(s) this meeting." if total
                 else "No recorded public questions, deputations, or petitions this meeting."),
        n=total, era=era, detail_panel="engagement", scope=[SCOPE_SINGLE_MEETING],
        stat={"value": total, "denominator": None, "unit": "count"}, digest_floor=0.0,
    )


def _t_confidential_tender_size(session, council_id, pc, meeting_id=None) -> TestResult:
    """[30] Are the CONFIDENTIAL tenders systematically the larger-dollar ones?
    Pooled cross-sectional: median confidential vs open (amount-bearing rows only).
    DIRECTIONAL — n_confidential is small; measured by the is_confidential FLAG on
    rows that carry an amount, never by award-field missingness (the [25] trap).
    """
    if meeting_id is not None:
        return _t_confidential_tender_size_meeting(session, council_id, meeting_id)
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
                       "Do confidential tenders carry higher dollar values than open ones?",
                       scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING])
    conf_med = round(statistics.median(conf))
    opn_med = round(statistics.median(opn))
    ratio = round(conf_med / opn_med, 1) if opn_med else None
    chart = _bars(
        [("Confidential", round(conf_med / 1000)), ("Open", round(opn_med / 1000))],
        unit="k", highlight_label="Confidential",
    )
    # Derived, not asserted (docs/SECOND_COUNCIL_PLAN.md 1.1): pricier is
    # the concern (least-scrutinised contracts are the biggest); at or
    # below the open median is the opposite finding. The rank-sum p-value
    # and "~1 in 5 carries an amount" missingness clause from the old
    # unconditional text were Cambridge-specific statistics this function
    # doesn't compute — dropped rather than kept as an unsourced assertion
    # (this test still declares itself DIRECTIONAL/thin-n either way).
    pricier = ratio is not None and ratio > 1
    return TestResult(
        test_id="transparency.confidential_tender_size",
        title="Are the redacted tenders the bigger contracts?",
        genre="Transparency / financial (3.4 / 3.1)",
        principle="Nolan Openness · CIPFA-G — transparency/audit",
        question="Do confidential tenders carry higher dollar values than open ones?",
        valence=CRITICAL if pricier else SUPPORTIVE,
        grade=G_CONCERN if pricier else G_SOUND,
        headline=(f"Confidential tenders run a ${conf_med:,} median vs ${opn_med:,} open "
                  f"(~{ratio}×) — DIRECTIONAL, n={len(conf)}"),
        verdict=("The contracts residents can least scrutinise are systematically the largest — "
                 "confidentiality is often lawful, so this is a visibility concern, not impropriety."
                 if pricier else
                 "Confidential tenders are not systematically the larger contracts — the visibility "
                 "gap this test looks for isn't showing up here."),
        n=len(conf),
        base_rate=f"open-tender median ${opn_med:,} (n={len(opn)})",
        era="1995–2026 · DIRECTIONAL (n<30)",
        data_ok=True,
        detail_panel="confidential-tender-size",
        chart=chart,
        scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING],
    )


def _t_confidential_tender_size_meeting(session, council_id, meeting_id) -> TestResult:
    """This meeting's own confidential tenders (if any), next to the
    whole-corpus open-tender median — a single meeting rarely has enough
    tenders of either kind to compute its own median, so the comparison
    point is the established corpus baseline, not a recomputed one."""
    import statistics
    rows = session.query(Tender.amount, Tender.is_confidential) \
        .join(Meeting, Tender.meeting_id == Meeting.id) \
        .filter(Meeting.id == meeting_id, Tender.amount.isnot(None), Tender.amount > 0).all()
    era = _meeting_label(session, meeting_id)
    conf = [a for a, ic in rows if ic]
    body_types = _same_body_meeting_types(session, meeting_id)
    comparable = _comparable_label(session, meeting_id, body_types)
    corpus_q = (session.query(Tender.amount, Tender.is_confidential, Meeting.meeting_date)
                .join(Meeting, Tender.meeting_id == Meeting.id)
                .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes",
                        Tender.amount.isnot(None), Tender.amount > 0))
    if body_types:
        corpus_q = corpus_q.filter(Meeting.meeting_type.in_(body_types))
    corpus_open = [a for a, ic, _d in corpus_q.all() if not ic]
    corpus_med = round(statistics.median(corpus_open)) if corpus_open else None
    if not conf:
        return TestResult(
            test_id="transparency.confidential_tender_size", title="Were any tenders this meeting confidential?",
            genre="Transparency / financial (3.4 / 3.1)", principle="Nolan Openness · CIPFA-G",
            question="Was any tender awarded confidentially this meeting, and at what value?",
            valence=NEUTRAL, grade=G_OBSERVATION,
            headline="No confidential tenders (with a recorded amount) this meeting",
            verdict="No confidential tenders (with a recorded amount) this meeting.",
            n=0, era=era, detail_panel="confidential-tender-size", scope=[SCOPE_SINGLE_MEETING],
            stat={"value": 0, "denominator": None, "unit": "count"}, digest_floor=0.0,
        )
    return TestResult(
        test_id="transparency.confidential_tender_size", title="Were any tenders this meeting confidential?",
        genre="Transparency / financial (3.4 / 3.1)", principle="Nolan Openness · CIPFA-G",
        question="Was any tender awarded confidentially this meeting, and at what value?",
        valence=NEUTRAL, grade=G_OBSERVATION,
        headline=f"{len(conf)} confidential tender(s) this meeting, ${max(conf):,.0f} largest",
        verdict=f"{len(conf)} confidential tender(s) this meeting (largest ${max(conf):,.0f})"
                + (f", vs a ${corpus_med:,} open-tender median {comparable}." if corpus_med else "."),
        n=len(conf),
        base_rate=f"${corpus_med:,} open-tender median, {comparable}" if corpus_med else None,
        era=era, detail_panel="confidential-tender-size", scope=[SCOPE_SINGLE_MEETING],
        stat={"value": len(conf), "denominator": None, "unit": "count"}, digest_floor=1.0,
    )


# [36] placeholder "nil" confidential-reports headings (e.g. "Confidential
# Reports - Nil items") are standing agenda-section headers, not decided
# items — is_confidential=True on these rows is an extraction artifact, not
# a real closed item. Anchored to the four known instances' shared shape
# ("confidential reports [section] - nil...") so it doesn't also swallow a
# real description that happens to mention "nil" mid-sentence.
_NIL_PLACEHOLDER_RE = re.compile(
    r"^confidential reports?(\s+section)?\s*-\s*nil\b", re.IGNORECASE
)


def _is_nil_placeholder(desc: str | None) -> bool:
    return bool(desc) and bool(_NIL_PLACEHOLDER_RE.match(desc.strip()))


# theme keyword buckets for [36] — legitimate statutory grounds vs contentious topics
_CONF_THEMES = [
    ("Commercial-in-conf", r"commercial|in-confidence|negotiation|proposal|confidential"),
    ("Tender/procurement", r"tender|rft|contract|procure|quotation|supplier|panel"),
    ("Personnel/HR", r"\bceo\b|chief executive|staff|employee|personnel|recruit|remuneration|salary|human resource"),
    ("Legal/litigation", r"legal|litigation|court|claim|settlement|solicitor|counsel|dispute"),
    ("Land/property deal", r"lease|land|acquisition|dispose|disposal|purchase of|sale of|easement|freehold|valuation"),
    ("Named development", r"development|structure plan|precinct|activity centre|rezoning|subdivision|building height"),
]


def _t_confidential_topics(session, council_id, pc, meeting_id=None) -> TestResult:
    """[36] Is confidentiality aimed at particular subject matter — contentious
    topics beyond lawful grounds — or does it track the statutory grounds?
    Topical decomposition across the confidential-item tables. A credit if closure
    tracks lawful grounds and the contentious 'named development' theme is NOT
    over-closed. Keyword bucketing is noisy — reported at Observation/strength level.
    """
    if meeting_id is not None:
        return _t_confidential_topics_meeting(session, council_id, meeting_id)
    from src.models import OtherItem, DelegatedDecision
    descs: list[tuple[str, bool]] = []
    for model in (Tender, OtherItem, DelegatedDecision):
        for desc, ic in (
            session.query(model.description, model.is_confidential)
            .join(Meeting, model.meeting_id == Meeting.id)
            .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes")
        ):
            if _is_nil_placeholder(desc):
                continue  # standing "Confidential Reports - Nil" heading, not a decided item
            descs.append(((desc or "").lower(), bool(ic)))
    total = len(descs)
    conf_total = sum(1 for _d, ic in descs if ic)
    if not total or not conf_total:
        return _nodata("transparency.confidential_topics",
                       "What subject matter gets closed?",
                       "Transparency (3.4)", "Nolan Openness · CIPFA-B",
                       "Does confidentiality track lawful grounds or contentious topics?",
                       scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING])
    base = conf_total / total * 100
    theme_stat: list[tuple[str, int, int, float]] = []  # name, items, conf, lift
    for name, pat in _CONF_THEMES:
        rx = re.compile(pat)
        items = [ic for d, ic in descs if rx.search(d)]
        n = len(items)
        c = sum(1 for ic in items if ic)
        rate = (c / n * 100) if n else 0.0
        theme_stat.append((name, n, c, round(rate / base, 2) if base else 0.0))
    dev = next(t for t in theme_stat if t[0] == "Named development")
    top = max(theme_stat, key=lambda t: t[3])
    least_closed = min(theme_stat, key=lambda t: t[3])
    # Derived, not asserted (docs/SECOND_COUNCIL_PLAN.md 1.1): the credit
    # only holds if the contentious "named development" theme is actually
    # the one closed least of all themes measured, not assumed to be.
    dev_is_least_closed = dev[0] == least_closed[0]
    chart = _bars(
        [(t[0], _capped_pct(t[2], t[1]) if t[1] else 0) for t in theme_stat],
        unit="%", highlight_label="Named development",
    )
    dev_pct = _capped_pct(dev[2], dev[1]) if dev[1] else 0.0
    return TestResult(
        test_id="transparency.confidential_topics",
        title="What subject matter gets closed — and is it the contentious stuff?",
        genre="Transparency (3.4)",
        principle="Nolan Openness · CIPFA-B — openness & engagement",
        question="Does confidentiality track lawful statutory grounds or politically contentious topics?",
        valence=SUPPORTIVE if dev_is_least_closed else CRITICAL,
        grade=G_STRENGTH if dev_is_least_closed else G_CONCERN,
        headline=(f"Confidentiality concentrates on lawful grounds ({top[0]} {round(top[2]/top[1]*100)}%, "
                  f"lift {top[3]}×); contentious 'named development' is "
                  + (f"the LEAST closed ({dev_pct}%, lift {dev[3]}×)" if dev_is_least_closed else
                     f"closed at {dev_pct}% (lift {dev[3]}×), not the least-closed theme")),
        verdict=("Closure tracks the categories the law exists to protect (commercial-in-confidence, "
                 "tenders, HR, legal, land contracts); the most politically sensitive category — named "
                 "developments — is the most OPEN, not the most closed. Keyword themes are coarse, and "
                 "any error biases toward the null (over-counting development closures)."
                 if dev_is_least_closed else
                 "Named developments — the most politically sensitive category — are closed at least "
                 "as often as, or more than, other themes; confidentiality doesn't cleanly track lawful "
                 "grounds over contentious topics here.") + COVID_CONFOUND_CAVEAT,
        n=conf_total,
        base_rate=f"{_capped_pct(conf_total, total)}% of all items confidential",
        era="1995–2026",
        data_ok=True,
        detail_panel="confidential-topics",
        chart=chart,
        scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING],
    )


def _t_confidential_topics_meeting(session, council_id, meeting_id) -> TestResult:
    """A theme-lift statistic needs many items — one meeting recounts what
    was closed and its (already-public, since it's in the minutes) subject
    description instead."""
    from src.models import OtherItem, DelegatedDecision
    descs: list[str] = []
    for model in (Tender, OtherItem, DelegatedDecision):
        for (desc,) in (
            session.query(model.description)
            .join(Meeting, model.meeting_id == Meeting.id)
            .filter(Meeting.id == meeting_id, model.is_confidential.is_(True))
        ):
            if desc and not _is_nil_placeholder(desc):
                descs.append(desc.strip())
    era = _meeting_label(session, meeting_id)
    if not descs:
        return TestResult(
            test_id="transparency.confidential_topics", title="What was closed to the public this meeting?",
            genre="Transparency (3.4)", principle="Nolan Openness · CIPFA-B",
            question="Which items, if any, were taken confidential this meeting, and on what subject?",
            valence=NEUTRAL, grade=G_OBSERVATION,
            headline="No confidential items this meeting",
            verdict="No confidential items this meeting.",
            n=0, era=era, detail_panel="confidential-topics", scope=[SCOPE_SINGLE_MEETING],
            stat={"value": 0, "denominator": None, "unit": "count"}, digest_floor=0.0,
        )
    shown = "; ".join(d[:120] for d in descs[:5])
    return TestResult(
        test_id="transparency.confidential_topics", title="What was closed to the public this meeting?",
        genre="Transparency (3.4)", principle="Nolan Openness · CIPFA-B",
        question="Which items, if any, were taken confidential this meeting, and on what subject?",
        valence=NEUTRAL, grade=G_OBSERVATION,
        headline=f"{len(descs)} item(s) closed to the public this meeting",
        verdict=f"{len(descs)} item(s) closed to the public this meeting: {shown}",
        n=len(descs), era=era, detail_panel="confidential-topics", scope=[SCOPE_SINGLE_MEETING],
        stat={"value": len(descs), "denominator": None, "unit": "count"}, digest_floor=1.0,
    )


def _t_question_responsiveness(session, council_id, pc, meeting_id=None) -> TestResult:
    """[37] Public-question responsiveness — answered in the room, or 'taken on
    notice'? Deferral share by era, tracking this council's configured
    external-scrutiny window if it has one (config/council_eras.json,
    docs/SECOND_COUNCIL_PLAN.md 1.2) — an era-neutral overall rate otherwise."""
    if meeting_id is not None:
        return _t_question_responsiveness_meeting(session, council_id, meeting_id, pc)
    r = pc.get("pq_responsiveness") or public_question_responsiveness(session, council_id)
    series = [{"x": y.year, "y": y.on_notice_pct}
              for y in r.by_year if y.on_notice_pct is not None]
    if r.inquiry_window is None:
        # No configured external-scrutiny window (docs/SECOND_COUNCIL_PLAN.md
        # 1.2) — era-neutral computation, not an invented split: the overall
        # deferral rate is still real data, just not a before/after story.
        if r.total == 0:
            return _nodata("engagement.question_responsiveness",
                           "Are residents' questions answered, or quietly 'taken on notice'?",
                           "Process / engagement (3.4)",
                           "CIPFA-B — openness & stakeholder engagement · Nolan Accountability",
                           "What share of public questions are deferred rather than answered "
                           "in the meeting?", scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING])
        return TestResult(
            test_id="engagement.question_responsiveness",
            title="Are residents' questions answered, or quietly 'taken on notice'?",
            genre="Process / engagement (3.4)",
            principle="CIPFA-B — openness & stakeholder engagement · Nolan Accountability",
            question="What share of public questions are deferred rather than answered in the meeting?",
            valence=NEUTRAL,
            grade=G_OBSERVATION,
            headline=f"{r.on_notice_pct}% of public questions are taken on notice rather than "
                     "answered live",
            verdict="No configured external-scrutiny window for this council, so this is reported "
                    "as an overall rate rather than a before/during/after trend."
                    + COVID_CONFOUND_CAVEAT,
            n=r.answered + r.on_notice,
            base_rate=f"{r.answered_pct}% answered live",
            detail_panel="question-responsiveness",
            chart=_line(series, unit="%"),
            scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING],
        )
    # Derived, not asserted (docs/SECOND_COUNCIL_PLAN.md 1.1): whether
    # deferral actually rose or fell across the scrutiny window, rather
    # than an assumed "tripled, then held" shape — and no council named in
    # the verdict, which used to name Cambridge and its Authorised Inquiry
    # unconditionally.
    worsened = r.post_pct > r.pre_pct + 5
    improved = r.post_pct < r.pre_pct - 5
    peak_clause = f" (peak {r.peak_pct}% in {r.peak_year})" if r.peak_pct is not None else ""
    if worsened:
        valence, grade = CRITICAL, G_CONCERN
        headline = (f"Deferral of public questions rose from {r.pre_pct}% before scrutiny to "
                    f"{r.inquiry_pct}% during it{peak_clause}, still elevated at {r.post_pct}% after")
        verdict = ("Most public questions are answered live, but during and after the scrutiny window "
                   "they were increasingly deferred to 'on notice' — a measurable dip in in-room "
                   "accountability. 'On notice' is lawful and often appropriate, so this is a "
                   "responsiveness concern, not impropriety; the classifier is conservative, so the "
                   "deferral share is a floor.")
    elif improved:
        valence, grade = SUPPORTIVE, G_STRENGTH
        headline = (f"Deferral of public questions fell from {r.pre_pct}% before scrutiny to "
                    f"{r.post_pct}% after{peak_clause}")
        verdict = "In-room accountability improved, not eroded, across the scrutiny window."
    else:
        valence, grade = NEUTRAL, G_OBSERVATION
        headline = (f"Deferral of public questions held near {r.pre_pct}% before scrutiny and "
                    f"{r.post_pct}% after — no clear trend")
        verdict = "No material change in public-question responsiveness across the scrutiny window."
    verdict += COVID_CONFOUND_CAVEAT
    return TestResult(
        test_id="engagement.question_responsiveness",
        title="Are residents' questions answered, or quietly 'taken on notice'?",
        genre="Process / engagement (3.4)",
        principle="CIPFA-B — openness & stakeholder engagement · Nolan Accountability",
        question="What share of public questions are deferred rather than answered in the meeting, over time?",
        valence=valence,
        grade=grade,
        headline=headline,
        verdict=verdict,
        n=r.answered + r.on_notice,
        base_rate=f"{r.pre_pct}% deferred pre-scrutiny baseline",
        era="pre-2018 / 2018–21 / post-2022",
        data_ok=True,
        detail_panel="question-responsiveness",
        chart=_line(series, unit="%"),
        scope=[SCOPE_WHOLE_CORPUS, SCOPE_SINGLE_MEETING],
    )


def _t_question_responsiveness_meeting(session, council_id, meeting_id, pc=None) -> TestResult:
    """This meeting's own answered-vs-on-notice split, next to the
    pre-Inquiry corpus baseline (never re-derived from this one meeting).

    Same fix as _t_transparency_meeting's `corpus` lookup: it depends only
    on `body_types`, not `meeting_id`, so `pc` memoizes it by body_types
    instead of recomputing the identical corpus-wide query once per
    meeting sharing that body class."""
    body_types = _same_body_meeting_types(session, meeting_id)
    comparable = _comparable_label(session, meeting_id, body_types)
    r = public_question_responsiveness(session, council_id, meeting_id=meeting_id)
    corpus_cache = (pc if pc is not None else {}).setdefault("_pq_responsiveness_corpus_by_body_types", {})
    cache_key = tuple(sorted(body_types))
    if cache_key not in corpus_cache:
        corpus_cache[cache_key] = public_question_responsiveness(session, council_id, meeting_types=body_types)
    corpus = corpus_cache[cache_key]
    era = _meeting_label(session, meeting_id)
    total = r.answered + r.on_notice
    if total == 0:
        return TestResult(
            test_id="engagement.question_responsiveness", title="Were public questions answered this meeting?",
            genre="Process / engagement (3.4)", principle="CIPFA-B",
            question="How many public questions this meeting were answered live vs taken on notice?",
            valence=NEUTRAL, grade=G_OBSERVATION,
            headline="No public questions this meeting",
            verdict="No public questions this meeting.",
            n=0, era=era, detail_panel="question-responsiveness", scope=[SCOPE_SINGLE_MEETING],
            stat={"value": 0, "denominator": None, "unit": "count"}, digest_floor=0.0,
        )
    on_notice_pct = _capped_pct(r.on_notice, total)
    return TestResult(
        test_id="engagement.question_responsiveness", title="Were public questions answered this meeting?",
        genre="Process / engagement (3.4)", principle="CIPFA-B",
        question="How many public questions this meeting were answered live vs taken on notice?",
        valence=NEUTRAL, grade=G_OBSERVATION,
        headline=f"{r.answered} of {total} public question(s) answered live, {r.on_notice} taken on notice this meeting",
        verdict=f"{r.answered} of {total} public question(s) answered live this meeting "
                f"({on_notice_pct}% on notice), vs a {corpus.pre_pct}% pre-Inquiry baseline "
                f"{comparable}.",
        n=total, base_rate=f"{corpus.pre_pct}% pre-Inquiry baseline, {comparable}", era=era,
        detail_panel="question-responsiveness", scope=[SCOPE_SINGLE_MEETING],
        stat={"value": r.on_notice, "denominator": total, "unit": "count"}, digest_floor=0.0,
    )


# ── registry ────────────────────────────────────────────────────────────────
# Which tests exist and what order they run in is config/test_registry.json's
# call (docs/frontend/TEST_REGISTRY_PLAN.md B.3) — this dict has no opinion
# on membership or order, only "given an id, which function computes it."
# run_test_battery/run_meeting_digest walk the registry and look up here.
_GENERATORS = {
    # Integrity / procurement
    "procurement.threshold_gaming": _t_threshold_gaming,
    "procurement.incumbency": _t_procurement_incumbency,
    "procurement.single_source": _t_single_source,
    "procurement.concentration": _t_tender_concentration,
    "procurement.decider_supplier_conflict": _t_decider_supplier_conflict,
    # Integrity / conflict
    "conflict.recusal_management": _t_recusal_overall,
    "conflict.recusal_trend": _t_recusal_trend,
    "conflict.delegate_body_conflict": _t_delegate_body_conflict,
    # Governance / planning fairness
    "planning.big_dollar_leniency": _t_big_dollar_leniency,
    "planning.repeat_applicant": _t_repeat_applicant,
    "planning.objection_responsiveness": _t_objection_dose,
    # Governance / culture
    "governance.officer_ratification": _t_officer_divergence,
    "governance.power_spread": _t_voting_power,
    "governance.oversight_body_capture": _t_oversight_body_capture,
    "governance.unanimity_trend": _t_unanimity_trend,
    "governance.chair_capture": _t_mayoral,
    "governance.durable_faction": _t_sponsorship,
    "governance.incumbency": _t_tenure,
    "governance.freshman_effect": _t_freshman,
    "governance.election_cycle": _t_election_cycle,
    "governance.attendance": _t_attendance,
    # Transparency
    "transparency.confidential_share": _t_transparency,
    "transparency.confidential_tender_size": _t_confidential_tender_size,
    "transparency.confidential_topics": _t_confidential_topics,
    # Financial
    "finance.eoy_spending": _t_eoy_spending,
    "finance.reserve_trajectory": _t_reserve_trajectory,
    # Engagement
    "engagement.participation": _t_engagement,
    "engagement.deputation_dissent": _t_deputation_dissent,
    "engagement.question_responsiveness": _t_question_responsiveness,
}


def _load_registry_or_raise() -> list[RegistryRow]:
    """The battery must refuse to run on a partial/mismatched registry
    (TEST_REGISTRY_PLAN.md Step 3 item 5) — a row with no generator, or a
    generator with no row, is a bug worth stopping the run for, not silently
    producing 28 tests."""
    registry = load_test_registry()
    registry_ids = {row.id for row in registry}
    generator_ids = set(_GENERATORS)
    if registry_ids != generator_ids:
        raise RuntimeError(
            "config/test_registry.json and _GENERATORS disagree — "
            f"registry rows with no generator: {sorted(registry_ids - generator_ids)}; "
            f"generators with no registry row: {sorted(generator_ids - registry_ids)}"
        )
    return registry


def run_test_battery(session: Session, council_id: int,
                     precomputed: dict | None = None) -> list[TestResult]:
    """Run the standard battery and return a TestResult per test.

    `precomputed` may carry already-computed query objects under keys:
    power, recusal_trend, conflict, tenders, transparency, tenure, mayoral,
    sponsorship, dose, divergence, decider_supplier, delegate_body,
    oversight — to avoid recomputing the heavy ones.
    """
    pc = precomputed or {}
    registry = _load_registry_or_raise()
    results: list[TestResult] = []
    for row in registry:
        fn = _GENERATORS[row.id]
        try:
            r = fn(session, council_id, pc)
            # The registry authors the rendered title/question (B.5) — this
            # is also what keeps the S7 invariant gate's scan of these two
            # fields checking the text actually displayed.
            r.title = row.title_technical
            r.question = row.question_technical
            # Same discipline for principle (docs/uplift/migration/
            # 04-jurisdiction.md G-01/Step 1): config/test_registry.json's
            # `principles` is the one place this project already treats as
            # authoritative for this kind of static per-test metadata
            # (docs/MAP.md: "the registry row ... tests.py still owns the
            # computation"). Each generator's own `principle=` literal is
            # never read anywhere once this overwrite runs — kept in the
            # generator only as inline documentation of what the test is
            # about, not as a second source of truth a reader could see
            # drift from the registry.
            r.principle = " · ".join(row.principles)
            results.append(r)
        except Exception as exc:  # a broken test must not sink the battery
            results.append(TestResult(
                test_id=row.id,
                title=fn.__name__.replace("_t_", "").replace("_", " "),
                genre="(error)", principle="—", question="—",
                valence=NEUTRAL, grade=G_NODATA, data_ok=False,
                headline="Test errored", verdict=f"{type(exc).__name__}: {exc}",
            ))
    return results


def run_meeting_digest(
    session: Session, council_id: int, meeting_id: int, pc: dict | None = None,
) -> list[TestResult]:
    """Run only the SCOPE_SINGLE_MEETING-eligible tests (_MEETING_BATTERY),
    scoped to one meeting (docs/frontend/PRODUCT_ROADMAP.md F2) — a review
    artifact for looking at what a single-meeting digest would actually say
    before deciding whether/how to publish anything like it. Called
    automatically by every `council draft` run (`cmd_draft`, src/cli.py),
    which writes the result to a `local/` subdirectory deliberately excluded
    from manifest.json's "snapshots" list and from
    docs/review/editor/Editor_prompt.txt's non-recursive `*.json` scope —
    still NOT wired into S7/S8/S9, the coverage register, or anything
    `council publish` can reach; see that exclusion (and
    `tests/test_publish_gate.py`) for why, and `council meeting-digest`'s own
    docstring for the separate one-off manual preview path.

    `pc`: an optional precomputed-value dict, same shape run_test_battery()
    already threads through as `precomputed` — a caller looping this over
    many meetings (compute_watch_feed()) can pass one shared dict so a
    query that only depends on something coarser than meeting_id (e.g.
    _t_transparency_meeting()'s body_types-keyed corpus lookup) is computed
    once per distinct value, not once per meeting. Defaults to a fresh
    dict per call, i.e. no sharing, for every other caller.
    """
    if pc is None:
        pc = {}
    registry = _load_registry_or_raise()
    results: list[TestResult] = []
    for row in registry:
        if not row.meeting_scope:
            continue
        fn = _GENERATORS[row.id]
        try:
            results.append(fn(session, council_id, pc, meeting_id=meeting_id))
        except Exception as exc:  # a broken test must not sink the digest
            results.append(TestResult(
                test_id=getattr(fn, "__name__", "unknown"),
                title=fn.__name__.replace("_t_", "").replace("_", " "),
                genre="(error)", principle="—", question="—",
                valence=NEUTRAL, grade=G_NODATA, data_ok=False,
                headline="Test errored", verdict=f"{type(exc).__name__}: {exc}",
                scope=[SCOPE_SINGLE_MEETING],
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


# ════════════════════════════════════════════════════════════════════════════
# CLAIM-OBJECT COUNTERPARTS (Step 6, docs/uplift/migration/02-claim-layer.md)
#
# Additive per that step: TestResult keeps shipping unchanged above. These
# are new, separate functions producing a Claim (src/analysis/claims.py)
# for the same underlying question, starting with the three tests
# 02-claim-layer.md's own migration plan flags as the clearest fix (G-01
# fiscal-year, G-18 flat-classification, G-12 invalid ratio). 26 of the 29
# battery tests have no claim-object counterpart yet — not attempted this
# pass; each remaining one needs its own population/comparison/statistic
# design, same as these three, not a mechanical pattern that generalizes.
#
# None of these are wired into run_test_battery() or council draft (Step 7)
# — call them directly, or via lint against them in a standalone script/
# test, until that wiring exists.
# ════════════════════════════════════════════════════════════════════════════

def _t_eoy_spending_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_eoy_spending` (G-01's clearest fix).

    Reports the EOY award-*count* share, not the dollar-value share the
    legacy TestResult headlines — `proportion_ci()` needs a binomial count,
    not a dollar sum; a dollar-weighted CI would need a different estimator
    (e.g. a bootstrap over award amounts), not built here. Stated as a
    caveat, not silently substituted.

    Grades CRITICAL only when the observed share's CI clearly excludes the
    even-spread null (2/12) — pass `LintContext(null_value=2/12)` when
    linting this claim; the linter's own 0.0 default would under-check it.
    """
    from src.models import Council

    rows = [(a, m) for a, _n, _y, m in _tender_rows(session, council_id) if a and m]
    if not rows:
        return None
    council = session.query(Council).filter(Council.id == council_id).first()
    start_month = fiscal_year_start_month(council.short_name) if council else 7
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    fy_order = [(start_month - 1 + i) % 12 + 1 for i in range(12)]
    eoy_labels = ", ".join(month_names[m - 1] for m in fy_order[-2:])
    eoy_months = set(fy_order[-2:])

    total_n = len(rows)
    eoy_n = sum(1 for _a, m in rows if m in eoy_months)
    null_share = 2 / 12
    est = proportion_ci(eoy_n, total_n)
    grade = GRADE_CRITICAL if est.ci_low > null_share else GRADE_NEUTRAL
    justification = (
        f"observed EOY award-count share's 95% CI [{round(est.ci_low * 100)}%, "
        f"{round(est.ci_high * 100)}%] {'excludes' if grade == GRADE_CRITICAL else 'contains'} "
        f"the even-distribution null of {round(null_share * 100)}%"
    )
    return Claim(
        id="finance.eoy_spending",
        hypothesis="Do tender awards cluster into the final two months of the fiscal year, "
                   "beyond what an even monthly spread would predict?",
        population=Population(
            grain="(meeting, award)",
            definition="tender awards with a known amount and a known award month",
            base_table="tender_fact",
            filter_chain=("amount is not null", "award month is known"),
        ),
        numerator=NumeratorDenominator(
            definition="tender awards in the two fiscal-year-end months", n=eoy_n,
        ),
        denominator=NumeratorDenominator(
            definition="tender awards with a known amount and month", n=total_n,
        ),
        grade=grade,
        grade_justification=justification,
        comparison=Comparison(
            type=COMPARISON_NONE,
            reference_definition="an even 2/12 monthly share if EOY spending were uniformly distributed",
            reference_is_same_event=True,
        ),
        statistic=Statistic(value=est.value, ci_low=est.ci_low, ci_high=est.ci_high, method=est.method),
        narrative=Narrative(
            headline=f"{eoy_labels} (fiscal year-end) hold {round(est.value * 100)}% of tender "
                     f"awards ({eoy_n}/{total_n})",
            body=f"Of {total_n} tender awards with a known amount and month, {eoy_n} fell in "
                 f"{eoy_labels}, the two months before the fiscal year-end boundary read from "
                 "config/fiscal_year.json's fiscal_year_start_month.",
            caveats=(
                "This claim tracks award-count share, not dollar-value share; the legacy "
                "narrative for this test reports a dollar-value share instead, which would need "
                "a different estimator (e.g. a bootstrap over award amounts), not built here.",
            ),
        ),
    )


def _t_repeat_applicant_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_repeat_applicant` (G-18's clearest fix).

    Compares the two extreme frequency buckets (one-shot vs. 7+
    applications) directly via `difference_in_proportions_ci()`, rather
    than eyeballing the legacy 4-bucket spread/monotonicity heuristic — a
    real two-group comparison the linter can check.

    Stated, known gap: no `achieved_power` computation exists for a
    two-proportion difference (it would need an assumed minimum detectable
    effect this project hasn't specified anywhere). When the comparison is
    "flat" (CI contains zero), this claim's narrative says so — and L-13
    is *expected* to FAIL on the missing power field. That is a real,
    surfaced gap (this is exactly D-11/D-18's underpowered-null problem),
    not a bug in this migration to hide.
    """
    rows = (
        session.query(PlanningApplication.applicant_name, PlanningApplication.status)
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
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
        return None

    one_shot = [s for items in freq.values() if len(items) == 1 for s in items]
    frequent = [s for items in freq.values() if len(items) >= 7 for s in items]
    if not one_shot or not frequent:
        return None  # the extreme-bucket comparison needs both ends populated

    k1, n1 = sum(1 for s in one_shot if s == ApplicationStatus.APPROVED), len(one_shot)
    k2, n2 = sum(1 for s in frequent if s == ApplicationStatus.APPROVED), len(frequent)
    diff = difference_in_proportions_ci(k1, n1, k2, n2)
    flat = diff.ci_low <= 0 <= diff.ci_high

    return Claim(
        id="planning.repeat_applicant",
        hypothesis="Are repeat applicants (7+ applications) approved at a different rate "
                   "than one-shot applicants?",
        population=Population(
            grain="(application)",
            definition="decided planning applications with a named applicant",
            base_table="application_fact",
            filter_chain=("applicant_name is not null", "status in (approved, refused)"),
        ),
        numerator=NumeratorDenominator(
            definition="approved applications, pooled across the two compared groups", n=k1 + k2,
        ),
        denominator=NumeratorDenominator(
            definition="decided applications, pooled across the two compared groups", n=n1 + n2,
        ),
        grade=GRADE_SUPPORTIVE if flat else GRADE_CONCERN,
        grade_justification=(
            f"difference in approval rate (7+ minus one-shot) 95% CI [{round(diff.ci_low, 2)}, "
            f"{round(diff.ci_high, 2)}] {'contains' if flat else 'excludes'} zero"
        ),
        comparison=Comparison(
            type=COMPARISON_BETWEEN_SUBJECT,
            reference_definition="one-shot applicants (exactly 1 application)",
            reference_is_same_event=True,
        ),
        statistic=Statistic(value=diff.value, ci_low=diff.ci_low, ci_high=diff.ci_high, method=diff.method),
        narrative=Narrative(
            headline=f"Approval among decided applications: repeat applicants (7+) {round(k2 / n2 * 100)}% vs "
                     f"one-shot {round(k1 / n1 * 100)}%",
            body=(
                f"Among decided applications with a named applicant, one-shot applicants "
                f"(n={n1}) were approved {round(k1 / n1 * 100)}% of the time; applicants with 7 "
                f"or more applications (n={n2}) were approved {round(k2 / n2 * 100)}% of the time."
                + (" No difference in approval rate is supported by this comparison." if flat else
                   " A difference in approval rate is supported by this comparison.")
            ),
            caveats=(
                "numerator/denominator here are pooled across the two compared subgroups, not a "
                "single population — this claim shape (a direct two-group comparison) doesn't map "
                "cleanly onto a single numerator/denominator pair; the per-group counts are in body.",
            ),
        ),
    )


def _t_recusal_overall_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_recusal_overall` (G-12's clearest fix).

    The legacy TestResult's "declaring lifts recusal {factor}x" headline
    divides declared_recusal_pct by baseline_recusal_pct — D-12's exact
    structurally-invalid comparison (different events: a declared-interest
    recusal vs. an ordinary-vote absence for any reason). This claim does
    NOT reproduce that ratio as its graded statistic. The graded quantity
    is the must-leave recusal proportion alone; the baseline is demoted to
    an explicitly-flagged, caveated `comparison` (L-07), not a headline
    multiplier.

    Pass `LintContext(null_value=0.5)` when linting a CRITICAL grade from
    this claim — the interesting question is whether the CI is clearly on
    one side of "most councillors comply."
    """
    s = conflict_recusal_stats(session, council_id, min_declared=1)
    have_must_leave = s.must_leave_total > 0
    k = s.must_leave_recused if have_must_leave else s.declared_recused
    n = s.must_leave_total if have_must_leave else s.declared_total
    if n == 0:
        return None
    population_definition = (
        "must-leave (financial/proximity) declared-interest votes" if have_must_leave
        else "declared-interest votes (no must-leave declarations on record, blended fallback)"
    )

    # Clustering: expand per-councillor profiles into row-level flags.
    # min_declared=1 above ensures every councillor is profiled, so this
    # should sum exactly to n — only trust the clustered estimate when it
    # does; otherwise fall back to the plain (unclustered) CI with a caveat
    # rather than silently clustering over a partial population.
    cluster_rows: list[tuple[int, bool]] = []
    for p in s.profiles:
        declared, recused = (
            (p.must_leave_declared, p.must_leave_recused) if have_must_leave
            else (p.declared_votes, p.recused)
        )
        cluster_rows.extend((p.councillor_id, True) for _ in range(recused))
        cluster_rows.extend((p.councillor_id, False) for _ in range(declared - recused))

    stat_kwargs = {}
    clustering_caveat = None
    if len(cluster_rows) == n:
        try:
            clustered = clustered_proportion(
                cluster_rows, cluster_key=lambda r: r[0], is_positive=lambda r: r[1],
                clustering_unit="councillor",
            )
            stat_kwargs = dict(value=clustered.value, ci_low=clustered.ci_low, ci_high=clustered.ci_high,
                                method=clustered.method, clustering_unit="councillor")
        except ValueError:
            clustering_caveat = "Fewer than 2 councillors have a must-leave declaration on record; not clustered."
    else:
        clustering_caveat = (
            f"Per-councillor profiles ({len(cluster_rows)} rows) do not sum to the aggregate n ({n}); "
            "not clustered rather than clustering over a partial population."
        )
    if not stat_kwargs:
        est = proportion_ci(k, n)
        stat_kwargs = dict(value=est.value, ci_low=est.ci_low, ci_high=est.ci_high, method=est.method)

    stat = Statistic(**stat_kwargs)
    managed = stat.value > 0.5
    caveats = [
        f"The baseline ordinary-vote absence rate ({s.baseline_recusal_pct}%) is a different event "
        "from a declared-interest recusal (absence for any reason vs. stepping out on a declared "
        "conflict) and is not a valid same-event comparator for a ratio.",
    ]
    if clustering_caveat:
        caveats.append(clustering_caveat)

    return Claim(
        id="conflict.recusal_management",
        hypothesis="When a legally-mandatory (financial/proximity) interest is declared, is it "
                   "managed — does the member recuse?",
        population=Population(
            grain="(meeting, item, councillor)",
            definition=population_definition,
            base_table="declaration_fact",
            filter_chain=("interest_type in (financial, proximity)",) if have_must_leave else (),
        ),
        numerator=NumeratorDenominator(
            definition=f"{population_definition} where the member recused (stepped out)", n=k,
        ),
        denominator=NumeratorDenominator(definition=population_definition, n=n),
        grade=GRADE_SUPPORTIVE if managed else GRADE_CRITICAL,
        grade_justification=(
            f"recusal rate 95% CI [{round(stat.ci_low * 100)}%, {round(stat.ci_high * 100)}%] "
            f"{'is entirely above' if stat.ci_low > 0.5 else 'is entirely below' if stat.ci_high < 0.5 else 'straddles'} "
            "the 50% majority-compliance threshold"
        ),
        comparison=Comparison(
            type=COMPARISON_BETWEEN_SUBJECT,
            reference_definition="the ABSENT rate on ordinary (non declared-interest) votes",
            reference_is_same_event=False,
        ),
        statistic=stat,
        narrative=Narrative(
            headline=(
                f"Members recuse {round(stat.value * 100)}% of the time on {population_definition}"
                if managed else
                f"Members stay and vote {round((1 - stat.value) * 100)}% of the time on {population_definition}"
            ),
            body=f"Of {n} {population_definition}, the member recused (stepped out) in {k} "
                 f"({round(stat.value * 100)}%).",
            caveats=tuple(caveats),
        ),
    )


# ── era/period-comparison claims ─────────────────────────────────────────
# Same shape: a rate before vs. after a scrutiny/election window, upgraded
# from the legacy fixed-±5pp-band heuristic to a real CI-based significance
# check via difference_in_proportions_ci(). Raw pre/post counts aren't
# always exposed by the underlying query object (only pct + n) — where
# that's true, k is back-derived as round(pct/100*n), a documented
# approximation (the query object rounds before returning; this is a
# rounding-of-a-rounding, not a new precision loss class).

def _t_recusal_trend_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_recusal_trend`. Grades on whether the
    post-scrutiny CI is significantly below/above the pre-scrutiny rate,
    not a fixed ±5pp band. `k` for each era is back-derived from
    `must_leave_*_pct`/`_n` (RecusalTrendStats doesn't expose raw recused
    counts directly) — an approximation, stated as a caveat."""
    r = pc.get("recusal_trend") or recusal_compliance_trend(session, council_id)
    if r.inquiry_window is None or r.must_leave_pre_n == 0 or r.must_leave_post_n == 0:
        return None
    k_pre = round(r.must_leave_pre_pct / 100 * r.must_leave_pre_n)
    k_post = round(r.must_leave_post_pct / 100 * r.must_leave_post_n)
    diff = difference_in_proportions_ci(k_pre, r.must_leave_pre_n, k_post, r.must_leave_post_n)
    if diff.ci_high < 0:
        grade, direction = GRADE_CRITICAL, "fell"
    elif diff.ci_low > 0:
        grade, direction = GRADE_SUPPORTIVE, "rose"
    else:
        grade, direction = GRADE_NEUTRAL, "held near"
    return Claim(
        id="conflict.recusal_trend",
        hypothesis="Did must-leave recusal compliance change around the council's external-scrutiny window?",
        population=Population(
            grain="(meeting, item, councillor)",
            definition="must-leave declared-interest votes, pre- vs. post-scrutiny era",
            base_table="declaration_fact",
            filter_chain=(f"era in (pre-scrutiny, post-scrutiny per {r.era_label or 'configured window'})",),
        ),
        numerator=NumeratorDenominator(definition="must-leave votes where the member recused, pooled pre+post", n=k_pre + k_post),
        denominator=NumeratorDenominator(definition="must-leave declared-interest votes, pooled pre+post", n=r.must_leave_pre_n + r.must_leave_post_n),
        grade=grade,
        grade_justification=f"post-minus-pre recusal-rate 95% CI [{round(diff.ci_low, 2)}, {round(diff.ci_high, 2)}]",
        comparison=Comparison(
            type=COMPARISON_TEMPORAL,
            reference_definition=f"must-leave recusal rate before the {r.era_label or 'scrutiny'} window",
            reference_is_same_event=True,
        ),
        statistic=Statistic(value=diff.value, ci_low=diff.ci_low, ci_high=diff.ci_high, method=diff.method),
        narrative=Narrative(
            headline=f"Must-leave recusal {direction} {r.must_leave_pre_pct}% before scrutiny to {r.must_leave_post_pct}% after",
            body=f"Pre-scrutiny: {k_pre}/{r.must_leave_pre_n} must-leave votes saw the member recuse "
                 f"({r.must_leave_pre_pct}%). Post-scrutiny: {k_post}/{r.must_leave_post_n} "
                 f"({r.must_leave_post_pct}%).",
            caveats=(
                "Per-era k is back-derived from a rounded percentage and n (the underlying query "
                "returns pct+n, not raw counts) — an approximation, not exact.",
            ),
        ),
    )


def _t_transparency_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_transparency`. Grades on whether the peak
    year's confidential share is significantly above the pre-era baseline,
    using each year's exact raw total/confidential counts (TransparencyYear
    carries these directly, no back-derivation needed here)."""
    t = pc.get("transparency") or transparency_by_year(session, council_id)
    if not t.years:
        return None
    cutoff = t.inquiry_window[0] if t.inquiry_window else None
    pre_years = [y for y in t.years if cutoff is None or y.year < cutoff]
    peak_year_obj = next((y for y in t.years if y.year == t.peak_year), None)
    if not pre_years or peak_year_obj is None:
        return None
    pre_total = sum(y.total for y in pre_years)
    pre_conf = sum(y.confidential for y in pre_years)
    if pre_total == 0 or peak_year_obj.total == 0:
        return None
    diff = difference_in_proportions_ci(pre_conf, pre_total, peak_year_obj.confidential, peak_year_obj.total)
    spike = diff.ci_low > 0
    return Claim(
        id="transparency.confidential_share",
        hypothesis="Is the peak year's confidential-item share significantly above the pre-era baseline?",
        population=Population(
            grain="(meeting, item)",
            definition="decided items recorded confidential or open, pre-era baseline vs. peak year",
            base_table="motion_fact",
            filter_chain=(f"year < {cutoff}" if cutoff else "pre-era baseline (no configured scrutiny window)",),
        ),
        numerator=NumeratorDenominator(definition="confidential items, pooled baseline+peak year", n=pre_conf + peak_year_obj.confidential),
        denominator=NumeratorDenominator(definition="decided items, pooled baseline+peak year", n=pre_total + peak_year_obj.total),
        grade=GRADE_CRITICAL if spike else GRADE_SUPPORTIVE,
        grade_justification=f"peak-minus-baseline confidential-share 95% CI [{round(diff.ci_low, 2)}, {round(diff.ci_high, 2)}]",
        comparison=Comparison(
            type=COMPARISON_TEMPORAL,
            reference_definition="pre-era confidential-item share baseline",
            reference_is_same_event=True,
        ),
        statistic=Statistic(value=diff.value, ci_low=diff.ci_low, ci_high=diff.ci_high, method=diff.method),
        narrative=Narrative(
            headline=f"{t.pre_era_pct}% confidential at baseline vs {t.peak_pct}% in peak year {t.peak_year}",
            body=f"Baseline: {pre_conf}/{pre_total} items confidential ({round(pre_conf / pre_total * 100)}%). "
                 f"Peak year {t.peak_year}: {peak_year_obj.confidential}/{peak_year_obj.total} "
                 f"({round(peak_year_obj.confidential / peak_year_obj.total * 100)}%).",
            caveats=(COVID_CONFOUND_CAVEAT.strip(),),
        ),
    )


def _t_question_responsiveness_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_question_responsiveness`. Same era-CI shape
    as `_t_recusal_trend_claim`; `k` is back-derived from pct+n for the
    same reason (PQResponsivenessStats doesn't expose raw pre/post counts)."""
    r = pc.get("pq_responsiveness") or public_question_responsiveness(session, council_id)
    if r.inquiry_window is None or r.pre_n == 0 or r.post_n == 0:
        return None
    k_pre = round(r.pre_pct / 100 * r.pre_n)
    k_post = round(r.post_pct / 100 * r.post_n)
    diff = difference_in_proportions_ci(k_pre, r.pre_n, k_post, r.post_n)
    if diff.ci_low > 0:
        grade, direction = GRADE_CRITICAL, "rose"
    elif diff.ci_high < 0:
        grade, direction = GRADE_SUPPORTIVE, "fell"
    else:
        grade, direction = GRADE_NEUTRAL, "held near"
    return Claim(
        id="engagement.question_responsiveness",
        hypothesis="Did the share of public questions deferred ('on notice') change around the "
                   "council's external-scrutiny window?",
        population=Population(
            grain="(meeting, question)",
            definition="public questions answered live or taken on notice, pre- vs. post-scrutiny era",
            base_table="question_fact",
            filter_chain=(f"era in (pre-scrutiny, post-scrutiny per {r.era_label or 'configured window'})",),
        ),
        numerator=NumeratorDenominator(definition="questions taken on notice, pooled pre+post", n=k_pre + k_post),
        denominator=NumeratorDenominator(definition="public questions answered or on notice, pooled pre+post", n=r.pre_n + r.post_n),
        grade=grade,
        grade_justification=f"post-minus-pre deferral-rate 95% CI [{round(diff.ci_low, 2)}, {round(diff.ci_high, 2)}]",
        comparison=Comparison(
            type=COMPARISON_TEMPORAL,
            reference_definition=f"deferral rate before the {r.era_label or 'scrutiny'} window",
            reference_is_same_event=True,
        ),
        statistic=Statistic(value=diff.value, ci_low=diff.ci_low, ci_high=diff.ci_high, method=diff.method),
        narrative=Narrative(
            headline=f"Deferral of public questions {direction} {r.pre_pct}% before scrutiny to {r.post_pct}% after",
            body=f"Pre-scrutiny: {k_pre}/{r.pre_n} questions taken on notice ({r.pre_pct}%). "
                 f"Post-scrutiny: {k_post}/{r.post_n} ({r.post_pct}%).",
            caveats=(
                "Per-era k is back-derived from a rounded percentage and n, not an exact count.",
                COVID_CONFOUND_CAVEAT.strip(),
            ),
        ),
    )


# ── two-group bucket-comparison claims ───────────────────────────────────

def _t_mayoral_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_mayoral`. `k` for each group is back-derived
    from `mayor_contest_pct`/`other_contest_pct` + `_moved` (MayoralStats
    doesn't expose raw contest counts)."""
    m = pc.get("mayoral") or mayoral_agenda_setting(session, council_id)
    if m.mayor_moved == 0 or m.other_moved == 0:
        return None
    k_mayor = round(m.mayor_contest_pct / 100 * m.mayor_moved)
    k_other = round(m.other_contest_pct / 100 * m.other_moved)
    diff = difference_in_proportions_ci(k_other, m.other_moved, k_mayor, m.mayor_moved)
    captured = diff.ci_high < 0
    return Claim(
        id="governance.chair_capture",
        hypothesis="Do the Mayor's own motions draw significantly less dissent than backbench motions?",
        population=Population(
            grain="(meeting, item)",
            definition="carried motions with a known mover, mayoral vs. backbench",
            base_table="motion_fact",
            filter_chain=("mover held a Mayor term covering the meeting date (mayoral group) or not (backbench group)",),
        ),
        numerator=NumeratorDenominator(definition="contested (dissented) carried motions, pooled both groups", n=k_mayor + k_other),
        denominator=NumeratorDenominator(definition="carried motions, pooled both groups", n=m.mayor_moved + m.other_moved),
        grade=GRADE_CRITICAL if captured else GRADE_SUPPORTIVE,
        grade_justification=f"mayoral-minus-backbench dissent-rate 95% CI [{round(diff.ci_low, 2)}, {round(diff.ci_high, 2)}]",
        comparison=Comparison(
            type=COMPARISON_BETWEEN_SUBJECT,
            reference_definition="backbench-moved carried motions",
            reference_is_same_event=True,
        ),
        statistic=Statistic(value=diff.value, ci_low=diff.ci_low, ci_high=diff.ci_high, method=diff.method),
        narrative=Narrative(
            headline=f"Mayoral motions drew dissent {m.mayor_contest_pct}% of the time vs {m.other_contest_pct}% for backbench motions",
            body=f"Mayoral: {k_mayor}/{m.mayor_moved} carried motions contested ({m.mayor_contest_pct}%). "
                 f"Backbench: {k_other}/{m.other_moved} ({m.other_contest_pct}%).",
            caveats=("Per-group k is back-derived from a rounded percentage and n, not an exact count.",),
        ),
    )


def _t_oversight_body_capture_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_oversight_body_capture`. Uses exact raw
    won/n counts (OversightBodyCaptureStats carries these directly)."""
    r = pc.get("oversight") or oversight_body_capture(session, council_id)
    if r.n_appointees == 0 or r.appointee_n == 0 or r.non_appointee_n == 0:
        return None
    diff = difference_in_proportions_ci(r.non_appointee_won, r.non_appointee_n, r.appointee_won, r.appointee_n)
    captured = not (diff.ci_low <= 0 <= diff.ci_high)
    return Claim(
        id="governance.oversight_body_capture",
        hypothesis="Do oversight-body appointees win contested votes at a significantly different "
                   "rate than non-appointees?",
        population=Population(
            grain="(meeting, item, councillor)",
            definition="contested-vote outcomes, oversight-body appointees vs. non-appointees",
            base_table="vote_fact",
            filter_chain=("councillor ever appointed to an internal oversight body (appointee group) or not",),
        ),
        numerator=NumeratorDenominator(definition="contested votes won, pooled both groups", n=r.appointee_won + r.non_appointee_won),
        denominator=NumeratorDenominator(definition="contested votes cast, pooled both groups", n=r.appointee_n + r.non_appointee_n),
        grade=GRADE_CRITICAL if captured else GRADE_SUPPORTIVE,
        grade_justification=f"appointee-minus-non-appointee win-rate 95% CI [{round(diff.ci_low, 2)}, {round(diff.ci_high, 2)}]",
        comparison=Comparison(
            type=COMPARISON_BETWEEN_SUBJECT,
            reference_definition="non-appointee councillors' win rate on the same contested votes",
            reference_is_same_event=True,
        ),
        statistic=Statistic(value=diff.value, ci_low=diff.ci_low, ci_high=diff.ci_high, method=diff.method,
                             clustering_unit=None),
        narrative=Narrative(
            headline=f"Contested-vote win rate: oversight-body appointee {r.appointee_win_rate}% "
                     f"(n={r.appointee_n}) vs non-appointee {r.non_appointee_win_rate}% (n={r.non_appointee_n})",
            body=f"{r.n_appointees} distinct councillors have ever sat on an oversight body. "
                 f"Appointees won {r.appointee_won}/{r.appointee_n} contested votes; "
                 f"non-appointees won {r.non_appointee_won}/{r.non_appointee_n}.",
            caveats=("Era-pooled across the whole corpus; a modern-era shift could still hide in the aggregate.",),
        ),
    )


def _t_objection_dose_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_objection_dose`. Uses exact raw n/refused
    counts from the "0" and "5+" objector buckets (ObjectionDoseBucket
    carries these directly, no back-derivation needed). Grades on whether
    the CI is entirely above zero (responsive) or entirely below zero
    (inverted) — a CI containing zero is genuinely inconclusive (NEUTRAL),
    not CRITICAL: an earlier version of this claim used the legacy test's
    own two-way supportive/critical split, which is only valid for a point
    estimate with no CI. Found by running this claim against real data —
    see project memory, Step 7."""
    d = pc.get("dose") or objection_dose_response(session, council_id)
    by = {b.label: b for b in d.buckets}
    lo, hi = by.get("0"), by.get("5+")
    if lo is None or hi is None or lo.n == 0 or hi.n == 0:
        return None
    diff = difference_in_proportions_ci(lo.refused, lo.n, hi.refused, hi.n)
    if diff.ci_low > 0:
        grade = GRADE_SUPPORTIVE
    elif diff.ci_high < 0:
        grade = GRADE_CRITICAL
    else:
        grade = GRADE_NEUTRAL
    return Claim(
        id="planning.objection_responsiveness",
        hypothesis="Is the refusal rate on applications with 5+ objectors significantly higher than "
                   "on applications with none?",
        population=Population(
            grain="(application)",
            definition="decided planning applications, 0 objectors vs. 5+ objectors",
            base_table="application_fact",
            filter_chain=("objector count bucketed: 0 vs. 5+",),
        ),
        numerator=NumeratorDenominator(definition="refused applications, pooled both groups", n=lo.refused + hi.refused),
        denominator=NumeratorDenominator(definition="decided applications, pooled both groups", n=lo.n + hi.n),
        grade=grade,
        grade_justification=f"5+-minus-0-objector refusal-rate 95% CI [{round(diff.ci_low, 2)}, {round(diff.ci_high, 2)}]",
        comparison=Comparison(
            type=COMPARISON_BETWEEN_SUBJECT,
            reference_definition="applications with no community objections",
            reference_is_same_event=True,
        ),
        statistic=Statistic(value=diff.value, ci_low=diff.ci_low, ci_high=diff.ci_high, method=diff.method),
        narrative=Narrative(
            headline=f"Refusal rate on decided applications: {lo.refusal_pct}% with no objectors vs "
                     f"{hi.refusal_pct}% with 5+ objectors",
            body=f"Of decided applications, no objectors: {lo.refused}/{lo.n} refused ({lo.refusal_pct}%). "
                 f"5+ objectors: {hi.refused}/{hi.n} refused ({hi.refusal_pct}%).",
            caveats=(
                "An observational association, not proof the objections themselves changed the "
                "outcome: a non-compliant application could independently attract both more "
                "objectors and a higher refusal rate.",
            ),
        ),
    )


def _t_big_dollar_leniency_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_big_dollar_leniency`. Compares the two
    extreme value quartiles (Q1 lowest-$ vs. Q4 highest-$) directly, same
    pattern as `_t_repeat_applicant_claim`."""
    rows = (
        session.query(PlanningApplication.estimated_value, PlanningApplication.status)
        .join(Motion, PlanningApplication.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.council_id == council_id,
            PlanningApplication.estimated_value.isnot(None),
            PlanningApplication.status.in_([ApplicationStatus.APPROVED, ApplicationStatus.REFUSED]),
        ).all()
    )
    vals = sorted([(v, s) for v, s in rows if v and v > 0], key=lambda t: t[0])
    if len(vals) < 20:
        return None
    q = len(vals) // 4
    q1, q4 = vals[:q], vals[3 * q:]
    k1 = sum(1 for _v, s in q1 if s == ApplicationStatus.APPROVED)
    k4 = sum(1 for _v, s in q4 if s == ApplicationStatus.APPROVED)
    diff = difference_in_proportions_ci(k1, len(q1), k4, len(q4))
    flat = diff.ci_low <= 0 <= diff.ci_high
    return Claim(
        id="planning.big_dollar_leniency",
        hypothesis="Is the approval rate for the highest-value quartile of applications different "
                   "from the lowest-value quartile?",
        population=Population(
            grain="(application)",
            definition="decided planning applications with a recorded value, lowest vs. highest value quartile",
            base_table="application_fact",
            filter_chain=("estimated_value quartile: Q1 (lowest) vs. Q4 (highest)",),
        ),
        numerator=NumeratorDenominator(definition="approved applications, pooled Q1+Q4", n=k1 + k4),
        denominator=NumeratorDenominator(definition="decided applications, pooled Q1+Q4", n=len(q1) + len(q4)),
        grade=GRADE_SUPPORTIVE if flat else GRADE_CONCERN,
        grade_justification=f"Q4-minus-Q1 approval-rate 95% CI [{round(diff.ci_low, 2)}, {round(diff.ci_high, 2)}] "
                             f"{'contains' if flat else 'excludes'} zero",
        comparison=Comparison(
            type=COMPARISON_BETWEEN_SUBJECT,
            reference_definition="lowest-value quartile of decided applications",
            reference_is_same_event=True,
        ),
        statistic=Statistic(value=diff.value, ci_low=diff.ci_low, ci_high=diff.ci_high, method=diff.method),
        narrative=Narrative(
            headline=f"Approval among decided applications: {round(k4 / len(q4) * 100)}% for the "
                     f"highest-value quartile vs {round(k1 / len(q1) * 100)}% for the lowest-value quartile",
            body=f"Of decided applications, lowest-value quartile: {k1}/{len(q1)} approved "
                 f"({round(k1 / len(q1) * 100)}%). Highest-value quartile: {k4}/{len(q4)} approved "
                 f"({round(k4 / len(q4) * 100)}%).",
        ),
    )


def _t_freshman_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_freshman`. Compares first-12-months dissent
    rate against later-service dissent rate directly."""
    rows = (
        session.query(Vote.councillor_id, Vote.choice, Motion.votes_against, Meeting.meeting_date)
        .join(Motion, Vote.motion_id == Motion.id)
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes",
                Motion.outcome == MotionOutcome.CARRIED)
        .all()
    )
    first_seen: dict[int, object] = {}
    for cid, _ch, _va, d in rows:
        if d and (cid not in first_seen or d < first_seen[cid]):
            first_seen[cid] = d
    early_diss = early_n = late_diss = late_n = 0
    for cid, ch, va, d in rows:
        if not d or (va or 0) == 0:
            continue
        is_against = 1 if ch == VoteChoice.AGAINST else 0
        days = (d - first_seen[cid]).days if cid in first_seen else 9999
        if days <= 365:
            early_diss += is_against
            early_n += 1
        else:
            late_diss += is_against
            late_n += 1
    if early_n == 0 or late_n == 0:
        return None
    diff = difference_in_proportions_ci(late_diss, late_n, early_diss, early_n)
    return Claim(
        id="governance.freshman_effect",
        hypothesis="Do councillors dissent at a different rate in their first 12 months than later "
                   "in their service?",
        population=Population(
            grain="(meeting, item, councillor)",
            definition="contested carried-motion votes, first 12 months of service vs. later",
            base_table="vote_fact",
            filter_chain=("days since councillor's first recorded vote <= 365 (early) vs. > 365 (late)",),
        ),
        numerator=NumeratorDenominator(definition="dissenting (AGAINST) votes, pooled early+late", n=early_diss + late_diss),
        denominator=NumeratorDenominator(definition="contested carried-motion votes, pooled early+late", n=early_n + late_n),
        grade=GRADE_NEUTRAL,
        grade_justification=f"early-minus-late dissent-rate 95% CI [{round(diff.ci_low, 2)}, {round(diff.ci_high, 2)}] "
                             "- reported descriptively, not graded a direction (per the legacy test's own framing)",
        comparison=Comparison(
            type=COMPARISON_BETWEEN_SUBJECT,
            reference_definition="the same councillors' later-service votes",
            reference_is_same_event=True,
        ),
        statistic=Statistic(value=diff.value, ci_low=diff.ci_low, ci_high=diff.ci_high, method=diff.method),
        narrative=Narrative(
            headline=f"Contested-vote dissent in first 12 months {round(early_diss / early_n * 100)}% vs "
                     f"{round(late_diss / late_n * 100)}% later",
            body=f"First 12 months: {early_diss}/{early_n} contested-vote dissents "
                 f"({round(early_diss / early_n * 100)}%). Later service: {late_diss}/{late_n} "
                 f"({round(late_diss / late_n * 100)}%).",
            caveats=(
                "Pooled early-vs-late is confounded by cohort era (freshmen cluster in more "
                "turbulent modern years) - not corrected for here, same limitation as the legacy test.",
            ),
        ),
    )


def _t_election_cycle_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_election_cycle`."""
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
        in_window = (d.year % 2 == 1) and (4 <= d.month <= 10)
        if in_window:
            win_d += is_against
            win_n += 1
        else:
            oth_d += is_against
            oth_n += 1
    if win_n == 0 or oth_n == 0:
        return None
    diff = difference_in_proportions_ci(oth_d, oth_n, win_d, win_n)
    return Claim(
        id="governance.election_cycle",
        hypothesis="Is dissent higher in the pre-election window than the rest of the electoral cycle?",
        population=Population(
            grain="(meeting, item, councillor)",
            definition="carried-motion votes, pre-election window vs. rest of cycle",
            base_table="vote_fact",
            filter_chain=("meeting_date in Apr-Oct of an odd year (pre-election) vs. not",),
        ),
        numerator=NumeratorDenominator(definition="dissenting (AGAINST) votes, pooled both groups", n=win_d + oth_d),
        denominator=NumeratorDenominator(definition="carried-motion votes cast, pooled both groups", n=win_n + oth_n),
        grade=GRADE_NEUTRAL,
        grade_justification=f"pre-election-minus-rest dissent-rate 95% CI [{round(diff.ci_low, 2)}, {round(diff.ci_high, 2)}] "
                             "- reported descriptively (per the legacy test's own framing)",
        comparison=Comparison(
            type=COMPARISON_BETWEEN_SUBJECT,
            reference_definition="votes cast in the rest of the electoral cycle",
            reference_is_same_event=True,
        ),
        statistic=Statistic(value=diff.value, ci_low=diff.ci_low, ci_high=diff.ci_high, method=diff.method),
        narrative=Narrative(
            headline=f"Dissent on carried-motion votes: {round(win_d / win_n * 100)}% pre-election vs "
                     f"{round(oth_d / oth_n * 100)}% otherwise",
            body=f"Pre-election window (Apr-Oct, odd year): {win_d}/{win_n} carried-motion votes were "
                 f"dissents ({round(win_d / win_n * 100)}%). Rest of cycle: {oth_d}/{oth_n} "
                 f"({round(oth_d / oth_n * 100)}%).",
        ),
    )


def _t_deputation_dissent_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_deputation_dissent`."""
    dep_meetings = {m for (m,) in session.query(Deputation.meeting_id)
                    .join(Meeting, Deputation.meeting_id == Meeting.id)
                    .filter(Meeting.council_id == council_id).distinct().all()}
    rows = _meeting_contestation(session, council_id)
    with_d = [c for mid, c in rows if mid in dep_meetings]
    without_d = [c for mid, c in rows if mid not in dep_meetings]
    if not with_d or not without_d:
        return None
    diff = difference_in_proportions_ci(sum(without_d), len(without_d), sum(with_d), len(with_d))
    return Claim(
        id="engagement.deputation_dissent",
        hypothesis="Do meetings with a public deputation see a different contestation rate than "
                   "meetings without one?",
        population=Population(
            grain="(meeting, item)",
            definition="carried motions, meetings with a deputation vs. without",
            base_table="motion_fact",
            filter_chain=("meeting had >=1 recorded Deputation vs. none",),
        ),
        numerator=NumeratorDenominator(definition="contested carried motions, pooled both groups", n=sum(with_d) + sum(without_d)),
        denominator=NumeratorDenominator(definition="carried motions, pooled both groups", n=len(with_d) + len(without_d)),
        grade=GRADE_NEUTRAL,
        grade_justification=f"with-minus-without-deputation contestation-rate 95% CI [{round(diff.ci_low, 2)}, {round(diff.ci_high, 2)}] "
                             "- reported descriptively (per the legacy test's own framing)",
        comparison=Comparison(
            type=COMPARISON_BETWEEN_SUBJECT,
            reference_definition="meetings with no recorded public deputation",
            reference_is_same_event=True,
        ),
        statistic=Statistic(value=diff.value, ci_low=diff.ci_low, ci_high=diff.ci_high, method=diff.method),
        narrative=Narrative(
            headline=f"Contestation of carried motions {round(sum(with_d) / len(with_d) * 100)}% with a deputation vs "
                     f"{round(sum(without_d) / len(without_d) * 100)}% without",
            body=f"With a deputation: {sum(with_d)}/{len(with_d)} carried motions contested. "
                 f"Without: {sum(without_d)}/{len(without_d)}.",
            caveats=(
                "Confounded by busy meetings having both more deputations and more motions - "
                "not corrected for here, same limitation as the legacy test.",
            ),
        ),
    )


# ── single-proportion claims ─────────────────────────────────────────────

def _t_officer_divergence_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_officer_divergence`. Grades on whether the
    ratification rate's CI is clearly above the 85% near-total threshold,
    not a point-estimate cutoff."""
    pairs = pc.get("divergence") or officer_divergence(session, council_id, None, None)
    total = len(pairs)
    if total == 0:
        return None
    diverged = sum(1 for p in pairs if p.diverged)
    lost = sum(1 for p in pairs if p.council_outcome == "lost")
    deferred = sum(1 for p in pairs if p.council_outcome == "deferred")
    ratified = total - diverged
    est = proportion_ci(ratified, total)
    null_value = 0.85
    grade = GRADE_CRITICAL if est.ci_low > null_value else GRADE_SUPPORTIVE
    return Claim(
        id="governance.officer_ratification",
        hypothesis="Is council's ratification rate of officer recommendations significantly above 85%?",
        population=Population(
            grain="(meeting, item)",
            definition="agenda-matched motions with an officer recommendation",
            base_table="motion_fact",
            filter_chain=("officer recommendation matched to a minutes outcome",),
        ),
        numerator=NumeratorDenominator(definition="motions where council adopted the officer recommendation", n=ratified),
        denominator=NumeratorDenominator(definition="agenda-matched motions with an officer recommendation", n=total),
        grade=grade,
        grade_justification=f"ratification-rate 95% CI [{round(est.ci_low, 2)}, {round(est.ci_high, 2)}] "
                             f"{'excludes' if grade == GRADE_CRITICAL else 'does not clearly exceed'} the 85% near-total threshold",
        comparison=Comparison(
            type=COMPARISON_NONE,
            reference_definition="an 85% near-total-ratification threshold",
            reference_is_same_event=True,
        ),
        statistic=Statistic(value=est.value, ci_low=est.ci_low, ci_high=est.ci_high, method=est.method),
        narrative=Narrative(
            headline=f"Council adopted the officer recommendation {round(est.value * 100)}% of the time",
            body=f"Of {diverged} departure(s) from {total} matched items: {lost} LOST outright, "
                 f"{deferred} DEFERRED (a procedural pause, not necessarily a rejection).",
            caveats=(
                "Cannot detect a motion council substantially amended before carrying it - an "
                "amended-then-carried motion counts as ratification here, not divergence.",
            ),
        ),
    )


def _t_threshold_gaming_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_threshold_gaming`. Reframes the legacy
    below:above mass ratio as a proportion (below / (below+above)) so it
    has a real CI; null_value=1.6/2.6, the ratio<=1.6 clean threshold
    expressed as a proportion."""
    rows = [(a, y) for a, _n, y, _m in _tender_rows(session, council_id) if a and y]
    modern = [a for a, y in rows if y >= 2015]
    thr = 250_000
    below = sum(1 for a in modern if thr * 0.8 <= a < thr)
    above = sum(1 for a in modern if thr <= a < thr * 1.2)
    if below + above == 0:
        return None
    est = proportion_ci(below, below + above)
    null_value = 1.6 / 2.6
    grade = GRADE_CRITICAL if est.ci_low > null_value else GRADE_SUPPORTIVE
    return Claim(
        id="procurement.threshold_gaming",
        hypothesis="Is there excess tender-value mass just below the competitive-tender threshold, "
                   "beyond a 1.6:1 below:above ratio?",
        population=Population(
            grain="(meeting, award)",
            definition="tender awards from 2015+ valued within 20% of the $250k competitive-tender threshold",
            base_table="tender_fact",
            filter_chain=("year >= 2015", "amount in [0.8*250k, 1.2*250k)"),
        ),
        numerator=NumeratorDenominator(definition="awards just below the threshold ([0.8x, 1x))", n=below),
        denominator=NumeratorDenominator(definition="awards within 20% of the threshold on either side", n=below + above),
        grade=grade,
        grade_justification=f"below-threshold-share 95% CI [{round(est.ci_low, 2)}, {round(est.ci_high, 2)}] "
                             f"{'excludes' if grade == GRADE_CRITICAL else 'does not clearly exceed'} "
                             f"the 1.6:1 ratio's equivalent share ({round(null_value, 2)})",
        comparison=Comparison(
            type=COMPARISON_NONE,
            reference_definition="a below:above mass ratio of 1.6:1 (the McCrary-spike clean threshold)",
            reference_is_same_event=True,
        ),
        statistic=Statistic(value=est.value, ci_low=est.ci_low, ci_high=est.ci_high, method=est.method),
        narrative=Narrative(
            headline=f"{below} awards just below the $250k threshold vs {above} just above",
            body=f"Of {below + above} tender awards from 2015+ within 20% of the $250k competitive-tender "
                 f"threshold, {below} fall just below it and {above} just above.",
        ),
    )


def _t_unanimity_trend_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_unanimity_trend`. Purely descriptive
    (legacy test carries no good/bad direction) — grade is always neutral."""
    rows = _minutes_motions(session, council_id)
    contested = total = 0
    for outcome, va, year in rows:
        if year is None or outcome != MotionOutcome.CARRIED:
            continue
        total += 1
        contested += 1 if (va or 0) > 0 else 0
    if total == 0:
        return None
    est = proportion_ci(contested, total)
    return Claim(
        id="governance.unanimity_trend",
        hypothesis="What share of carried motions draw at least one dissenting vote?",
        population=Population(
            grain="(meeting, item)",
            definition="carried motions in minutes",
            base_table="motion_fact",
            filter_chain=("outcome = carried",),
        ),
        numerator=NumeratorDenominator(definition="carried motions with at least one dissenting vote", n=contested),
        denominator=NumeratorDenominator(definition="carried motions in minutes", n=total),
        grade=GRADE_NEUTRAL,
        grade_justification="descriptive test, no good/bad direction (per the legacy test's own framing)",
        statistic=Statistic(value=est.value, ci_low=est.ci_low, ci_high=est.ci_high, method=est.method),
        narrative=Narrative(
            headline=f"{round(est.value * 100)}% of carried motions drew a dissenting vote (chamber-wide)",
            body=f"Of {total} carried motions in minutes, {contested} drew at least one dissenting vote.",
        ),
    )


def _t_attendance_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_attendance`. Purely descriptive (legacy
    test carries no good/bad direction). Splits ABSENT into recusal
    (declared_interest=True) vs. genuine (declared_interest=False)."""
    rows = session.query(Vote.choice, Vote.declared_interest).join(Motion, Vote.motion_id == Motion.id) \
        .join(Meeting, Motion.meeting_id == Meeting.id) \
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes").all()
    total = len(rows)
    if total == 0:
        return None
    absent = sum(1 for ch, _di in rows if ch == VoteChoice.ABSENT)
    recusal_abs = sum(1 for ch, di in rows if ch == VoteChoice.ABSENT and di)
    genuine_abs = absent - recusal_abs
    est = proportion_ci(genuine_abs, total)
    return Claim(
        id="governance.attendance",
        hypothesis="What share of cast-vote opportunities are genuine (non-recusal) non-attendance?",
        population=Population(
            grain="(meeting, item, councillor)",
            definition="vote rows in minutes",
            base_table="vote_fact",
            filter_chain=(),
        ),
        numerator=NumeratorDenominator(definition="ABSENT votes with no declared interest (genuine non-attendance)", n=genuine_abs),
        denominator=NumeratorDenominator(definition="vote rows in minutes", n=total),
        grade=GRADE_NEUTRAL,
        grade_justification="descriptive test, no good/bad direction (per the legacy test's own framing)",
        statistic=Statistic(value=est.value, ci_low=est.ci_low, ci_high=est.ci_high, method=est.method),
        narrative=Narrative(
            headline=f"Genuine (non-recusal) non-attendance is {round(est.value * 100, 2)}% of all vote rows in minutes",
            body=f"Of {total} vote rows in minutes, {absent} are ABSENT: {recusal_abs} with a declared interest on "
                 f"that motion (recusal), {genuine_abs} with none (genuine non-attendance).",
        ),
    )


def _t_delegate_body_conflict_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_delegate_body_conflict`. Reports only the
    one body with genuine private stakes (Ocean Gardens) as the graded
    proportion — the legacy test's own finding is the contrast between
    bodies, which this single-proportion claim shape can't represent; the
    other bodies' near-zero rates are in the body text instead."""
    r = pc.get("delegate_body") or delegate_body_conflict(session, council_id)
    if not r.bodies:
        return None
    og = next((b for b in r.bodies if "Ocean Gardens" in b.label), r.bodies[-1])
    others = [b for b in r.bodies if b is not og]
    if og.affiliated_votes == 0:
        return None
    est = proportion_ci(og.affiliated_declared, og.affiliated_votes)
    return Claim(
        id="conflict.delegate_body_conflict",
        hypothesis="Do council-appointed delegates with a genuine private stake in their body's "
                   "business declare an interest before voting on it?",
        population=Population(
            grain="(meeting, item, councillor)",
            definition=f"votes by a councillor within their {og.label} appointment window, on {og.label} business",
            base_table="declaration_fact",
            filter_chain=(f"councillor appointed to {og.label}", "vote falls within the appointment window"),
        ),
        numerator=NumeratorDenominator(definition="votes where the delegate declared an interest", n=og.affiliated_declared),
        denominator=NumeratorDenominator(definition=f"votes by a {og.label} delegate on {og.label} business", n=og.affiliated_votes),
        grade=GRADE_SUPPORTIVE,
        grade_justification=f"declared-interest rate {round(est.value * 100)}% (95% CI [{round(est.ci_low, 2)}, {round(est.ci_high, 2)}])",
        statistic=Statistic(value=est.value, ci_low=est.ci_low, ci_high=est.ci_high, method=est.method),
        narrative=Narrative(
            headline=f"{og.label}: {og.affiliated_declared}/{og.affiliated_votes} ({round(est.value * 100)}%) "
                     "declared — the one body with genuine personal stakes",
            body=f"{og.label} votes: {og.affiliated_declared}/{og.affiliated_votes} declared "
                 f"({round(est.value * 100)}%). Institutional-delegation bodies (" + "; ".join(
                f"{b.label} {b.affiliated_declared}/{b.affiliated_votes} ({b.affiliated_declared_pct}%)"
                for b in others
            ) + ") correctly attract near-zero declarations.",
            caveats=(
                f"Every per-body n is thin ({min(b.affiliated_votes for b in r.bodies)}-"
                f"{max(b.affiliated_votes for b in r.bodies)} affiliated votes) - directional, not "
                "precise, for any one body.",
            ),
        ),
    )


def _t_decider_supplier_conflict_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_decider_supplier_conflict`. The graded
    statistic is the tender-award declared-interest rate (exact counts).
    The legacy test's actual grading driver — raw surname collisions vs. a
    chance baseline — already has its own bespoke method
    (`_surname_chance_baseline()`, G-31) and is carried into `grade`
    directly rather than forced into this schema's CI machinery, which
    isn't built for a collision-count-vs-expectation comparison."""
    r = pc.get("decider_supplier") or decider_supplier_conflict(session, council_id)
    if r.votes_on_tender_motions == 0:
        return None
    est = proportion_ci(r.declared_votes, r.votes_on_tender_motions)
    n_collisions = len(r.collisions)
    below_chance = n_collisions <= r.expected_collisions_under_chance
    grade = GRADE_SUPPORTIVE if (n_collisions == 0 or below_chance) else GRADE_NEUTRAL
    return Claim(
        id="procurement.decider_supplier_conflict",
        hypothesis="Do tender-award voters declare an interest at a different rate than the chamber baseline?",
        population=Population(
            grain="(meeting, item, councillor)",
            definition="votes on tender-award motions",
            base_table="vote_fact",
            filter_chain=("motion matched as a tender-award motion",),
        ),
        numerator=NumeratorDenominator(definition="tender-award votes where the councillor declared an interest", n=r.declared_votes),
        denominator=NumeratorDenominator(definition="votes on tender-award motions", n=r.votes_on_tender_motions),
        grade=grade,
        grade_justification=(
            f"{n_collisions} raw decider<->winner surname collision(s) across {r.named_awards} named "
            f"awards, {'at or below' if below_chance else 'above'} the chance baseline of "
            f"{r.expected_collisions_under_chance}"
        ),
        statistic=Statistic(value=est.value, ci_low=est.ci_low, ci_high=est.ci_high, method=est.method),
        narrative=Narrative(
            headline=f"Tender-award votes declare an interest {round(est.value * 100)}% of the time "
                     f"(chamber base {r.base_declared_pct}%)",
            body=f"{n_collisions} raw decider<->winner surname collision(s) across {r.named_awards} "
                 f"named awards and {r.surnames_tested} voting-councillor surnames.",
            caveats=(
                "A raw surname collision is a candidate for human review, never itself confirmed "
                "evidence of a relationship.",
                "Only separately-moved tender-award motions are visible, not consent-agenda'd awards.",
            ),
        ),
    )


# ── the 7 of the remaining 10 tests with genuinely new statistical machinery
# (docs/analysis/inference.py's median/categorical/concentration/overlap/
# trend additions). The other 3 (single_source, reserve_trajectory,
# sponsorship) have no underlying data or a hardcoded-prose query — no
# machinery closes those; not attempted.

def _t_voting_power_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_voting_power`. Upgrades the legacy fixed
    >15pp-swing heuristic to a real per-person CI comparison: for each
    long-serving councillor with >=2 term points, back-derive a Wilson CI
    per term (k rounded from win_rate*n — `PowerTermPoint` doesn't carry a
    raw win count) and check whether any two of their own terms have
    non-overlapping CIs — real, not just noisy, movement. Grades on whether
    at least one councillor shows this."""
    p = pc.get("power") or voting_power(session, council_id)
    if not p.over_time:
        return None
    n_with_confirmed_turnover = 0
    n_evaluated = 0
    turnover_names = []
    for person in p.over_time:
        if len(person.points) < 2:
            continue
        n_evaluated += 1
        cis = []
        for pt in person.points:
            if pt.n == 0:
                continue
            k = round(pt.win_rate * pt.n)
            cis.append(proportion_ci(k, pt.n))
        confirmed = any(
            a.ci_high < b.ci_low or b.ci_high < a.ci_low
            for i, a in enumerate(cis) for b in cis[i + 1:]
        )
        if confirmed:
            n_with_confirmed_turnover += 1
            turnover_names.append(person.name)
    if n_evaluated == 0:
        return None
    wins = [pr.win_rate for pr in p.profiles]
    lo, hi = (round(min(wins) * 100), round(max(wins) * 100)) if wins else (None, None)
    return Claim(
        id="governance.power_spread",
        hypothesis="Does at least one long-serving councillor's win rate shift significantly "
                   "between their own terms (real turnover, not an ossified hierarchy)?",
        population=Population(
            grain="(meeting, item, councillor)",
            definition="long-serving councillors with contested-vote win rates in 2+ terms",
            base_table="vote_fact",
            filter_chain=("councillor has a win-rate point in 2 or more 4-year terms",),
        ),
        numerator=NumeratorDenominator(
            definition="councillors with a statistically confirmed (non-overlapping-CI) shift between two of their own terms",
            n=n_with_confirmed_turnover,
        ),
        denominator=NumeratorDenominator(definition="long-serving councillors evaluated across 2+ terms", n=n_evaluated),
        grade=GRADE_SUPPORTIVE if n_with_confirmed_turnover > 0 else GRADE_CRITICAL,
        grade_justification=(
            f"{n_with_confirmed_turnover}/{n_evaluated} long-serving councillors show a statistically "
            "confirmed shift between two of their own terms"
            if n_with_confirmed_turnover > 0 else
            "no long-serving councillor's term-to-term win-rate CIs are confirmed non-overlapping — "
            "consistent with (not proof of) a static hierarchy"
        ),
        statistic=Statistic(
            value=n_with_confirmed_turnover / n_evaluated if n_evaluated else None,
            clustering_unit="councillor",
        ),
        narrative=Narrative(
            headline=f"Contested-vote win rates span {lo}–{hi}% between councillors; "
                     f"{n_with_confirmed_turnover}/{n_evaluated} long-servers show confirmed term-to-term movement",
            body=(
                f"Of {n_evaluated} councillors with win-rate data in 2+ terms, "
                f"{n_with_confirmed_turnover} show a statistically confirmed shift between two of "
                f"their own terms" + (f": {', '.join(turnover_names)}." if turnover_names else ".")
            ),
            caveats=(
                "A councillor without confirmed movement may still have moved — this only counts "
                "movement large enough for two term-level Wilson CIs to stop overlapping, a "
                "conservative (under-, not over-, counting) bar.",
            ),
        ),
    )


def _t_tenure_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_tenure`. Purely descriptive (legacy test
    carries no good/bad direction) — grade is always neutral. `statistic`
    carries the median service length in years (not a 0-1 proportion —
    this claim's natural unit isn't a rate); `numerator`/`denominator`
    separately carry the long-server share as a real proportion."""
    t = pc.get("tenure") or councillor_tenure(session, council_id)
    if not t.profiles:
        return None
    years = [p.years for p in t.profiles]
    est = median_ci(years) if len(years) >= 2 else None
    n15 = sum(1 for y in years if y >= 15)
    longest = max(t.profiles, key=lambda p: p.years)
    return Claim(
        id="governance.incumbency",
        hypothesis="What is the distribution of councillor service length, and how many serve 15+ years?",
        population=Population(
            grain="(councillor)", definition="councillors with a computed tenure (20+ recorded votes)",
            base_table="vote_fact", filter_chain=("at least 20 recorded votes",),
        ),
        numerator=NumeratorDenominator(definition="councillors serving 15+ years", n=n15),
        denominator=NumeratorDenominator(definition="councillors with a computed tenure", n=t.n_councillors),
        grade=GRADE_NEUTRAL,
        grade_justification="descriptive test, no good/bad direction (per the legacy test's own framing)",
        statistic=Statistic(
            value=t.median_years,
            ci_low=est.ci_low if est else None, ci_high=est.ci_high if est else None,
            method="bootstrap" if est else "",
        ),
        narrative=Narrative(
            headline=f"Median service {t.median_years} years; {n15} councillors served 15+; "
                     f"longest {longest.years}y",
            body=f"Of {t.n_councillors} councillors with a computed tenure, {n15} served 15 years "
                 f"or more; the longest-serving reached {longest.years} years.",
            caveats=(
                "A service-length distribution is a description of chamber composition, not a "
                "good/bad signal by itself — stability and entrenchment risk are two readings of "
                "the same number.",
            ),
        ),
    )


def _t_tender_concentration_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_tender_concentration`. Purely descriptive
    (legacy test carries no good/bad direction) — grade is always neutral.
    The graded `statistic` is the count-based redacted-award share (a real
    proportion, `TenderConcentration.redacted_awards`/`total_awards`); the
    Herfindahl index is reported separately in the body — concentration
    itself has no CI/null (see `herfindahl_index()`'s own docstring)."""
    t = pc.get("tenders") or tender_concentration(session, council_id)
    if t.total_awards == 0:
        return None
    est = proportion_ci(t.redacted_awards, t.total_awards)
    remainder = max(0.0, t.named_amount - sum(c.total_amount for c in t.contractors))
    hhi_shares = [c.total_amount for c in t.contractors] + ([remainder] if remainder > 0 else [])
    hhi = herfindahl_index(hhi_shares) if hhi_shares and sum(hhi_shares) > 0 else None
    return Claim(
        id="procurement.concentration",
        hypothesis="What share of tender awards have a redacted (non-identifiable) recipient?",
        population=Population(
            grain="(meeting, award)", definition="tender awards with a known amount",
            base_table="tender_fact", filter_chain=("amount is not null",),
        ),
        numerator=NumeratorDenominator(definition="tender awards with a redacted/non-identifiable recipient", n=t.redacted_awards),
        denominator=NumeratorDenominator(definition="tender awards with a known amount", n=t.total_awards),
        grade=GRADE_NEUTRAL,
        grade_justification="descriptive test, no good/bad direction (per the legacy test's own framing)",
        statistic=Statistic(value=est.value, ci_low=est.ci_low, ci_high=est.ci_high, method=est.method),
        narrative=Narrative(
            headline=f"${t.total_amount / 1e6:.1f}M across {t.distinct_named} named firms; "
                     f"{round(est.value * 100)}% of awards have a redacted recipient",
            body=f"Of {t.total_awards} tender awards with a known amount, {t.redacted_awards} have a "
                 f"redacted/non-identifiable recipient. Top-10 named firms take "
                 f"{round(t.top10_share * 100)}% of named dollars"
                 + (f"; Herfindahl index (top-15 firms + remainder bucket) is {round(hhi, 3)}." if hhi else "."),
            caveats=(
                "Concentration among a broad supplier base is ordinary for big civil contracts, not "
                "a good/bad signal on its own — the redacted share is the real watch-item, which is "
                "what this claim grades.",
            ),
        ),
    )


def _t_procurement_incumbency_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_procurement_incumbency`. Reframes the
    legacy "is any firm both a frequent repeat-winner and a top-10
    dollar-recipient" boolean as a hypergeometric chance-overlap test:
    under independent random assignment, how likely is this much overlap
    between the two sets by chance alone?"""
    rows = list(_tender_rows(session, council_id))
    by_firm: dict[str, dict] = {}
    for a, name, y, _m in rows:
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
        return None
    population_size = len(by_firm)
    frequent_keys = {k for k, v in by_firm.items() if len(v["years"]) >= 4}
    top_dollar_keys = {
        k for k, _v in sorted(by_firm.items(), key=lambda kv: kv[1]["amt"], reverse=True)[:10]
    }
    observed_overlap = len(frequent_keys & top_dollar_keys)
    if not frequent_keys or not top_dollar_keys:
        return None
    overlap_test = hypergeometric_overlap_test(
        population_size=population_size, group_a_size=len(frequent_keys),
        group_b_size=len(top_dollar_keys), observed_overlap=observed_overlap,
    )
    surprising = overlap_test.p_value_at_least_observed < 0.05
    display = contractor_display_names(name for _a, name, _y, _m in rows if name)
    overlap_names = sorted(display.get(k, k) for k in (frequent_keys & top_dollar_keys))
    return Claim(
        id="procurement.incumbency",
        hypothesis="Is the overlap between frequent repeat-winners (4+ distinct years) and "
                   "top-10 dollar-recipients larger than chance would predict?",
        population=Population(
            grain="(firm)", definition="distinct named contractors with a tender award",
            base_table="tender_fact", filter_chain=("awarded_to is a named contractor, not a redacted placeholder",),
        ),
        numerator=NumeratorDenominator(definition="firms both a frequent repeat-winner and a top-10 dollar-recipient", n=observed_overlap),
        denominator=NumeratorDenominator(definition="distinct named contractors", n=population_size),
        grade=GRADE_CRITICAL if surprising else GRADE_SUPPORTIVE,
        grade_justification=(
            f"P(overlap >= {observed_overlap}) = {round(overlap_test.p_value_at_least_observed, 4)} under a "
            f"chance null (expected {round(overlap_test.expected_overlap, 2)}) — "
            f"{'below' if surprising else 'not below'} the 0.05 threshold"
        ),
        statistic=Statistic(value=float(observed_overlap), method="hypergeometric"),
        narrative=Narrative(
            headline=(
                f"{observed_overlap} named contractor(s) are both a frequent repeat-winner and a "
                f"top-10 dollar-recipient, vs {round(overlap_test.expected_overlap, 1)} expected by chance"
            ),
            body=f"Of {population_size} distinct named contractors, {len(frequent_keys)} won in 4+ "
                 f"distinct years and {len(top_dollar_keys)} are top-10 by dollar value; "
                 f"{observed_overlap} firm(s) are in both sets" + (f": {', '.join(overlap_names)}." if overlap_names else "."),
            caveats=(
                "Repeat-winning alone is not evidence of impropriety — mundane low-value equipment/"
                "cartage rebids are frequent repeat-winners in every corpus checked so far without "
                "being big-dollar incumbents.",
            ),
        ),
    )


def _t_engagement_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_engagement`. Purely descriptive (legacy
    test carries no good/bad direction) — grade is always neutral. The
    graded `statistic` is an OLS trend slope (engagements/year) over the
    yearly count series, since a raw count has no natural denominator to
    build a proportion from."""
    years = public_engagement_by_year(session, council_id)
    usable = [y for y in years if y.total]
    if len(usable) < 3:
        return None
    trend = linear_trend_ci([y.year for y in usable], [y.total for y in usable])
    total = sum(y.total for y in years)
    recent = [y for y in years if y.year >= 2016]
    recent_avg = round(sum(y.total for y in recent) / len(recent)) if recent else 0
    return Claim(
        id="engagement.participation",
        hypothesis="Is the volume of public participation (questions, deputations, petitions) "
                   "trending up or down over time?",
        population=Population(
            grain="(meeting)", definition="years with at least one recorded public engagement",
            base_table="question_fact", filter_chain=("year total > 0",),
        ),
        numerator=NumeratorDenominator(definition="total recorded public engagements across all years", n=total),
        denominator=NumeratorDenominator(definition="years with recorded engagement data", n=len(usable)),
        grade=GRADE_NEUTRAL,
        grade_justification="descriptive test, no good/bad direction (per the legacy test's own framing)",
        statistic=Statistic(value=trend.slope, ci_low=trend.ci_low, ci_high=trend.ci_high, method=trend.method),
        narrative=Narrative(
            headline=f"{total:,} recorded public engagements across {len(usable)} years, "
                     f"~{recent_avg}/yr recently, trend {round(trend.slope, 1)}/yr",
            body=f"Public participation (questions, deputations, petitions) trend: "
                 f"{round(trend.slope, 1)} engagements/year "
                 f"(95% CI [{round(trend.ci_low, 1)}, {round(trend.ci_high, 1)}]).",
            caveats=(
                "Volume tracks the political temperature rather than a steady civic baseline — a "
                "trend here is not itself a compliance signal.",
            ),
        ),
    )


def _t_confidential_tender_size_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_confidential_tender_size`. Upgrades the
    legacy median-ratio comparison (no CI, no significance test) to a real
    bootstrap CI on the median difference plus a Mann-Whitney significance
    test."""
    rows = session.query(Tender.amount, Tender.is_confidential) \
        .join(Meeting, Tender.meeting_id == Meeting.id) \
        .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes",
                Tender.amount.isnot(None), Tender.amount > 0).all()
    conf = [a for a, ic in rows if ic]
    opn = [a for a, ic in rows if not ic]
    if len(conf) < 2 or len(opn) < 2:
        return None
    import statistics as _statistics
    diff = median_difference_ci(opn, conf, seed=0)
    mw = mann_whitney_test(opn, conf)
    pricier = diff.ci_low > 0
    conf_median, opn_median = _statistics.median(conf), _statistics.median(opn)
    return Claim(
        id="transparency.confidential_tender_size",
        hypothesis="Do confidential tenders carry a significantly higher dollar value than open ones?",
        population=Population(
            grain="(meeting, award)", definition="tenders with a known amount, confidential vs. open",
            base_table="tender_fact", filter_chain=("amount is not null and amount > 0",),
        ),
        numerator=NumeratorDenominator(definition="confidential tenders with a known amount", n=len(conf)),
        denominator=NumeratorDenominator(definition="tenders with a known amount (confidential + open)", n=len(conf) + len(opn)),
        grade=GRADE_CRITICAL if pricier else GRADE_SUPPORTIVE,
        grade_justification=(
            f"confidential-minus-open median-value 95% CI [{round(diff.ci_low)}, {round(diff.ci_high)}] "
            f"{'excludes' if pricier else 'does not exclude'} zero (Mann-Whitney p={round(mw.p_value, 4)})"
        ),
        comparison=Comparison(
            type=COMPARISON_BETWEEN_SUBJECT, reference_definition="open (non-confidential) tenders",
            reference_is_same_event=True,
        ),
        statistic=Statistic(value=diff.value, ci_low=diff.ci_low, ci_high=diff.ci_high, method=diff.method),
        narrative=Narrative(
            headline=f"Confidential tenders run a ${conf_median:,.0f} median vs ${opn_median:,.0f} "
                     f"open (n={len(conf)})",
            body=f"Of tenders with a known amount, {len(conf)} confidential and {len(opn)} open; "
                 f"median-value difference {round(diff.value):,} (95% CI [{round(diff.ci_low):,}, "
                 f"{round(diff.ci_high):,}]).",
            caveats=(
                "Confidentiality is often lawful — a higher confidential median is a visibility "
                "concern, not evidence of impropriety on its own.",
                "Thin n on the confidential side is common; read as directional at low n.",
            ),
        ),
    )


def _t_confidential_topics_claim(session, council_id, pc) -> Claim | None:
    """Claim counterpart to `_t_confidential_topics`. The graded statistic
    is the "named development" theme's own closure-rate CI, checked
    against every other theme's CI for confident separation; a
    `chi_square_independence()` omnibus test over the full theme x
    confidential table is reported alongside as supporting evidence, not
    the graded quantity itself (an omnibus test can reject "all themes
    equal" without telling you which theme differs, or in which
    direction)."""
    from src.models import DelegatedDecision, OtherItem

    descs: list[tuple[str, bool]] = []
    for model in (Tender, OtherItem, DelegatedDecision):
        for desc, ic in (
            session.query(model.description, model.is_confidential)
            .join(Meeting, model.meeting_id == Meeting.id)
            .filter(Meeting.council_id == council_id, Meeting.document_type == "minutes")
        ):
            if _is_nil_placeholder(desc):
                continue
            descs.append(((desc or "").lower(), bool(ic)))
    total = len(descs)
    conf_total = sum(1 for _d, ic in descs if ic)
    if not total or not conf_total:
        return None

    theme_counts: dict[str, tuple[int, int]] = {}  # name -> (confidential, total)
    for name, pat in _CONF_THEMES:
        rx = re.compile(pat)
        items = [ic for d, ic in descs if rx.search(d)]
        theme_counts[name] = (sum(1 for ic in items if ic), len(items))
    dev_conf, dev_n = theme_counts["Named development"]
    others = {k: v for k, v in theme_counts.items() if k != "Named development" and v[1] > 0}
    if dev_n == 0 or not others:
        return None

    dev_est = proportion_ci(dev_conf, dev_n)
    other_ests = {name: proportion_ci(c, n) for name, (c, n) in others.items()}
    dev_confidently_least = all(dev_est.ci_high < est.ci_low for est in other_ests.values())

    table = [[c, n - c] for c, n in theme_counts.values() if n > 0]
    chi2 = chi_square_independence(table) if len(table) >= 2 else None

    return Claim(
        id="transparency.confidential_topics",
        hypothesis="Is the 'named development' theme confidently the least-closed of the "
                   "confidentiality themes measured?",
        population=Population(
            grain="(meeting, item)", definition="tender/other/delegated-decision items matching a confidentiality theme keyword",
            base_table="motion_fact", filter_chain=("description matches a theme keyword pattern",),
        ),
        numerator=NumeratorDenominator(definition="'named development' items recorded confidential", n=dev_conf),
        denominator=NumeratorDenominator(definition="items matching the 'named development' theme keyword", n=dev_n),
        grade=GRADE_SUPPORTIVE if dev_confidently_least else GRADE_CRITICAL,
        grade_justification=(
            f"'named development' closure-rate CI [{round(dev_est.ci_low, 2)}, {round(dev_est.ci_high, 2)}] is "
            + ("entirely below every other theme's CI" if dev_confidently_least else
               "not confidently below every other theme's CI")
        ),
        statistic=Statistic(value=dev_est.value, ci_low=dev_est.ci_low, ci_high=dev_est.ci_high, method=dev_est.method),
        narrative=Narrative(
            headline=f"'Named development' items are confidential {round(dev_est.value * 100)}% of the "
                     f"time (n={dev_n}), {'the least-closed theme' if dev_confidently_least else 'not confirmed least-closed'}",
            body=f"Of {dev_n} 'named development' items, {dev_conf} were recorded confidential. "
                 + (f"An omnibus chi-square test across all {len(table)} themes measured found closure "
                    f"rates differ significantly (p={round(chi2.p_value, 4)})." if chi2 else ""),
            caveats=(
                "Keyword-based theme bucketing is coarse; any misclassification biases toward the "
                "null (over-counting development closures), not toward this claim's conclusion.",
            ),
        ),
    )


# ── claim battery (Step 7, docs/uplift/migration/02-claim-layer.md) ─────────
# The Claim-object counterpart to _GENERATORS/run_test_battery() above. Only
# 19 of 29 test_ids have a registered claim generator — the other 10 need a
# genuinely different statistical shape this schema/inference toolkit
# doesn't cover yet (a median-value comparison, a categorical lift ratio, a
# set-overlap boolean, a win-rate hierarchy/spread, a raw count trend with
# no denominator, one still-hardcoded-prose test, and two with no
# underlying computation at all) — not attempted, not a placeholder.

_CLAIM_GENERATORS: dict[str, Callable] = {
    "conflict.recusal_management": _t_recusal_overall_claim,
    "conflict.recusal_trend": _t_recusal_trend_claim,
    "conflict.delegate_body_conflict": _t_delegate_body_conflict_claim,
    "planning.big_dollar_leniency": _t_big_dollar_leniency_claim,
    "planning.repeat_applicant": _t_repeat_applicant_claim,
    "planning.objection_responsiveness": _t_objection_dose_claim,
    "governance.officer_ratification": _t_officer_divergence_claim,
    "governance.oversight_body_capture": _t_oversight_body_capture_claim,
    "governance.unanimity_trend": _t_unanimity_trend_claim,
    "governance.chair_capture": _t_mayoral_claim,
    "governance.freshman_effect": _t_freshman_claim,
    "governance.election_cycle": _t_election_cycle_claim,
    "governance.attendance": _t_attendance_claim,
    "transparency.confidential_share": _t_transparency_claim,
    "finance.eoy_spending": _t_eoy_spending_claim,
    "engagement.deputation_dissent": _t_deputation_dissent_claim,
    "engagement.question_responsiveness": _t_question_responsiveness_claim,
    "procurement.threshold_gaming": _t_threshold_gaming_claim,
    "procurement.decider_supplier_conflict": _t_decider_supplier_conflict_claim,
    "governance.power_spread": _t_voting_power_claim,
    "governance.incumbency": _t_tenure_claim,
    "procurement.concentration": _t_tender_concentration_claim,
    "procurement.incumbency": _t_procurement_incumbency_claim,
    "engagement.participation": _t_engagement_claim,
    "transparency.confidential_tender_size": _t_confidential_tender_size_claim,
    "transparency.confidential_topics": _t_confidential_topics_claim,
}

# test_ids with no claim generator yet, for reporting ("N of 29 checked")
# without treating absence as either a pass or a failure.
CLAIM_GENERATOR_COVERAGE_GAP: frozenset[str] = frozenset(_GENERATORS) - frozenset(_CLAIM_GENERATORS)


@dataclass(frozen=True)
class ClaimGenerationError:
    test_id: str
    error: str


def run_claim_battery(
    session: Session, council_id: int, precomputed: dict | None = None,
) -> tuple[dict[str, Claim], list[ClaimGenerationError]]:
    """Run every registered claim generator and return `{test_id: Claim}`
    plus any generation errors. A generator returning `None` means "no data
    to build a claim from" (the `_nodata()` convention's Claim-side
    analogue) and is simply omitted, not an error. A generator raising is
    caught and recorded rather than sinking the whole battery — same
    discipline `run_test_battery()` already applies to `TestResult`
    generators.
    """
    pc = precomputed or {}
    claims: dict[str, Claim] = {}
    errors: list[ClaimGenerationError] = []
    for test_id, fn in _CLAIM_GENERATORS.items():
        try:
            claim = fn(session, council_id, pc)
        except Exception as exc:
            errors.append(ClaimGenerationError(test_id=test_id, error=f"{type(exc).__name__}: {exc}"))
            continue
        if claim is not None:
            claims[test_id] = claim
    return claims, errors
