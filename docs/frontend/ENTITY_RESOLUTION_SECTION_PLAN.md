# /method — an entity-resolution section, from two live cases

Status: **built** (Steps 1–4, 2026-09-11). Written 2026-09-10.
B.5 was settled **yes** — `method.json` is public-tier.
Extends `METHOD_PAGE_PLAN.md` (built 2026-09-07, Steps 1–7) with a fifth
section. Same rules apply: every figure traces to a file under `data/` or the
live database, and carries its own date.
Audience: the person handing Part D's steps, one at a time, to a fresh model
instance. Parts A–C are the context every step assumes.

---

## Part A — What the data actually holds

### A.1 Case 1 is real, and there are 15 of them, not one

Against the live database (`data/council.db`, 2026-09-10): **436 named award
rows**, **314 distinct normalised firms**, of which **15 have more than one raw
spelling**. `_normalise_contractor()` (`src/analysis/queries.py`) lowercases,
strips six company suffixes, drops `.` and `,`, then removes all internal
whitespace.

| merged key | raw strings in the database |
|---|---|
| `hotmix` | "Hotmix" ×3 · "HOT MIX" ×1 · "Hot Mix" ×1 · "Hot Mix Pty Ltd" ×1 |
| `walimestone` | "WA Limestone" ×3 · "W.A. Limestone" ×1 |
| `rjvincent` | "RJ Vincent" ×2 · "R J Vincent" ×1 |
| `deneefesigns` | "De Neefe Signs Pty Ltd" ×2 · "DeNeefe Signs" ×1 |
| `davidporterconsultingengineer` | "David Porter, Consulting Engineer" ×2 · "David Porter Consulting Engineer" ×1 |
| `cjdequipment` | "CJD Equipment" ×7 · "CJD Equipment Pty Ltd" ×2 |
| `majormotors` | "Major Motors" ×3 · "Major Motors Pty Ltd" ×2 |
| `boyaequipment` | "Boya Equipment" ×5 · "Boya Equipment Pty Ltd" ×1 |
| `ghd` | "GHD" ×2 · "GHD Pty Ltd" ×2 |
| `connellwagner` | "Connell Wagner" ×2 · "Connell Wagner Pty Ltd" ×2 |
| `fleetcare` | "Fleetcare Pty Ltd" ×2 · "Fleetcare" ×1 |
| `proturfservices` | "Pro Turf Services" ×2 · "Pro Turf Services Pty Ltd" ×1 |
| `bsdconsultants` | "BSD Consultants" ×1 · "BSD Consultants Pty Ltd" ×1 |
| `alvito` | "Alvito Pty Ltd" ×1 · "Alvito" ×1 |
| `downerediworks` | "Downer EDI Works" ×2 · "Downer EDI Works Pty Ltd" ×1 |

`hotmix` is the best single illustration — four raw strings differing by case,
internal space and suffix at once. `walimestone` shows punctuation alone;
`rjvincent` is the brief's own example and should stay in for that reason.

### A.2 The trap in Case 1: redaction placeholders rank first by value

Grouping `awarded_to` naively puts **"Respondent 1" ($14,495,500 across 5
awards)** and **"Respondent 7" ($3,330,829)** at the top of the value ranking —
above every real firm. They are de-identification placeholders, not suppliers.

`tender_concentration()` already excludes them through `_is_redacted_recipient()`,
which was widened on 2026-08-31 after "Tenderer N" and "Contractor N" slipped
through a `respondent%` prefix check and were counted as real firms.

A demonstration section that grouped names without that exclusion would print a
placeholder as the council's largest contractor **on the page about method**.
See B.4.

### A.3 Case 2 is exactly as described, and the query already documents it

`decider_supplier_conflict()` on the live corpus returns:

```
tender_motions            432
votes_on_tender_motions   461
declared_votes              8   (1.74%, against a 3.75% chamber base)
named_awards              412
surnames_tested           184
collisions                  2
```

The two collisions:

| firm (raw) | amount | councillor surname matched |
|---|---|---|
| G T Evans Weed Spraying Service | $70,000 | Evans |
| MacDonald Johnston | $217,154 | Johnston |

