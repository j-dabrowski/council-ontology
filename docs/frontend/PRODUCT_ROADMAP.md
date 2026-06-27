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

**Monetisation alignment:**
- Latest month's digest: free (drives return visits and sharing)
- Historical digests beyond 6 months: paywalled or email-gated
- Email alerts ("new minutes published — here's what matters"): paid tier

---
