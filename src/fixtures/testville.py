"""
The Testville fixture-corpus builder (docs/SECOND_COUNCIL_PLAN.md Phase 0.1).

One shared builder, two consumers: `tests/test_council_agnostic.py` seeds it
into a tmp in-memory DB per test run; `council seed-fixture testville`
(`src/cli.py`) seeds it into the local `data/council.db` so it can be
drafted and browsed like any other council in Draft mode. They must never
drift into two hand-kept copies of "the synthetic council" — this is the
one definition both read.

Two profiles:

- `"baseline"` — a Cambridge-*shaped* council (never seeded via the CLI;
  pytest-only). Its knobs are set to reproduce the same real, already-
  measured Cambridge findings the battery's static verdict prose asserts
  (confidential tenders pricier, recusal compliance declining, near-total
  officer ratification, no threshold-gaming spike, mayor draws less dissent
  than backbenchers, ...) so it is the thing every hardcoded verdict in
  `src/analysis/tests.py` happens to already agree with.
- `"testville"` — every one of those signals inverted (docs/
  SECOND_COUNCIL_PLAN.md 0.1). A battery test whose `valence`/`grade` is
  hardcoded to baseline's conclusion instead of derived from the data will
  say the same thing about Testville's opposite numbers — that mismatch,
  not this module, is what `tests/test_council_agnostic.py` detects.

Both profiles are fully synthetic: no real councillor, address, or firm
name from Cambridge's actual corpus appears anywhere here, and neither
corpus spans 1995-2026 (Cambridge's real span). `Council.slug`-equivalent
uniqueness (`Councillor.slug`) is guaranteed by prefixing every synthetic
councillor's slug with the profile key, since a local dev DB seeded with
Testville also holds the real Cambridge corpus in the same tables.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from src.models import (
    Appointment,
    ApplicationStatus,
    BudgetItem,
    BuildingPermit,
    CommitteeReport,
    CommunitySubmission,
    Council,
    Councillor,
    CouncillorTerm,
    DelegatedDecision,
    Deputation,
    ExtractionEvidence,
    InterestDeclaration,
    InterestDeclarationType,
    Meeting,
    Motion,
    MotionOutcome,
    OtherItem,
    Petition,
    PermitStatus,
    PlanningApplication,
    PublicQuestion,
    Site,
    Tender,
    Vote,
    VoteChoice,
)


@dataclass
class CorpusProfile:
    """Knobs the builder reads. Every knob below is named in docs/
    SECOND_COUNCIL_PLAN.md 0.1's inversion list, or is a cheap, natural
    extension of it — giving Phase 1.1 real, differently-shaped numbers to
    branch on once a test's hardcode is fixed, not just two runs of the
    same shape."""

    key: str
    council_name: str
    short_name: str
    start_year: int
    end_year: int
    seed: int
    synthetic: bool = True
    # tenders
    confidential_premium: float = 1.8   # confidential tender $ vs open tender $ (>1 pricier)
    tender_gaming: bool = False          # bunch tenders just under the $250k tender threshold
    incumbency_overlap: bool = False     # a frequent repeat winner is also a top-10 $ recipient
    eoy_spike: bool = False              # December tender $ spikes vs an even spread
    # conflict / recusal
    recusal_pre: float = 0.75            # P(stepped out | declared, must-leave) by era
    recusal_inquiry: float = 0.55
    recusal_post: float = 0.35
    # governance
    officer_divergence_rate: float = 0.05   # share of paired agenda items council departs on
    mayor_dissent_ratio: float = 0.55        # mayor-moved dissent odds vs backbench
    oversight_capture: bool = False          # audit-committee appointees skew to the chamber's winners
    # planning
    big_dollar_gap: float = 3.0          # pp spread in approval rate, low- vs high-value quartile
    repeat_applicant_gap: float = 2.0    # pp spread in approval rate, 1x vs 7+x applicants
    objection_responsive: bool = True    # refusal rate rises with objector count
    # engagement
    deferral_pre: float = 0.15           # P(public question taken "on notice") by era
    deferral_inquiry: float = 0.45
    deferral_post: float = 0.55


PROFILES: dict[str, CorpusProfile] = {
    "baseline": CorpusProfile(
        key="baseline",
        council_name="Baseline Shire Council",
        short_name="BaselineShire",
        start_year=2013,
        end_year=2023,
        seed=1001,
        confidential_premium=1.8,
        tender_gaming=False,
        incumbency_overlap=False,
        eoy_spike=False,
        recusal_pre=0.75, recusal_inquiry=0.55, recusal_post=0.35,
        officer_divergence_rate=0.04,
        mayor_dissent_ratio=0.5,
        oversight_capture=False,
        big_dollar_gap=3.0,
        repeat_applicant_gap=2.0,
        objection_responsive=True,
        deferral_pre=0.15, deferral_inquiry=0.45, deferral_post=0.55,
    ),
    "testville": CorpusProfile(
        key="testville",
        council_name="City of Testville",
        short_name="Testville",
        start_year=2009,
        end_year=2023,
        seed=2002,
        confidential_premium=0.5,
        tender_gaming=True,
        incumbency_overlap=True,
        eoy_spike=True,
        recusal_pre=0.35, recusal_inquiry=0.55, recusal_post=0.75,
        officer_divergence_rate=0.55,
        mayor_dissent_ratio=1.8,
        oversight_capture=True,
        big_dollar_gap=28.0,
        repeat_applicant_gap=26.0,
        objection_responsive=False,
        deferral_pre=0.55, deferral_inquiry=0.45, deferral_post=0.15,
    ),
}

# ── fictional name/content pools — disjoint per profile so a shared dev DB
# never collides a slug, address, or firm name across the two. ────────────

_BASELINE_COUNCILLORS = [
    ("Alan", "Prescott"), ("Marion", "Delacroix"), ("Theo", "Nakamura"),
    ("Priya", "Anand"), ("Declan", "Osei"), ("Ingrid", "Solberg"),
    ("Marcus", "Feldman"), ("Yolanda", "Reyes"), ("Barnaby", "Whitlock"),
    ("Camille", "Duquesne"), ("Roland", "Achebe"), ("Sofia", "Marchetti"),
    ("Vincent", "Halloran"), ("Naomi", "Petrova"),
]
_TESTVILLE_COUNCILLORS = [
    ("Fenella", "Oduya"), ("Grant", "Vasilenko"), ("Bianca", "Okafor"),
    ("Silas", "Tremblay"), ("Odette", "Kowalczyk"), ("Rufus", "Adeyemi"),
    ("Wren", "Castellano"), ("Idris", "Nováková"), ("Peregrine", "Lindqvist"),
    ("Astrid", "Farouk"), ("Cormac", "Ibewuike"), ("Larkin", "Szabo"),
    ("Modesty", "Okonkwo"), ("Tabitha", "Renshaw"),
]

_BASELINE_STREETS = [
    "Prescott Lane", "Delacroix Avenue", "Millbrook Road", "Fairhaven Street",
    "Oakendale Crescent", "Sundew Terrace", "Windermere Way", "Cobalt Close",
]
_TESTVILLE_STREETS = [
    "Testville Parade", "Meridian Drive", "Halberd Street", "Founders Way",
    "Ironbark Crescent", "Lantern Hill Road", "Quarry Street", "Vellum Terrace",
]

_BASELINE_CONTRACTORS = [
    "Millbrook Civil Pty Ltd", "Fairhaven Landscaping", "Cobalt Electrical Services",
    "Windermere Earthworks", "Sundew Traffic Management", "Oakendale Plumbing Co",
    "Prescott Road Surfacing", "Delacroix Fencing Pty Ltd",
]
_TESTVILLE_CONTRACTORS = [
    "Meridian Civil Group", "Ironbark Earthworks", "Lantern Hill Traffic Control",
    "Quarry Street Electrical", "Vellum Landscaping Pty Ltd", "Founders Plumbing Co",
    "Halberd Road Surfacing", "Testville Fencing Services",
]

_BASELINE_APPLICANTS = [
    "H. Prescott Developments", "Fairhaven Building Co", "Millbrook Homes",
    "Oakendale Constructions", "Sundew Property Group",
]
_TESTVILLE_APPLICANTS = [
    "Meridian Developments", "Ironbark Homes", "Founders Building Co",
    "Quarry Street Constructions", "Lantern Hill Property Group",
]

_TAGS = ["planning", "finance", "governance", "community", "infrastructure"]
_CONF_THEMES = [
    ("commercial-in-confidence contract negotiation", True),
    ("tender and procurement panel arrangements", True),
    ("staff remuneration and personnel matter", True),
    ("legal advice and pending litigation", True),
    ("land acquisition and property valuation", True),
    ("named development structure plan", False),
]


def _slugify(profile_key: str, given: str, family: str) -> str:
    return f"{profile_key}-{given}-{family}".lower().replace(" ", "-").replace("'", "")


def _recusal_prob(profile: CorpusProfile, year: int) -> float:
    if year < 2018:
        return profile.recusal_pre
    if year <= 2021:
        return profile.recusal_inquiry
    return profile.recusal_post


def _deferral_prob(profile: CorpusProfile, year: int) -> float:
    if year < 2018:
        return profile.deferral_pre
    if year <= 2021:
        return profile.deferral_inquiry
    return profile.deferral_post


def _months_between(start: date, end: date):
    d = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    while d <= last:
        yield d
        if d.month == 12:
            d = date(d.year + 1, 1, 1)
        else:
            d = date(d.year, d.month + 1, 1)


@dataclass
class _CouncillorRig:
    obj: Councillor
    term_start: date
    term_end: date
    dissent_prob: float          # base P(vote AGAINST) on a contested motion
    is_mayor_window: tuple[date, date] | None = None
    is_audit_appointee: bool = False


def _make_councillors(session: Session, council_id: int, profile: CorpusProfile,
                      rng: random.Random) -> list[_CouncillorRig]:
    names = _TESTVILLE_COUNCILLORS if profile.key == "testville" else _BASELINE_COUNCILLORS
    span_start = date(profile.start_year, 1, 1)
    span_end = date(profile.end_year, 12, 31)
    span_days = (span_end - span_start).days

    rigs: list[_CouncillorRig] = []
    for i, (given, family) in enumerate(names):
        # staggered, overlapping terms: most serve a long stretch, a couple
        # are one-termers (governance.incumbency's "one-term vs career" mix;
        # governance.freshman_effect needs a real "recently joined" cohort).
        if i < 4:
            t_start = span_start
            t_end = span_end
        else:
            max_len = rng.randint(int(span_days * 0.25), span_days)
            latest_start = span_days - max_len
            offset = rng.randint(0, max(latest_start, 0))
            t_start = span_start + timedelta(days=offset)
            t_end = min(span_end, t_start + timedelta(days=max_len))
        c = Councillor(
            given_name=given, family_name=family,
            slug=_slugify(profile.key, given, family),
        )
        session.add(c)
        session.flush()
        # dissent tier: mostly moderate, a couple of loyalists, a couple of
        # frequent dissenters — gives governance.power_spread a real range.
        tier = rng.random()
        dissent_prob = 0.06 if tier < 0.2 else (0.4 if tier > 0.85 else 0.18)
        rigs.append(_CouncillorRig(obj=c, term_start=t_start, term_end=t_end,
                                   dissent_prob=dissent_prob))

    # Mayor: the longest-serving rig, for its own sub-window (~half its term).
    mayor_rig = max(rigs, key=lambda r: (r.term_end - r.term_start))
    total_days = (mayor_rig.term_end - mayor_rig.term_start).days
    # Offset from term_start (not flush with it) — CouncillorTerm's
    # uq_term constraint is (councillor_id, council_id, term_start), and
    # this same councillor also gets an ordinary "Councillor" term below
    # starting exactly at term_start; a mayoral window starting on the
    # same date would collide with it.
    m_start = mayor_rig.term_start + timedelta(days=total_days // 4)
    m_end = m_start + timedelta(days=total_days // 2)
    mayor_rig.is_mayor_window = (m_start, m_end)
    session.add(CouncillorTerm(
        councillor_id=mayor_rig.obj.id, council_id=council_id,
        ward=None, role="Mayor", term_start=m_start, term_end=m_end,
        source="fixture",
    ))

    # Ordinary CouncillorTerm rows for every rig (role="Councillor").
    for r in rigs:
        session.add(CouncillorTerm(
            councillor_id=r.obj.id, council_id=council_id,
            ward=None, role="Councillor", term_start=r.term_start, term_end=r.term_end,
            source="fixture",
        ))

    # Audit committee appointees — generic body-name keyword
    # (oversight_body_capture()'s match is council-agnostic; see that
    # function's own docstring). `oversight_capture=True` (Testville) skews
    # the pick to the chamber's habitual winners (lowest dissent_prob);
    # baseline draws across the whole spread, so appointee/non-appointee
    # win rates land close together. The actual `Appointment` rows need a
    # real `meeting_id` (NOT NULL) — deferred to `build_corpus` once the
    # first meeting exists; only the flag is set here.
    ordered = sorted(rigs, key=lambda r: r.dissent_prob)
    appointees = ordered[:3] if profile.oversight_capture else rng.sample(rigs, 3)
    for r in appointees:
        r.is_audit_appointee = True
    session.flush()
    return rigs


def _make_sites(session: Session, council_id: int, profile: CorpusProfile,
                rng: random.Random) -> list[Site]:
    streets = _TESTVILLE_STREETS if profile.key == "testville" else _BASELINE_STREETS
    sites = []
    for i in range(40):
        street = streets[i % len(streets)]
        s = Site(
            council_id=council_id,
            address=f"{10 + i} {street}",
            suburb=profile.short_name,
            zoning=rng.choice(["Residential", "Commercial", "Mixed Use"]),
        )
        session.add(s)
        sites.append(s)
    session.flush()
    return sites


def _tender_amount(rng: random.Random, profile: CorpusProfile, year: int, month: int) -> tuple[float, bool, str]:
    """(amount, is_confidential, size_tier).

    Baseline's organic draw is deliberately small-only ("size_tier" always
    "small") — its big-dollar contracts are injected separately as a
    dedicated, deterministic batch (`_inject_baseline_big_dollar_firms`)
    rather than drawn probabilistically here. A probabilistic "rare, large
    award" tier sounds right but isn't robust: `tender_concentration()`'s
    top10 ranking always returns exactly 10 firms once >=10 distinct firms
    exist, so if too few large awards land (thin-tail variance) some of
    those 10 slots get backfilled by ordinary small-job firms — which,
    being active across the whole corpus span, reliably also have
    years>=4, silently reintroducing the "overlap" `procurement.incumbency`
    is supposed to be clean of. A deterministic batch has no such variance.
    """
    is_confidential = rng.random() < 0.15
    size_tier = "small"
    if year < 2015 or not profile.tender_gaming:
        base = rng.uniform(5_000, 30_000) if year >= 2015 else rng.uniform(5_000, 200_000)
    else:
        roll = rng.random()
        if roll < 0.45:
            base = rng.uniform(5_000, 150_000)
        elif roll < 0.80:
            base = rng.uniform(200_000, 249_000)      # just-below-threshold pileup
        elif roll < 0.90:
            base = rng.uniform(250_000, 300_000)       # kept thin, on purpose
            size_tier = "large"
        else:
            base = rng.uniform(400_000, 2_000_000)
            size_tier = "large"
    if is_confidential:
        base *= profile.confidential_premium
    if profile.eoy_spike and month == 12:
        base *= 3.0
    return round(base, 2), is_confidential, size_tier


def build_corpus(session: Session, council_id: int, profile: CorpusProfile) -> None:
    """Populate every table the standard battery reads for `council_id`,
    shaped by `profile`. Idempotency/overwrite-safety is the caller's job
    (see `seed_profile` below) — this function always appends fresh rows.
    """
    rng = random.Random(profile.seed)
    rigs = _make_councillors(session, council_id, profile, rng)
    sites = _make_sites(session, council_id, profile, rng)
    contractors = _TESTVILLE_CONTRACTORS if profile.key == "testville" else _BASELINE_CONTRACTORS
    applicants = _TESTVILLE_APPLICANTS if profile.key == "testville" else _BASELINE_APPLICANTS
    incumbent_firm = contractors[0]  # the one firm a rigged incumbency test can catch
    # Disjoint, and deliberately >10-strong, small-job/big-job firm pools
    # (excluding the incumbent): tender_concentration()'s top10_amount only
    # excludes anyone once there are more than 10 distinct firms to rank —
    # with 8 total (the flavour-named list alone) every firm is trivially
    # "in the top 10" by construction, which would make every corpus look
    # like it has incumbency overlap regardless of this knob. A firm that
    # only ever wins small, frequent jobs should never accumulate top-10
    # dollars; a firm that only wins rare large jobs should never
    # accumulate enough distinct years — so, in the baseline profile, no
    # firm is accidentally both. Testville's incumbent (below) crosses both.
    #
    # "Years" means distinct calendar years, not award count — so each
    # big-job firm is also boxed into its own short (<=2-year) window
    # across the corpus span; without that, a firm winning several awards
    # spread evenly across an 11-year span accumulates years>=4 just from
    # its own natural spread, which would trigger `overlap` on its own.
    # There must also be at least 10 of them: with 16 total firms and only
    # 4 "big" ones, the other 6 of tender_concentration()'s top10 slots
    # would be filled by small-job firms regardless of how low their
    # dollar totals are (top10 always returns exactly 10 once >=10 firms
    # exist) — and a small firm active across the whole span reliably
    # has years>=4 too, so *that* alone would trigger `overlap`.
    small_job_firms = [f"{contractors[1]} — Crew {i}" for i in range(1, 13)]
    big_job_firm_names = [f"{contractors[-1]} — Division {i}" for i in range(1, 11)]
    span_years_list = list(range(profile.start_year, profile.end_year + 1))
    # every year maps to exactly one big-job firm (a contiguous window each,
    # covering the whole span — no gap for an "eligible" fallback to widen
    # any single firm's window back out) — the ONLY way to guarantee each
    # stays under the years>=4 overlap threshold regardless of span length.
    window_size = max(1, -(-len(span_years_list) // len(big_job_firm_names)))  # ceil div
    firm_by_year: dict[int, str] = {}
    for i, yr in enumerate(span_years_list):
        idx = min(i // window_size, len(big_job_firm_names) - 1)
        firm_by_year[yr] = big_job_firm_names[idx]

    # applicant frequency skew: applicants[0]/[1] are genuine repeat filers
    # (many applications each, landing solidly in the "4-6"/"7+" buckets);
    # everyone else gets a unique one-shot name, so the "1" and "2-3"
    # buckets aren't starved by a long tail piling onto a handful of
    # shared fallback names.
    _one_shot_counter = [0]

    def _pick_applicant() -> str:
        if rng.random() < 0.35:
            return rng.choice(applicants[:2])
        _one_shot_counter[0] += 1
        return f"{applicants[-1].split()[0]} Individual Applicant {_one_shot_counter[0]}"

    span_start = date(profile.start_year, 1, 1)
    span_end = date(profile.end_year, 12, 31)

    all_minutes: list[Meeting] = []
    meeting_idx = 0
    for month_start in _months_between(span_start, span_end):
        meeting_idx += 1
        meeting_date = month_start + timedelta(days=rng.randint(0, 20))
        meeting_type = "Special Council Meeting" if rng.random() < 0.05 else "Ordinary Council Meeting"
        year = meeting_date.year

        minutes = Meeting(
            council_id=council_id, meeting_type=meeting_type, meeting_date=meeting_date,
            document_type="minutes",
        )
        session.add(minutes)
        session.flush()
        all_minutes.append(minutes)

        if meeting_idx == 1:
            # Appointment.meeting_id is NOT NULL — anchor every audit-
            # committee appointment to this first real meeting, now that
            # one exists (the appointee flag was decided in
            # _make_councillors, before any Meeting row did).
            for r in rigs:
                if r.is_audit_appointee:
                    session.add(Appointment(
                        meeting_id=minutes.id, councillor_id=r.obj.id,
                        role="Member", body_name="Audit and Risk Committee",
                    ))
            session.flush()

        has_agenda = rng.random() < 0.55
        agenda = None
        if has_agenda:
            agenda = Meeting(
                council_id=council_id, meeting_type=meeting_type, meeting_date=meeting_date,
                document_type="agenda",
            )
            session.add(agenda)
            session.flush()

        active = [r for r in rigs if r.term_start <= meeting_date <= r.term_end]
        if len(active) < 4:
            active = rigs[:4]

        quotes: list[str] = []

        def _evidence(entity_table: str, entity_id: int, text: str) -> None:
            session.add(ExtractionEvidence(
                meeting_id=minutes.id, entity_table=entity_table, entity_id=entity_id,
                quote_text=text,
            ))
            quotes.append(text)

        # ---- motions ---------------------------------------------------
        item_no = 0
        motions: list[dict] = []  # {"obj": Motion, "kind": str, "diverge_target": bool}

        n_ordinary = rng.randint(4, 7)
        for _ in range(n_ordinary):
            item_no += 1
            mover, seconder = rng.sample(active, 2) if len(active) >= 2 else (active[0], active[0])
            title = f"{rng.choice(['Adoption of', 'Approval of', 'Consideration of'])} " \
                    f"{rng.choice(_TAGS)} matter {meeting_idx}.{item_no}"
            m = Motion(
                meeting_id=minutes.id, item_number=str(item_no), title=title,
                moved_by_id=mover.obj.id, seconded_by_id=seconder.obj.id,
                tags=rng.choice(_TAGS),
            )
            session.add(m)
            session.flush()
            motions.append({"obj": m, "kind": "ordinary", "mover": mover})
            _evidence("motions", m.id, f"Moved {mover.obj.given_name} {mover.obj.family_name}, "
                                        f"seconded {seconder.obj.given_name} {seconder.obj.family_name}, "
                                        f"that {title.lower()} be adopted.")

        # ---- a tender-award motion + its Tender row ---------------------
        tender_motion = None
        if rng.random() < 0.7:
            item_no += 1
            mover, seconder = rng.sample(active, 2) if len(active) >= 2 else (active[0], active[0])
            amount, is_conf, size_tier = _tender_amount(rng, profile, year, meeting_date.month)
            if profile.incumbency_overlap and rng.random() < 0.4:
                # Testville: the incumbent wins across every size tier, so
                # it is both a frequent repeat-winner AND a top-dollar
                # recipient — the overlap procurement.incumbency looks for.
                firm = incumbent_firm
            elif size_tier == "large":
                firm = firm_by_year[year]
            else:
                firm = rng.choice(small_job_firms)
            desc = f"Award of contract for {rng.choice(['road resurfacing', 'park upgrade', 'waste collection', 'IT services', 'building maintenance'])}"
            title = f"Award of Tender RFT{year}-{item_no} - {desc}"
            m = Motion(
                meeting_id=minutes.id, item_number=str(item_no), title=title,
                moved_by_id=mover.obj.id, seconded_by_id=seconder.obj.id,
                motion_text=f"That Council accept the tender from {firm if not is_conf else 'the preferred respondent'} "
                            f"for {desc.lower()}.",
                tags="finance",
            )
            session.add(m)
            session.flush()
            motions.append({"obj": m, "kind": "tender", "mover": mover})
            tender_motion = m
            t = Tender(
                meeting_id=minutes.id, reference_number=f"RFT{year}-{item_no}",
                description=desc, awarded_to=("Respondent 1" if is_conf else firm),
                amount=amount, is_confidential=is_conf,
            )
            session.add(t)
            session.flush()
            _evidence("tenders", t.id, f"Council resolved to accept the tender from "
                                       f"{firm if not is_conf else 'the preferred respondent'} "
                                       f"for {desc.lower()} in the amount of ${amount:,.0f}.")

        # ---- a development-application motion + PlanningApplication -----
        if rng.random() < 0.7:
            item_no += 1
            mover, seconder = rng.sample(active, 2) if len(active) >= 2 else (active[0], active[0])
            site = rng.choice(sites)
            value = rng.choice([
                rng.uniform(20_000, 150_000), rng.uniform(150_000, 500_000),
                rng.uniform(500_000, 1_200_000), rng.uniform(1_200_000, 4_000_000),
            ])
            applicant = _pick_applicant()
            n_obj = rng.choices([0, 1, 2, 3, 4, 5, 6, 8], weights=[35, 20, 12, 8, 6, 6, 6, 7], k=1)[0]

            # value quartile pressure (big_dollar_gap) + objector pressure
            # (objection_responsive, or its absence) + applicant-frequency
            # pressure (repeat_applicant_gap), combined additively into one
            # refusal probability.
            value_frac = min(value / 4_000_000, 1.0)
            value_pressure = (value_frac - 0.5) * (profile.big_dollar_gap / 100.0) * 4
            obj_pressure = (min(n_obj, 6) / 6.0) * (0.55 if profile.objection_responsive else -0.05)
            is_repeat = applicant in applicants[:2]
            repeat_pressure = -(profile.repeat_applicant_gap / 100.0) * 3 if is_repeat else 0.0
            refusal_p = max(0.03, min(0.9, 0.22 + value_pressure + obj_pressure + repeat_pressure))
            status = ApplicationStatus.REFUSED if rng.random() < refusal_p else ApplicationStatus.APPROVED

            title = f"Development Application - {site.address}"
            m = Motion(
                meeting_id=minutes.id, item_number=str(item_no), title=title,
                moved_by_id=mover.obj.id, seconded_by_id=seconder.obj.id,
                outcome=MotionOutcome.CARRIED,
                votes_for=len(active), votes_against=0,
                tags="planning",
            )
            session.add(m)
            session.flush()
            pa = PlanningApplication(
                motion_id=m.id, site_id=site.id, reference_number=f"DA{year}-{item_no}",
                applicant_name=applicant, description=f"Proposed development at {site.address}",
                application_date=meeting_date - timedelta(days=60),
                decision_date=meeting_date, status=status, estimated_value=round(value, 2),
            )
            session.add(pa)
            session.flush()
            for k in range(n_obj):
                session.add(CommunitySubmission(
                    application_id=pa.id, submitter_name=f"Resident {k + 1}",
                    submitter_type="individual", position="object",
                    summary="Objects to the proposed development on amenity grounds.",
                    received_date=meeting_date - timedelta(days=30),
                ))
            _evidence("planning_applications", pa.id,
                      f"Council resolved that development application {pa.reference_number} for "
                      f"{site.address} be {'refused' if status == ApplicationStatus.REFUSED else 'approved'}.")
            # every active councillor voted FOR this uncontested procedural motion
            for r in active:
                session.add(Vote(motion_id=m.id, councillor_id=r.obj.id, choice=VoteChoice.FOR))

        # ---- paired agenda motion for officer_divergence (tender_motion only,
        # kept simple: one divergence-eligible item per meeting) ------------
        diverge_target = False
        if agenda is not None and tender_motion is not None:
            diverge_target = rng.random() < profile.officer_divergence_rate
            am = Motion(
                meeting_id=agenda.id, item_number=tender_motion.item_number,
                title=tender_motion.title,
                officer_recommendation=f"That Council {tender_motion.title.lower()}.",
            )
            session.add(am)

        # ---- interest declaration(s) this meeting --------------------------
        declared: dict[int, dict[int, tuple[VoteChoice, bool]]] = {}
        n_decl = rng.choices([0, 1, 2], weights=[55, 35, 10], k=1)[0]
        for _ in range(n_decl):
            r = rng.choice(active)
            target = rng.choice(motions)
            m = target["obj"]
            itype = rng.choice(list(InterestDeclarationType))
            must_leave = itype in (InterestDeclarationType.FINANCIAL, InterestDeclarationType.PROXIMITY)
            stepped_out = must_leave and rng.random() < _recusal_prob(profile, year)
            choice = VoteChoice.ABSENT if stepped_out else rng.choice([VoteChoice.FOR, VoteChoice.AGAINST])
            declared.setdefault(m.id, {})[r.obj.id] = (choice, True)
            idecl = InterestDeclaration(
                meeting_id=minutes.id, councillor_id=r.obj.id, interest_type=itype,
                description=f"{itype.value} interest in relation to item {m.item_number}",
                item_reference=m.item_number,
            )
            session.add(idecl)
            session.flush()
            action = "left the meeting and did not vote" if stepped_out else "declared but remained in the room and voted"
            _evidence("interest_declarations", idecl.id,
                      f"{r.obj.given_name} {r.obj.family_name} declared a {itype.value} interest in "
                      f"item {m.item_number} and {action}.")

        # ---- votes for ordinary + tender motions ---------------------------
        for entry in motions:
            m: Motion = entry["obj"]
            mover_rig = entry["mover"]
            is_diverge_target = entry["kind"] == "tender" and diverge_target
            # forced contested, not just likely: a divergence pair needs a
            # real recorded AGAINST count, not merely a LOST/DEFERRED label
            # sitting on an otherwise-unanimous vote row set.
            contested = is_diverge_target or rng.random() < 0.4
            min_against = (len(active) // 2 + 1) if is_diverge_target else 0
            reserved = declared.get(m.id, {})

            votes_for = votes_against = votes_abstain = 0
            for r in active:
                if r.obj.id in reserved:
                    choice, is_declared = reserved[r.obj.id]
                else:
                    is_declared = False
                    p = r.dissent_prob
                    if mover_rig.is_mayor_window and \
                       mover_rig.is_mayor_window[0] <= meeting_date <= mover_rig.is_mayor_window[1]:
                        p = p * profile.mayor_dissent_ratio
                    p = min(p, 0.9)
                    if is_diverge_target:
                        # deterministic, not probabilistic: a divergence
                        # pair needs a guaranteed real AGAINST majority, not
                        # a chance one.
                        choice = VoteChoice.AGAINST if votes_against < min_against else VoteChoice.FOR
                    elif not contested:
                        choice = VoteChoice.FOR
                    else:
                        choice = VoteChoice.AGAINST if rng.random() < p else VoteChoice.FOR
                session.add(Vote(
                    motion_id=m.id, councillor_id=r.obj.id, choice=choice,
                    declared_interest=is_declared,
                ))
                if choice == VoteChoice.FOR:
                    votes_for += 1
                elif choice == VoteChoice.AGAINST:
                    votes_against += 1
                elif choice == VoteChoice.ABSENT:
                    pass
                else:
                    votes_abstain += 1

            if is_diverge_target:
                outcome = MotionOutcome.LOST if rng.random() < 0.7 else MotionOutcome.DEFERRED
            else:
                outcome = MotionOutcome.CARRIED if votes_for >= votes_against else MotionOutcome.LOST
            m.outcome = outcome
            m.votes_for = votes_for
            m.votes_against = votes_against
            m.votes_abstain = votes_abstain

        # ---- confidential-flagged miscellany: delegated decisions, budget
        # items, other items — feeds transparency.confidential_share /
        # confidential_topics. -----------------------------------------------
        base_conf_p = 0.35 if 2018 <= year <= 2021 else 0.12
        for _ in range(rng.randint(1, 3)):
            theme, _dev = rng.choice(_CONF_THEMES)
            is_conf = rng.random() < base_conf_p
            dd = DelegatedDecision(
                meeting_id=minutes.id, item_number=f"D{item_no + 1}",
                description=f"Delegated decision regarding {theme}",
                officer_title="Chief Executive Officer", is_confidential=is_conf,
            )
            session.add(dd)
        for _ in range(rng.randint(1, 2)):
            theme, _dev = rng.choice(_CONF_THEMES)
            is_conf = rng.random() < base_conf_p
            session.add(BudgetItem(
                meeting_id=minutes.id, item_number=f"B{item_no + 1}",
                description=f"Budget variation regarding {theme}",
                amount=round(rng.uniform(1_000, 500_000), 2), is_confidential=is_conf,
            ))
        for _ in range(rng.randint(1, 2)):
            theme, is_dev_theme = rng.choice(_CONF_THEMES)
            # "named development" theme is deliberately closed far less often
            # than the others, both profiles — matches the shape the battery
            # already asserts, and gives a real (not merely hardcoded) number
            # to compute a lift statistic from.
            p = base_conf_p * (0.3 if is_dev_theme else 1.3)
            is_conf = rng.random() < min(p, 0.9)
            session.add(OtherItem(
                meeting_id=minutes.id, item_number=f"O{item_no + 1}",
                item_type="Report", description=f"Report regarding {theme}",
                is_confidential=is_conf,
            ))
        session.add(BuildingPermit(
            meeting_id=minutes.id, reference_number=f"BP{year}-{meeting_idx}",
            site_address=rng.choice(sites).address,
            description="Residential building permit",
            estimated_value=round(rng.uniform(50_000, 800_000), 2),
            status=rng.choice(list(PermitStatus)),
        ))

        # ---- public engagement: questions, deputations, petitions ---------
        for q in range(rng.choices([0, 1, 2], weights=[40, 40, 20], k=1)[0]):
            on_notice = rng.random() < _deferral_prob(profile, year)
            response = ("The matter will be taken on notice and a written response provided."
                        if on_notice else
                        "The CEO responded to the question in the meeting.")
            pq = PublicQuestion(
                meeting_id=minutes.id, questioner_name=f"Resident {rng.randint(1, 500)}",
                question_summary="Question regarding council operations",
                response_summary=response,
            )
            session.add(pq)
            session.flush()
            _evidence("public_questions", pq.id, f"Question asked; response: {response}")
        if rng.random() < 0.15:
            dep = Deputation(
                meeting_id=minutes.id, presenter_name=f"Community representative {rng.randint(1, 200)}",
                topic=rng.choice(_TAGS), summary="Deputation heard by Council.",
            )
            session.add(dep)
        if rng.random() < 0.05:
            session.add(Petition(
                meeting_id=minutes.id, subject="Community petition",
                presented_by=f"Resident {rng.randint(1, 500)}",
                signatory_count=rng.randint(10, 400),
            ))
        if meeting_idx % 6 == 0:
            session.add(CommitteeReport(
                meeting_id=minutes.id, committee_name="Audit and Risk Committee",
                item_count=rng.randint(2, 6), summary="Committee report received.",
            ))

        if quotes:
            minutes.minutes_text = "\n".join(quotes)

    if not profile.incumbency_overlap:
        _inject_no_overlap_big_dollar_firms(session, all_minutes, rng)
    _inject_big_dollar_quartile_batch(session, all_minutes, sites, profile, rng)

    session.commit()


def _inject_no_overlap_big_dollar_firms(session: Session, all_minutes: list[Meeting],
                                        rng: random.Random) -> None:
    """A dedicated, deterministic batch of >=10 big-dollar firms, each
    confined to a single calendar year (so `years` stays 1, safely under
    `procurement.incumbency`'s years>=4 threshold) — see `_tender_amount`'s
    docstring for why this replaced a probabilistic "rare large award"
    tier. Firms are named ad hoc; nothing else references them.
    """
    by_year: dict[int, list[Meeting]] = {}
    for m in all_minutes:
        by_year.setdefault(m.meeting_date.year, []).append(m)
    years_with_meetings = [y for y, ms in by_year.items() if ms]
    if not years_with_meetings:
        return
    for i in range(12):
        year = rng.choice(years_with_meetings)
        meetings_this_year = by_year[year]
        firm = f"Civic Infrastructure Partners {i + 1}"
        for _ in range(2):
            m = rng.choice(meetings_this_year)
            amount = round(rng.uniform(500_000, 900_000), 2)
            t = Tender(
                meeting_id=m.id, reference_number=f"RFT{year}-BIG{i + 1}",
                description="Award of major infrastructure contract",
                awarded_to=firm, amount=amount, is_confidential=False,
            )
            session.add(t)


def _inject_big_dollar_quartile_batch(session: Session, all_minutes: list[Meeting],
                                      sites: list[Site], profile: CorpusProfile,
                                      rng: random.Random) -> None:
    """A dedicated, deterministic-count batch isolating
    `planning.big_dollar_leniency`'s value-quartile signal from the
    objector-count and applicant-frequency pressures the organic
    per-meeting draw (above) also injects into every application. At this
    fixture's organic scale (~90 applications, ~23/quartile) those other
    two pressures are large enough relative to `big_dollar_gap` that plain
    per-application sampling noise regularly pushed even a near-zero
    `big_dollar_gap` past the 12pp "flat" threshold `_t_big_dollar_leniency`
    checks — not a codebase bug, a fixture-scale one. Refusal *counts* are
    computed once per band, not drawn per application, so the intended
    signal survives regardless of corpus size. Every row here gets a
    unique one-shot applicant name and zero objectors, so it adds no
    cross-contamination into `planning.repeat_applicant` or
    `planning.objection_responsiveness`'s own signals.
    """
    if not all_minutes:
        return
    bands = [(20_000, 150_000), (150_000, 500_000), (500_000, 1_200_000), (1_200_000, 4_000_000)]
    n_per_band = 40
    base_rate = 0.22
    for qi, (lo, hi) in enumerate(bands):
        value_frac = min(((lo + hi) / 2) / 4_000_000, 1.0)
        value_pressure = (value_frac - 0.5) * (profile.big_dollar_gap / 100.0) * 4
        refusal_p = max(0.03, min(0.9, base_rate + value_pressure))
        n_refused = round(refusal_p * n_per_band)
        statuses = (
            [ApplicationStatus.REFUSED] * n_refused
            + [ApplicationStatus.APPROVED] * (n_per_band - n_refused)
        )
        rng.shuffle(statuses)
        for i, status in enumerate(statuses):
            meeting = rng.choice(all_minutes)
            site = rng.choice(sites)
            value = rng.uniform(lo, hi)
            mo = Motion(
                meeting_id=meeting.id, item_number=f"DQ{qi}.{i}",
                title=f"Development Application - {site.address}",
                outcome=MotionOutcome.CARRIED, votes_for=1, votes_against=0,
                tags="planning",
            )
            session.add(mo)
            session.flush()
            # No applicant_name: planning.repeat_applicant's own query
            # filters `applicant_name.isnot(None)`, so a nameless row is
            # structurally invisible to it — this batch's value-driven
            # approval pattern can't dilute that test's own
            # applicant-frequency signal. planning.big_dollar_leniency
            # doesn't read applicant_name at all.
            session.add(PlanningApplication(
                motion_id=mo.id, site_id=site.id, reference_number=f"DQ{qi}-{i}",
                applicant_name=None,
                description=f"Proposed development at {site.address}",
                application_date=meeting.meeting_date - timedelta(days=60),
                decision_date=meeting.meeting_date, status=status,
                estimated_value=round(value, 2),
            ))


def seed_profile(session: Session, profile_key: str) -> tuple[int, bool]:
    """Get-or-create the council for `profile_key` and build its corpus if
    it doesn't have one yet. Returns (council_id, created). Idempotent: a
    second call against an already-seeded council is a no-op (detected by
    the presence of any Meeting row), never a duplicate build.
    """
    profile = PROFILES[profile_key]
    council = session.query(Council).filter_by(short_name=profile.short_name).first()
    if council is None:
        council = Council(
            name=profile.council_name, short_name=profile.short_name, state="WA",
        )
        session.add(council)
        session.commit()
    already_seeded = session.query(Meeting).filter_by(council_id=council.id).first() is not None
    if already_seeded:
        return council.id, False
    build_corpus(session, council.id, profile)
    return council.id, True