The function's own docstring already carries the discipline this section is
meant to show: `awarded_to` NULL/blank rows excluded outright rather than read
as concealment; "Respondent N" excluded; named rows deduplicated by (normalised
contractor, normalised reference, amount) — with the note that "G T Evans Weed
Spraying Service" / TEN0008 / $70,000 is extracted as **two** minutes rows 16
days apart (ids 172 and 1850), one real 1995 award, and that without the dedup a
single real-world surname collision would be counted twice.

That dedup detail is worth showing. It is the same discipline as the resolution
itself, one layer down.

### A.4 The coverage limit is already published, in the scorecard

`src/analysis/tests.py` `_t_decider_supplier_conflict`'s verdict ends: "read
within its coverage limit, since only separately-moved tender-award motions are
visible, not consent-agenda'd awards." So the limit the brief asks to surface is
already asserted on the site — this section restates it where the method is
being explained, and the two must not drift.

### A.5 /method's data is not on the live site

`src/cli.py`: `SNAPSHOT_TIER = {"watch": "public"}` and
`CLAIM_DERIVED_SNAPSHOTS = ("scorecard",)`. Everything else defaults to `full`,
so `method.json` ships to `data/published_full/`, not to the public site.
`frontend/public/data/method.json` is the placeholder from
`METHOD_PAGE_PLAN.md` Step 2 — every field reads `"reason": "source_missing"`.

**So /method renders empty in production today**, and a new section added to it
would render empty too. See B.5.

### A.6 This section names two sitting councillors, on a page with no gate

`src/cli.py` writes `method.json` with the comment that it is not claim-derived
and "S7 has nothing to check on it, by design". That was true of a page carrying
only extraction metrics. It stops being true the moment the page carries the
Case 2 table, which pairs a firm with a councillor.

The claim is exculpatory — the whole point is that neither collision is a
conflict — but this project has a documented history of supportive-valence text
carrying an unflattering clause about a named person (the 2026-08-22 Editor pass,
BLOCKING flag 4). See B.1 and B.2.

---

## Part B — Decisions

### B.1 Publish the firm names and the fact of a surname match. Not the councillors.

The demonstration is entirely about the **firms**: two business names contained a
sitting councillor's surname, provenance identified both as unrelated
businesses, the result is a true null. Naming Cr Peter Evans and Cr David
Johnston adds nothing a reader needs and puts two real people beside the words
"undeclared conflict of interest" on the public record.

So the record carries: the raw firm string, the amount, what the firm actually
is (weed-spraying contractor; street-sweeper manufacturer), and the statement
that the name contained a sitting councillor's surname. It does **not** carry
`councillor_name`, `councillor_id`, or the surname as a separate field.

Be honest about what this does not achieve: a reader who knows the roster can
still infer the surname from "G T Evans Weed Spraying Service", because the
surname is in the firm's own name. That is unavoidable — the firm names are the
data. What is avoidable is the site asserting the pairing, and this does not
assert it.

### B.2 The section makes /method claim-bearing. Correct the comment and gate it.

B.1 makes the payload name-free by construction, which is what makes it
publishable — not an assumption that nobody will look. Two consequences:

- The `src/cli.py` comment saying S7 has nothing to check on `method.json` is no
  longer accurate as a general statement and must be corrected to say why *this*
  payload is name-free rather than why the file is exempt.
- The section must be inside Editor's scope for at least one review pass before
  it publishes. `method.json` sits in the draft root, so it already is — confirm
  that rather than assuming it.

Run `usable_roster_names()`-style checking over the built section in Step 1's
tests: if any councillor's full name reaches the payload, that is a build error,
not a review finding.

### B.3 Every string comes from the database at build time.

The brief's constraint. `build_method_record()` already takes a session; the new
`entity_resolution` block queries `tenders` / `meetings` and calls
`_normalise_contractor()` and `decider_supplier_conflict()` directly. No string
in Part A's tables is retyped into `method.py` or into JSX — they are shown here
so a reviewer can check the output, not so they can be pasted.

