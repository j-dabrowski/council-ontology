# Frontend / Product Roadmap

Forward-looking product surfaces for the dashboard. Relocated from the former
ANALYSIS_ROADMAP.md (the analysis-query layer it sat in is now in
`../pipeline/PIPELINE.md`). Build backlog for panel interactivity is in
`INTERACTIVITY.md`.

---

### F1 — Council boundary map (per-council Overview + aggregate Map page)

The same GeoJSON + data pipeline serves two surfaces:

**Surface A — Per-council Overview page (static graphic)**
A programmatically generated SVG or Canvas image rendered from structured data — not
AI-generated. Lives on each council's Overview page as a geographic anchor for the report.

What it shows:
- Council boundary polygon (GeoJSON)
- Tender award locations as dots (from geocoded `sites` table — depends on E1)
- Meeting venue (council chambers) as a distinct marker
- Prominent suburb labels and recognisable landmarks within the boundary

Rendering approach: D3.js or equivalent — project GeoJSON boundary into a fixed viewport,
overlay DB-sourced points. Outputs a deterministic image from the current data; re-renders
when data changes.

**Surface B — Map page (interactive aggregate view)**
The existing Leaflet map on `/map` overlays all council boundary polygons simultaneously,
covering WA or the Perth metro area. Each polygon is coloured or annotated with summary
data (e.g. transparency score, number of tenders, recusal rate). Users can zoom and pan
freely; clicking a council boundary opens a summary card linking to that council's report.

This gives the Map page a clear purpose: "see how councils compare geographically." As more
councils are added, the map fills in and becomes the product's discovery surface — readers
find their council on the map and drill into its report.

**Data needed:**
- Council boundary GeoJSON for each council (publicly available from data.wa.gov.au)
- Geocoded tender/planning sites (E1)
- Meeting venue coordinates (manual entry — one-off per council)
- Per-council summary stats for the map overlay (from existing scorecard/analysis queries)
- Optional: suburb boundary GeoJSON for labelling within the per-council graphic

**Scope note:** This is a self-contained frontend sub-project. The render pipeline (data → SVG)
can be built independently of the rest of the analysis stack. The same GeoJSON and data
contracts generalise to any council — adding a council means sourcing its boundary file
and running the geocoding step.

---

### F2 — Monthly digest feed (Overview page, Latest Activity)

An automated pipeline that triggers when new meeting minutes are published, extracts 2–4
highlights, stores a structured digest record, and renders a fade-back timeline on the
Overview page.

**Pipeline:**
1. Scraper detects new minutes on the council website (poll or webhook)
2. Minutes extracted via existing pipeline
3. Digest generation step: prompt selects 2–4 notable items from the new minutes —
   a tender awarded, a contentious vote, a recusal, a new conflict, anything with
   unusual public engagement. Keyed off interestingness, not volume.
4. Digest record written to a new `digests` table: `(council_id, period_start, period_end,
   highlights JSON, generated_at)`

**Frontend — Latest Activity section (Overview page):**
- Most recent digest shown prominently
- Previous months accessible via scroll/click with fade transition
- Default display window: 6 months; all historical digests stored and queryable
- Granularity follows publication cadence (typically monthly, occasionally fortnightly)

**Key design challenge:** The highlight extraction prompt. It must select for
*interestingness to a general reader*, not just high-volume or high-dollar items.
Requires iteration and a test battery of known-notable past events.

**2026-08-26 — the battery now declares which of its tests are eligible for
this.** Every `TestResult` in `src/analysis/tests.py` carries a `scope`
field (`SCOPE_WHOLE_CORPUS` / `SCOPE_SINGLE_MEETING`, one or both) declaring
which granularity that finding-type is *meaningful* at — not which
granularity it's currently computed at; every generator today still only
ever runs over the whole corpus. 14 of the 29 existing tests are tagged
single-meeting-eligible (direct event flags — a tender awarded, an item
closed, a conflict declared — or comparisons against an already-established
corpus-wide baseline); the other 15 stay whole-corpus only (entrenchment,
cohort, seasonal, or bunching patterns a single meeting can't exhibit).
`Refiner_prompt.txt` (v1.3) now declares `scope` for every newly-codified
test going forward, so this list stays current without a re-audit.

**Still unbuilt, and a real step beyond tagging:** actually computing any
tagged test over one meeting's data (period-filterable queries, a
`run_meeting_digest()`-shaped entry point), and giving Explorer/Refiner the
ability to originate genuinely new single-meeting hypotheses rather than
only tag existing ones. Single-meeting claims are more individually
attributable than corpus-wide aggregates (one date, few actors), so this
needs its own look at S7/S9/defamation exposure before it goes anywhere
near automation — not scheduled yet.

**Monetisation alignment:**
- Latest month's digest: free (drives return visits and sharing)
- Historical digests beyond 6 months: paywalled or email-gated
- Email alerts ("new minutes published — here's what matters"): paid tier

---

### F3 — Paywalled full report (quotation-sourced)

The plan (2026-08): three report tiers — a free summary, free graphs/stats,
and a paywalled "full" report with quotation-level sourcing behind every
claim. Not built yet; two things are, so this isn't starting from zero.

**What's already built (2026-08, see `docs/TESTING.md` "A future paywalled
tier" section):** every snapshot `council draft` produces is tagged
`"public"` or `"full"` in a `SNAPSHOT_TIER` map (`src/cli.py`), defaulting
to `"full"` (private) unless explicitly listed otherwise. `council publish`
already routes `"full"`-tier snapshots to a private destination
(`data/published_full/`, and a private GCS prefix in CI) that never touches
git or `frontend/public/`. No snapshot is tagged `"public"` yet — that's
the open decision below.

**What's still an open product decision:**
- **The actual split.** Two live options discussed and not yet chosen:
  same panels with quote text stripped for the free tier vs. redacted
  restored for paywalled; or whole panels free vs. whole panels paywalled
  (the ones with named-individual claims — Recusal, Power, Tenders — being
  the natural paywall candidates).
- **The serving backend.** Nothing serves the `"full"` tier to a paying
  user yet, and it can't be a static file — a client-side paywall doesn't
  protect a static asset; anyone can fetch it directly by URL regardless of
  UI gating. It needs a real server-side check (session + entitlement, e.g.
  Stripe) before returning data, most likely a Cloud Run endpoint reading
  from the private GCS prefix above — same OIDC trust relationship the
  publish pipeline already uses, extended rather than duplicated (see
  `docs/TESTING.md` "Where this goes next").

**Scope note:** don't build the backend speculatively before the tier
split is decided — the split determines what the backend's authorization
model even needs to check (per-panel vs. per-field), so deciding that first
avoids building the wrong shape twice.

---