Same object shape as the rest of `method.json`: `{value, source, generated_at,
n, …}`, with `source: "data/council.db"` and `generated_at` the build time,
since the database is the live source (`METHOD_PAGE_PLAN.md` B.1's rule that
what can be recomputed live, is).

### B.4 Apply the same exclusions the analysis applies.

`_is_redacted_recipient()` on Case 1's grouping (A.2), and Case 2 takes
`decider_supplier_conflict()`'s own output rather than re-deriving collisions —
so the section cannot disagree with the panel it describes. A demonstration of
method that used a different method than the analysis would be worse than no
demonstration.

Show the dedup fact from A.3 as part of Case 2: two extracted rows, 16 days
apart, one real award. It is a second, independent illustration of the same
discipline and it costs one sentence.

### B.5 DECIDE: does `method.json` become public-tier?

Without it this section ships to `data/published_full/` and the live /method
stays empty (A.5). The page exists to be the credibility artifact, so an empty
one is worse than none.

**Recommendation: yes — add `"method": "public"` to `SNAPSHOT_TIER`**, after
B.2's gating is in place. It carries no battery claim and, under B.1, no
person's name; the rest of its content is extraction metrics already summarised
in the README.

This is a publish-boundary change, so it is its own step (Step 3) with its own
review, and it is the one decision to settle before that step. If the answer is
no, Steps 1–2 still stand and the section is visible in Draft mode only — say so
rather than leaving the page empty and undiscussed.

### B.6 The limits are part of the section, not a footnote under it.

The brief requires three, and each attaches to the claim it qualifies rather
than collecting at the bottom:

1. **Surname matching cannot detect a connection through a differently-named
   entity** — a councillor with an interest in a firm trading under any other
   name is invisible to this test. Sits with Case 2's result.
2. **This is a null within a stated coverage boundary, not proof of absence.**
   Sits with the "zero genuine matches" figure, in the same visual block, not
   below the fold.
3. **Only separately-moved tender-award motions are visible, not
   consent-agenda'd awards** (A.4). Sits with the 412/432 denominators, and must
   read consistently with the scorecard verdict that already says it.

Write them once, in `method.py`, beside the numbers they qualify — not in JSX.
Same discipline as the registry's caveats.

---

## Part C — The section's shape

```
entity_resolution: {
  supplier_normalisation: {
    source: "data/council.db", generated_at: <build time>,
    named_award_rows: 436, distinct_firms: 314, multi_variant_firms: 15,
    rule: "lowercase; strip company suffixes; drop . and ,; remove internal whitespace",
    examples: [ { merged_key, raw: [{string, n}], n_awards, total_amount } ],
    excluded_placeholders: { n_awards, note }        // A.2
  },
  surname_collision: {
    source: "data/council.db", generated_at: <build time>,
    named_awards: 412, surnames_tested: 184,
    naive_matches: 2,
    resolved: [ { firm, amount, what_it_is, resolution } ],   // no councillor name (B.1)
    genuine_matches: 0,
    dedup_note: "…two extracted rows 16 days apart, one real award…",
    limits: [ … ]                                    // B.6
  }
}
```

`what_it_is` ("a weed-spraying contractor", "a street-sweeper manufacturer") is
the one piece of authored prose in the block. It is a statement about a business,
sourced from the tender's own description and evidence quote — Step 1 must
confirm it against that quote rather than from the firm's name, and say so.

---

## Part D — The steps

Four steps. 1 is the builder; 2 the page; 3 the publish boundary; 4 docs.

Every step ends with `pytest -q` where it touches Python, and `npm run lint &&
npm run build` where it touches the frontend.

**Standing context.** Read `docs/MAP.md` (per `CLAUDE.md`, every session),
`docs/frontend/METHOD_PAGE_PLAN.md` Parts B–C, and
`docs/frontend/INTERACTIVITY.md`'s hard rule.

**Three constraints govern every step:**
- *Every string comes from the database at build time.* Nothing in Part A is
  retyped into code (B.3).
- *No councillor's name reaches the payload* (B.1) — enforced by a test, not by
  care.
- *A null is not proof of absence*, and the section says so beside the number
  (B.6).

**One commit per step**, committed once its acceptance checks pass; if they
fail, do not commit — report. `docs/TESTING.md` "Commit conventions" applies:
**no `Co-Authored-By: Claude` trailer.**

---

### Step 1 — The `entity_resolution` block in `method.py`

Build Part C's shape inside `build_method_record()`.

- Case 1 groups `tenders.awarded_to` (minutes only) by `_normalise_contractor()`,
  excluding `_is_redacted_recipient()` rows and reporting them separately (B.4).
  Include every multi-variant firm — there are 15, which is a short enough list
  to show in full and more convincing than a chosen three.
- Case 2 calls `decider_supplier_conflict()` and reads `named_awards`,
  `surnames_tested` and `collisions` off it, dropping `councillor_name` /
  `councillor_id` at the boundary (B.1).
- `what_it_is` for each collision: check it against the tender's description and
  its `extraction_evidence` quote before writing it, and report what you found.
  If a quote does not support the characterisation, say so rather than keeping
  the sentence.
- The three limits from B.6, beside the figures they qualify.

Tests: the payload contains no councillor full name (build the roster from
`Councillor` and assert none appears anywhere in the serialised block); the
placeholder exclusion is applied; the numbers match a direct query.

Report the built block, and flag any figure that differs from Part A — the
corpus moves.

Acceptance: the block printed for the real corpus; the name-free test passes and
fails when a name is deliberately injected.

---

### Step 2 — The section on /method

A fifth section on `MethodPage.tsx`, after validation and before the nulls
statement — entity resolution is a validation story, and the nulls statement
should stay last because it is the page's closing argument.

Case 1: the merged key, its raw strings, and the award count and total per firm.
Show the rule as the section renders it, not as prose retyped from `queries.py`.

Case 2 gets the room the brief asks for: **before** (412 named awards, 184
surnames, 2 candidate matches), **after** (both resolved on provenance, 0
genuine matches), and the two firms with what each actually is. The three limits
sit with their figures (B.6).

No number and no firm string in JSX — everything renders from the snapshot
(`METHOD_PAGE_PLAN.md`'s standing rule).

Acceptance: build + lint; in DRAFT mode the section renders with all 15
multi-variant firms and both collisions; pick three strings on screen and name
the database rows they came from.

---

### Step 3 — The publish boundary

Settle B.5 first.

If yes: add `"method": "public"` to `SNAPSHOT_TIER`; correct the `src/cli.py`
comment about S7 (B.2) to state why this payload is name-free rather than that
the file is exempt; confirm `method.json` is inside Editor's scope and note the
first review pass; extend the publish-gate test to cover the new tier.

If no: leave the tier alone and record in `docs/TESTING.md` that /method is a
Draft-mode surface, so the next reader does not find an empty page and treat it
as a bug.

Acceptance: `pytest -q` green including the publish-gate tests; a `council
draft` run followed by the publish path puts the file where the decision says it
goes.

---

### Step 4 — Documentation

- `docs/frontend/METHOD_PAGE_PLAN.md` — the fifth section exists; its source is
  the live database rather than one of the five files.
- `docs/MAP.md` — extend the `/method` row: entity-resolution demonstrations
  live in `build_method_record()` and must reuse the analysis's own helpers
  (`_normalise_contractor`, `_is_redacted_recipient`,
  `decider_supplier_conflict`) rather than re-deriving them.
- `docs/TESTING.md` — whatever Step 3 settled.
- `docs/strategy/PRIVATE_ASSESSMENT.md` — B.1's decision and its residual: the
  surname is inferable from the firm's own name, and the site does not assert
  the pairing.
- Mark this file's status **built**.

---

### Deliberately not in this plan

Changing `_normalise_contractor()` or `_is_redacted_recipient()` · resolving
the remaining 15 multi-variant firms by hand into a canonical supplier table ·
any change to `decider_supplier_conflict()`'s logic or to what the scorecard
says about it · a general entity-resolution page covering councillor identity
(the dedup passes) — this section covers suppliers and the surname join only.
