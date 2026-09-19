# Codebase Map — Current State (Reconnaissance)

Produced for `docs/uplift/00-README.md`. Reconnaissance only: no evaluation, no
proposed changes. Every claim below cites a file path and, where useful, a
line number or symbol name. Items that could not be determined from the code
are marked `INVESTIGATE`.

---

## 1. DATAFLOW — source PDF to rendered panel

Stages, in order, with entry point and function. The CLI (`src/cli.py`,
5,572 lines) is the front door for every stage; each stage is a separate
`council <subcommand>`, run manually, one at a time — there is no single
process that runs the whole pipeline end to end.

1. **Scrape** — `council scrape <council>` → `cmd_scrape` (`src/cli.py:462`).
   Council-specific scraper subclass (`src/scraper/cambridge.py`, class
   `CambridgeScraper` at `:570`; base interface `src/scraper/base.py`,
   `BaseCouncilScraper` at `:125`) discovers meeting pages (sitemap, search,
   Playwright, Wayback fallback — `_collect_from_sitemap`/`_collect_from_search`/
   `_collect_from_playwright`/`_collect_from_wayback_pdfs`, `cambridge.py:131,171,199,478`)
   and downloads PDFs to `data/raw/<council>/*.pdf`, writing
   `data/raw/<council>/manifest.json`.
2. **Scraper audit / Wayback fill** — `council scraper-audit` and
   `council wayback-fill` (parsers at `src/cli.py:5167,5191`) — cadence
   gap detection and archive-based recovery. Scripted, no LLM.
3. **Census (Level 0)** — `council census <council>` → `cmd_census`
   (`src/cli.py:1345`, delegates to `scripts/census.py`). Free text
   extraction + keyword scan, no LLM. Writes `data/census.json`.
4. **Inventory (Level 1)** — `council inventory <council>` → `cmd_inventory`
   (`src/cli.py:1350`, delegates to `scripts/inventory.py`). One Claude call
   per document (see §2). Writes `data/inventories/*.json`.
5. **Typology (Level 1→2)** — `council typology` → `cmd_typology`
   (`src/cli.py:1355`, delegates to `scripts/inventory_typology.py`). Pure
   text analysis of the inventory output, no new LLM call.
6. **Sample selection (3a)** — `council sample` → `cmd_sample`
   (`src/cli.py:1360`, `scripts/stratified_sample.py`). Writes
   `data/<council>_sample.json`.
7. **Sample extraction (3b) / validation (3c)** — `council extract-sample`
   (`cmd_extract_sample`, `:1365`) and `council validate-sample`
   (`cmd_validate_sample`, `:1389`, `scripts/validate_sample.py`, sharing
   logic with `src/validation/core.py`).
8. **Full extraction (Level 5)** — `council extract <council>` →
   `cmd_extract` (`src/cli.py:511`). PDF → plain text (subprocess worker,
   `_extract_pdf_text_worker`, `src/cli.py:40`, or the extractor's own
   `extract_text_from_pdf`, `src/extraction/extractor.py:93` — two separate
   codepaths, see §2/§9) → `MinutesExtractor.extract_from_pdf`
   (`extractor.py:424`) → Claude API → `save_extraction()`
   (`extractor.py:755`) writes rows to `data/council.db`. Batch-mode variant
   goes through `council extract --batch` → `submit_batch`/`retrieve_batch_results`
   (`extractor.py:576,582`) → `council batch-collect` (`cmd_batch_collect`,
   `src/cli.py:900`).
9. **Full validation (Level 4)** — `council validate <council>` →
   `cmd_validate` (`src/cli.py:1394`, `scripts/validate_extraction.py`).
   Writes `data/validation/*.json` + `summary.json`.
10. **Audit (Level 6)** — `council audit` (parser `src/cli.py:5139`,
    `scripts/audit_report.py`). Human-in-the-loop, writes
    `data/audit_report.md`.
11. **Dynamic layer** — `council build-relationships` (parser `:5111`,
    `scripts/build_relationships.py`) computes ALLY/OPPONENT edges and
    writes to the `relationships` table. Not read by any downstream stage
    (§3, §9).
12. **Profile** — `council profile <council>` → `cmd_profile`
    (`src/cli.py:1424`, `src/analysis/profile.py`). Scripted, no LLM.
13. **Explore / Refine (S3/S4)** — `council explore` / `council refine` →
    both dispatch through `_cmd_agent_prompt()` (`src/cli.py:1399`) to a
    real `claude -p` subprocess (see §6). Refine's output is a hand-added
    (agent-written) entry in `src/analysis/tests.py` / `queries.py` —
    there is no automatic code generation; the session edits the files.
14. **Draft** — `council draft <council>` → `cmd_draft` (`src/cli.py:3727`)
    → `_generate_snapshots()` (`src/cli.py:2105`) → `run_test_battery()`
    (`src/analysis/tests.py:2301`) computes the 29-test battery (§4) →
    `src/invariant_gate.py`'s `run_invariant_gate()` runs over the battery
    (scripted, no LLM) → JSON snapshots written to
    `data/draft/<council>/<run_id>/*.json` plus `manifest.json`
    (file hashes + tiers, `src/publish_gate.py`'s `DraftManifest` shape).
15. **Editor / Fixer loop (S8)** — `council editor-loop` → scripted
    `scripts/conductor_loop.py:run_conductor_loop()` (`:227`), which shells
    out to `council editor` and `council fixer` (real `claude -p` sessions,
    see §6). Writes `defamation_review_<n>.json` / `fix_report_<track>_<n>.json`
    sidecars into the draft directory. Never calls `council publish`.
16. **Reply packets (S9)** — `council reply-packets` → `cmd_reply_packets`
    (`src/cli.py:1544`, `src/reply_packets.py`). Scripted, no LLM, never
    sends anything.
17. **Render (S10)** — `council render <mode> <council> <run_id>` →
    `_cmd_render` (`src/cli.py` inline handler set at the `render` subparser,
    ~`:4910`) → `_cmd_agent_prompt("renderer", ...)`. Per README and the
    render fork's finding, **never run for real** — no output artifacts
    exist from this stage as of this snapshot.
18. **Publish** — `council publish <council> --from-draft <dir>` →
    `cmd_publish` (`src/cli.py:4342`) → `src/publish_gate.py`:
    `verify_draft_integrity()` (hash check) → `check_clearance()` (gate
    profile) → `publish_snapshots()` copies bytes verbatim into
    `frontend/public/data/<council>/*.json` (public tier) and
    `data/published_full/<council>/<run_id>/*.json` (full tier). Never
    recomputes from the database.
19. **Render (frontend)** — Vite/React app (`frontend/src/`) fetches the
    published JSON via `getSnapshot()` (`frontend/src/api.ts:27`) and routes
    each battery test to a component via `PANEL_COMPONENTS`
    (`frontend/src/registry/components.tsx:31`), rendered inside
    `AnalysisPage.tsx` / `OverviewPage.tsx` (`frontend/src/pages/`).

**Where the flow is manual / split across services:** every arrow above is a
separate CLI invocation a human runs; nothing schedules them in sequence
(`.github/workflows/draft.yml` and `publish.yml` are `workflow_dispatch`
only — manually triggered, not chained to each other or to extraction).
`council extract`, `explore`, `refine`, `editor`, `fixer`, `render` all cost
real API/subscription usage and are never run automatically.

**INVESTIGATE:** whether any process runs stages 1–12 back-to-back for a
fresh corpus in one sitting, or whether every onboarding is done by a human
manually running each command in order — `pipeline/PIPELINE.md`'s "Corpus
onboarding order" section is described in `docs/MAP.md:329` as "a design
sketch, not built," which suggests the latter, but this was not verified
against the doc's actual content in this pass.

---

## 2. EXTRACTION LAYER

### Claude API call sites

- `src/extraction/extractor.py`, class `MinutesExtractor.__init__`
  (`:173-174`) creates one `anthropic.Anthropic()` client. Model is a module
  constant `_MODEL = "claude-haiku-4-5-20251001"` (`:30`), with commented-out
  alternates (`:28-29`) — model choice is a manual code edit, not a runtime
  flag or config value.
- `_extract_chunk` (`:316-422`) is the call site: nested `_call_api()`
  (`:354-365`) uses `self._client.messages.stream(...)`,
  `max_tokens=64_000`, `system=system_prompt`, one user message,
  `thinking={"type":"adaptive"}` when the model isn't Haiku (`:346,361-362`).
  Wrapped in `@retry` (tenacity) on `APIConnectionError`/`APIStatusError`,
  3 attempts, exponential backoff (`:348-353`).
- System prompt chosen per chunk: `_AGENDA_SYSTEM_PROMPT` for agendas, else
  `_SYSTEM_PROMPT` (`:330`).
- Batch path: `build_batch_requests`/`build_requests_from_text`
  (`:456,529`) build one request dict per document (each carrying its own
  `model=self._model`, `:503,555`); `submit_batch` (`:576-578`) calls
  `.messages.batches.create`; `retrieve_batch_results` (`:582-603`) calls
  `.batches.retrieve`/`.batches.results`.
- `src/cli.py`'s `cmd_extract`/`cmd_extract_sample`/batch commands drive
  `MinutesExtractor` — they do not call the Anthropic SDK directly.
- `scripts/compare_models.py` (`council compare`) is an independent call
  site: `_run_one` (`:52`) instantiates a separate `MinutesExtractor` per
  model in a `MODELS` list, runs three extractions in parallel for one PDF,
  writes nothing to the DB.
- `scripts/inventory.py` (`council inventory`, Level 1) is a fully separate
  call path: its own client getter `_get_client()` (`:189-197`), its own
  `_call_api()` (`:201-218`) using a distinct `INVENTORY_MODEL`, and its own
  prompt file (`inventory_prompt.txt`), not the extraction prompts.

### Prompt files and versioning

- `src/extraction/system_prompt.txt` (293 lines), `agenda_system_prompt.txt`
  (172 lines) — loaded **once at process start** as module constants
  (`extractor.py:57-58`, `Path(...).read_text()`), not re-read per call; a
  mid-run edit to the prompt file has no effect on an already-running
  process.
- **No explicit version marker exists for the extraction prompts** — grep
  for `prompt_version`/`PROMPT_VERSION` across `src/`, `scripts/` finds no
  hits tied to `system_prompt.txt`/`agenda_system_prompt.txt`.
- The separate Level-1 **inventory** prompt does carry a version:
  `PROMPT_VERSION = "inventory-v3"` (`scripts/inventory.py:61`), used to
  build its cache key (`_cache_path()`, `:136-138`) — this is a distinct,
  smaller pipeline stage, not core extraction.

### What is persisted per call

- **Raw response**: every chunk's raw LLM response is archived before
  parsing — `_write_archive_chunk` (`extractor.py:61-88`), called from
  `_extract_chunk` right after `_call_api()` returns (`:367-384`). `src/cli.py`
  wires this to `data/llm_archive/<run_id or batch_id>/`, with a per-run
  manifest and a top-level `data/llm_archive/index.json` (`cli.py:240,259,
  360,368-441,632-721,930-1092`). This is separate from
  `.cache/llm_responses/`, which only caches Level-1 inventory calls
  (`scripts/inventory.py:_cache_path/_load_cache/_save_cache`, `:136-151`).
- **Parsed intermediate**: raw JSON is parsed into a Pydantic
  `ExtractedMeeting` (`src/extraction/schemas.py`) via
  `ExtractedMeeting.model_validate_json(raw)` (`extractor.py:390`) — this
  typed object is not itself persisted as a standalone artefact; only the
  archived raw JSON and the final DB rows survive.
- **Final rows**: `save_extraction()` (`extractor.py:755` onward) writes
  entity rows (`Motion`, `Vote`, `Councillor`, etc.) plus
  `ExtractionEvidence` rows via a closure `_ev()` (`:870-881`).
  `meeting.minutes_text = text` (`:862`) also persists the full flat
  extracted document text into the `meetings` table.

### Model version, timestamp, per-field provenance

- `Meeting.extracted_at` (`src/models/ontology.py:208`) is set from
  `datetime.utcnow()` in `save_extraction` (`extractor.py:864`). **No
  `model` or `prompt_version` column exists on any table** — confirmed by
  grep of `ontology.py`.
- Model/run identity is reconstructed **off-schema, at query time**, not
  stored on the row: `src/provenance.py`'s `meeting_provenance()`
  (`:70-108`) joins `Meeting.minutes_pdf_path` against
  `data/batch_jobs/<batch_id>.json` records (which do carry `model`,
  `submitted_at`). This only resolves for meetings extracted via the batch
  API — the module's own docstring states 130 meetings (non-batch
  extraction) have `run_id`/`model` = `None` at query time (`:84`); a sync
  extraction's model choice is recoverable only from the archived raw
  response JSON's `"model"` key (`extractor.py:80`), which no code joins
  back to `Meeting`.
- Per-field provenance: `ExtractionEvidence` (`ontology.py:451-470`) stores
  `quote_text`, `char_offset`, `char_length` per `(entity_table, entity_id)`
  pair — a **logical, non-FK reference** (`entity_table` varies per row;
  physical FK not used, per the model's own docstring, `:453-461`).
  `char_offset`/`char_length` are computed by `_resolve_offset()`
  (`extractor.py:650-662`) as `text.find(quote)` against the meeting's flat
  extracted text, and are `None` when the quote isn't found verbatim. The
  extractor-level docstring (`:653-655`) and the model docstring
  (`ontology.py:459-460`) differ slightly in how strongly they characterise
  a null offset as a hallucination signal — `src/analysis/evidence.py`'s
  module docstring (`:7-9`) states explicitly that `char_offset IS NULL`
  "must never be read as a paraphrase signal," i.e. downstream code
  deliberately does not treat it that way even though the storage-layer
  docstring calls it a hallucination flag.
- **No page number is stored at extraction time anywhere.** Confirmed by
  grep of `ontology.py`/`extractor.py` for "page": the only hits are
  per-page loop variables inside PDF-to-text conversion, not a stored
  field. `char_offset` indexes into the single flattened `minutes_text`
  string with no page-boundary markers preserved.
- **Page numbers, when they appear at all, are computed live at draft time**
  by a completely separate mechanism: `src/analysis/evidence.py`'s
  `resolve_evidence()` (`:157-289`) re-opens the source PDF with `fitz`
  page-by-page (`_pdf_pages()`, `:71-86`), classifies each stored
  `quote_text` against that fresh per-page text at three tiers (exact /
  normalised / stripped — `_classify()`, `:130-154`, reusing
  `src/validation/core.py`'s normalisers per that module's own docstring
  constraint), and returns the first page containing the match
  (`_find_page()`, `:114-127`). A quote spanning a page break, or a
  document whose PDF is no longer on disk (or `--fast-evidence` is passed,
  forcing the DB's flat `minutes_text` fallback), legitimately resolves to
  no page number — logged as `resolved_against: "minutes_text"` rather than
  `"pdf"` (`_build_meeting_source`, `:89-111`).

### Source PDF retention and page-addressability

- PDFs are retained on disk under `data/raw/<council>/*.pdf` (634 files
  confirmed under `data/raw/cambridge/` at time of this snapshot).
  `.gitignore:28` excludes them from git — not committed, but not deleted.
- **Not page-addressable in storage.** Two separate PDF-to-text codepaths
  exist and both flatten pages into one string with no boundary metadata
  kept:
  - `src/extraction/extractor.py:93-116` (`extract_text_from_pdf`) — tries
    `fitz` first, `pypdf` fallback, `"\n\n".join(parts)`.
  - `src/cli.py:40-64` (`_extract_pdf_text_worker`) — a **second,
    independent implementation**, run in a subprocess so a hung PDF library
    can be SIGKILLed (`:799`, 30s timeout). This one tries `pypdf` first,
    `fitz` fallback — the **opposite try-order** from `extractor.py`'s
    function. Both are called from different places: `extract_text_from_pdf`
    directly at `cli.py:923,1034`; the subprocess worker dispatched at
    `cli.py:814`. (See §9 for whether this duplication is live/dead.)
  - Page-addressability is only ever reconstructed **after the fact**, at
    draft/request time, by `src/analysis/evidence.py` re-parsing the PDF
    fresh per page (see above) — the stored `char_offset` alone cannot be
    mapped to a page without that re-parse.

### Name normalisation at the extraction layer

- `src/extraction/schemas.py:30` `_parse_name_string()` splits a raw name
  string (e.g. `"Cr John Smith"`) via the `_TITLES` regex (`:23-27`);
  called from `_parse_vote_string` (`:57`) and three other sites (`:77,107,416`).
  Pydantic-level, shape/format normalisation (case, key aliasing), not
  identity resolution.
- `src/extraction/extractor.py:675` `_normalise_councillor_name()` — strips
  honorifics, fixes swapped given/family fields, rejoins split surname
  particles, clears placeholder names. Called from `_get_or_create_councillor`
  (`:718-752`, which also does slug-based dedup lookup against existing
  `Councillor` rows) and again inline in `save_extraction` (`:917-919`).
  This is the function that actually decides which `Councillor` row a new
  vote/motion attaches to.
- No contractor-name normalisation exists in `src/extraction/` or the
  extraction-invoking parts of `src/cli.py` — that logic lives in the
  analysis layer (§4/§7).

---

## 3. DATABASE

Single SQLite file, `data/council.db` (185.6 MB at time of this snapshot,
gitignored, `src/storage/database.py`). No per-council database files —
`data/cambridge/` and `data/perth/` hold only pipeline JSON/text artefacts.
FK enforcement is applied at the application layer: `_enable_wal_and_fk`
(`src/storage/database.py:18-26`) runs `PRAGMA foreign_keys=ON` via a
SQLAlchemy `connect` event on every engine connection — a raw `sqlite3`
CLI session against the file does not get this pragma automatically.

**No schema drift**: all 20 tables in the live `.schema` output have a 1:1
corresponding class in `src/models/ontology.py`, and vice versa.

| Table | Rows | PK | Grain | One row represents | FK out | Live / stale |
|---|---|---|---|---|---|---|
| `councils` | 3 | id | `id` (unique `name`) | One council (Cambridge, "City of Testville" fixture, Perth) | — | Live — keyed by `short_name` everywhere |
| `councillors` | 423 | id | `id` (unique `slug`) | One deduplicated person | — | Live — extraction, queries, tests, frontend |
| `councillor_terms` | 125 | id | `(councillor_id, council_id, term_start)`, enforced by a `uq_term` unique constraint — clean | One tenure stint (ward/role/dates) | councillor_id→councillors, council_id→councils | Live but thin — `profile.py`, `queries.py` (Mayor-term lookup, `:3289-3293`), `evidence.py`; **not** in the `tests.py` battery, not read by frontend directly |
| `sites` | 2,494 | id | `id`; no uniqueness constraint on address — grain not fully clean | One physical address in planning matters | council_id→councils | Live — queries, frontend map/record page, `scripts/geocode_sites.py` writes lat/lng |
| `meetings` | 853 | id | **not clean** — no unique constraint on `(council_id, meeting_date, meeting_type)`; 130 groups of that tuple hold 2+ rows (e.g. two rows both `council_id=1`, `2022-10-18`, "Development Committee," different source PDFs, one `document_type='minutes'`/one `'unknown'`) — real grain is closer to one row per **source document**, not one row per real-world meeting | One ingested source document | council_id→councils | Live — extractor writes, ~30 files read |
| `motions` | 15,481 | id | `id` (no natural key; `item_number` not unique across meetings) | One formal motion | meeting_id→meetings, moved_by_id→councillors, seconded_by_id→councillors | Live — digest, divergence, tests, queries, frontend |
| `votes` | 29,028 | id | `(motion_id, councillor_id)`, enforced by `uq_vote` — clean | One councillor's vote on one motion | motion_id→motions, councillor_id→councillors | Live — queries, tests, dedup, build_relationships |
| `planning_applications` | 3,400 | id | `id`; `reference_number` indexed but nullable/non-unique | One development application | motion_id→motions (nullable), site_id→sites (nullable) | Live — queries, tests, evidence, record_streets, frontend record page |
| `community_submissions` | 2,353 | id | `id` | One written public submission | application_id→planning_applications (nullable), motion_id→motions (nullable) | Live — queries, evidence |
| `public_questions` | 3,620 | id | `id` | One public question | meeting_id→meetings | Live — queries, tests, frontend `QuestionResponsivenessPanel.tsx` |
| `deputations` | 1,518 | id | `id` | One deputation | meeting_id→meetings | Live — queries, tests, frontend `EngagementChart.tsx` |
| `petitions` | 391 | id | `id` | One petition | meeting_id→meetings | Live in queries/frontend EngagementChart, **not in the `tests.py` battery** |
| `appointments` | 947 | id | `id` | One councillor appointment to an external body | meeting_id→meetings, councillor_id→councillors (nullable) | Live in `queries.py`/`evidence.py`/`profile.py`; **not in `tests.py`, not in any frontend component** |
| `committee_reports` | 911 | id | `id` | One committee report tabled | meeting_id→meetings | **Extraction- and profile-only** — zero references in `queries.py`, `tests.py`, or frontend |
| `budget_items` | 4,252 | id | `id` | One budget line item | meeting_id→meetings | Live — `queries.py`, generic `entity_table="budget_items"` path into `TransparencyTrendPanel.tsx` |
| `interest_declarations` | 2,130 | id | `id` | One declared conflict of interest | meeting_id→meetings, councillor_id→councillors (nullable) | Live — queries, tests, evidence, frontend Conflict panels |
| `tenders` | 969 | id | `id`; `reference_number` indexed, non-unique | One tender awarded | meeting_id→meetings | Live — queries, tests, evidence, `method.py`, frontend Transparency/Record pages |
| `delegated_decisions` | 1,590 | id | `id` | One officer delegated decision | meeting_id→meetings | Live — queries, tests, evidence, cli |
| `building_permits` | 847 | id | `id`; `reference_number` indexed, non-unique | One building permit | meeting_id→meetings | **Extraction- and profile-only** — zero references in `queries.py`, `tests.py`, or frontend |
| `other_items` | 12,157 | id | `id` | Catch-all extracted item not matching another entity type | meeting_id→meetings | Live — digest, profile, lookup_search, evidence, cli, tests |
| `extraction_evidence` | 72,984 | id | `id`; logical (non-FK) grain `(entity_table, entity_id)` → many quotes per entity | One verbatim source quote backing one field/entity | meeting_id→meetings (real FK); `entity_table`/`entity_id` explicitly polymorphic, not a physical FK (`ontology.py:452-461`) | Live — drill-down/provenance backbone; `evidence.py`, `queries.py`, `profile.py`, every frontend drill-down |
| `relationships` | 158 | id | `id`; logical `(kind, source_type, source_id, target_type, target_id)`, also not FK-enforced (`ontology.py:479-489`) | One typed edge (ALLY/OPPONENT/etc.) between two entities | — (none physical) | **Write-only** — populated by `council build-relationships` (`scripts/build_relationships.py`); zero reads found in `queries.py` or `tests.py` |

Two polymorphic "logical FK" patterns exist by explicit design
(`extraction_evidence.entity_table/entity_id`, `relationships.source_type/
target_type`+`target_id`) — both documented in `ontology.py` docstrings as
intentional (SQLite cannot FK to a variable target table), not oversights.

**Non-SQLite structured stores adjacent to the DB** (config/registry data,
not corpus data — noted, not detailed): `config/test_registry.json`,
`config/rating.json`, `config/agent_switches.json`, `config/invariants.json`,
`config/council_eras.json`, `investigator/coverage_register.json`.

**INVESTIGATE:** whether `sites` has any de-duplication for the same
physical address recurring across years — no unique constraint and no
dedup script analogous to `scripts/dedup_councillors.py` was found for
sites in this pass.

---

## 4. ANALYSIS LAYER

### Where statistics are computed

The **Standard Test Battery** is `run_test_battery()`
(`src/analysis/tests.py:2301`), driven by a `_GENERATORS` dict
(`tests.py:2244-2274` onward) mapping **29** `test_id`s to `_t_*` generator
functions — confirmed by direct count (`grep -c '": _t_'` = 29) and matching
`config/test_registry.json`'s row count exactly (also 29). Full map (a
representative subset; all 29 are one-line entries in `_GENERATORS`):

| test_id | function | def line |
|---|---|---|
| procurement.threshold_gaming | `_t_threshold_gaming` | 1115 |
| procurement.incumbency | `_t_procurement_incumbency` | 1159 |
| procurement.single_source | `_t_single_source` | 1776 |
| procurement.concentration | `_t_tender_concentration` | 923 |
| procurement.decider_supplier_conflict | `_t_decider_supplier_conflict` | 993 |
| conflict.recusal_management | `_t_recusal_overall` | 205 |
| conflict.recusal_trend | `_t_recusal_trend` | 307 |
| conflict.delegate_body_conflict | `_t_delegate_body_conflict` | 370 |
| planning.big_dollar_leniency | `_t_big_dollar_leniency` | 1211 |
| planning.repeat_applicant | `_t_repeat_applicant` | 1309 |
| planning.objection_responsiveness | `_t_objection_dose` | 853 |
| governance.officer_ratification | `_t_officer_divergence` | 577 |
| governance.power_spread | `_t_voting_power` | 640 |
| governance.oversight_body_capture | `_t_oversight_body_capture` | 678 |
| governance.unanimity_trend | `_t_unanimity_trend` | 1374 |
| governance.chair_capture | `_t_mayoral` | 754 |
| governance.durable_faction | `_t_sponsorship` | 785 |
| governance.incumbency | `_t_tenure` | 818 |
| governance.freshman_effect | `_t_freshman` | 1484 |
| governance.election_cycle | `_t_election_cycle` | 1536 |
| governance.attendance | `_t_attendance` | 1648 |
| transparency.confidential_share | `_t_transparency` | 497 |
| transparency.confidential_tender_size | `_t_confidential_tender_size` | 1856 |
| transparency.confidential_topics | `_t_confidential_topics` | 1990 |
| finance.eoy_spending | `_t_eoy_spending` | 1441 |
| finance.reserve_trajectory | `_t_reserve_trajectory` | 1787 |
| engagement.participation | `_t_engagement` | 1799 |
| engagement.deputation_dissent | `_t_deputation_dissent` | 1579 |
| engagement.question_responsiveness | `_t_question_responsiveness` | 2108 |

Most `_t_*` functions call one query helper from `src/analysis/queries.py`
(imported at `tests.py:43-59`) or `officer_divergence`
(`src/analysis/divergence.py`, imported at `tests.py:60`); many also have a
`SCOPE_SINGLE_MEETING` sibling (`_t_*_meeting`) re-deriving the same stat
for one meeting (used by the digest surface, §1).

Separately, `src/analysis/evidence.py` computes per-test drill-down
"evidence" bundles (~29 `evidence_for_*` functions, `:292` onward) — a
**separate computation path** from `tests.py`, re-deriving underlying rows
for display, called from `_generate_snapshots()` in `src/cli.py` (e.g.
`:3145-3157, 3164-3176, 3180-3192`, continuing through `~:3374`).

`src/analysis/rating.py`'s `compute_rating()` (`:65`) computes the overall
governance rating, downstream of and separate from per-test valence (see
below). `src/analysis/coverage_register.py`, `method.py`, `digest.py`,
`profile.py`, `meeting_baselines.py`, `lookup_search.py`,
`record_councillors.py`, `record_streets.py` are analysis modules outside
the 29-test battery, feeding other snapshots.

### Persisted intermediate between query results and panel props

**None.** `cmd_draft` (`src/cli.py:3727`) → `_generate_snapshots()`
(`:2105`) calls `run_test_battery(session, council_id, precomputed={...})`
(`:3112-3118`). The returned `list[TestResult]` is converted straight to
dicts by a local closure `_dc()` (`:2149-2154`, `dataclasses.asdict` +
isoformat coercion) and written directly to JSON by `_write()`
(`:2175-2181`). `_generate_snapshots()`'s own docstring (`:2110-2112`)
calls this in-memory battery list itself "the claim objects the S7
invariant gate checks" — i.e. the `TestResult` dataclass list *is* the only
claim-layer artefact that exists, and it lives only for the duration of one
`council draft` process; it is never written to a database table or a
standalone cache file independent of the final snapshot JSON.
`src/invariant_gate.py`'s `derive_claim_tier()` (referenced `cli.py:2100-2101`)
consumes the same in-memory list. `council publish` never recomputes —
per `src/publish_gate.py`, it only copies the already-written draft JSON
bytes after a hash check (§1, §6).

### Where a panel's grade/valence is decided

**Per-test valence/grade is decided inline in Python, inside each `_t_*`
function** — a hardcoded threshold check, then a ternary over
`SUPPORTIVE`/`NEUTRAL`/`CRITICAL` (`tests.py:64-66`) and `G_*` grade labels
(`:69-75`). No LLM involvement and no config-file threshold at this level.
Two concrete examples:
- `_t_threshold_gaming` (`:1124,1143-1144`): `clean = ratio is None or
  ratio <= 1.6` → `valence=SUPPORTIVE if clean else CRITICAL`. `1.6` is a
  literal in the function body.
- `_t_recusal_overall` (`:220,227-228`): `managed = stay < 50.0` →
  `valence=SUPPORTIVE if managed else CRITICAL`.

`config/test_registry.json` carries no threshold and no valence field
(fields present: `id, order, category, question_technical, question_public,
title_technical, title_public, principles, method, caveats, objection,
response, evidence_query, evidence_snapshot, has_deep_dive, public_interest,
meeting_scope, digest_threshold, detail_panel`). Its only runtime effect on
a `TestResult` is overwriting `title`/`question` after the generator
returns (`tests.py:2320-2321`) — deliberately, so the S7 invariant gate
scans the text actually displayed, not the raw generator string.

**Overall governance rating** (a separate, downstream statistic) is
computed by `src/analysis/rating.py:compute_rating()` (`:65`), driven by
`config/rating.json`: a base band from `critical_share` vs.
`bands[].max_critical_share` (`rating.py:99-102`; config bands: green
≤0.20, yellow ≤0.45, red ≤1.00), "floor" overrides that can only force a
*worse* band (`_floor_fires`, `:53-62`, applied `:105-120`; e.g. any single
"Integrity flag" grade forces `red`), and a `coverage_gate`
(`min_computable_share: 0.60`, `min_decisive_tests: 8`) that can override
everything to `"insufficient"` before the critical-share band is computed
(`:77-97`). Per its module docstring, this reads only
`valence`/`grade`/`data_ok`/`test_id` off each `TestResult` — never
headline/verdict prose.

### Where headline/body text originates, relative to the numbers

**Same code path, same function, by construction.** `headline` and
`verdict` are Python f-strings/ternaries written inline in the same `_t_*`
function that computes the number, using the same local variables — no LLM
call and no separate authoring step at battery-run time. Concrete trace,
`procurement.threshold_gaming` (`tests.py:1115-1156`):
- **Number**: `ratio = round(below/above, 2)` (`:1123`).
- **Grade/valence**: `clean = ratio is None or ratio <= 1.6` (`:1124`) —
  same function, same locals.
- **Headline/verdict**: `:1145-1149`, ternaries on `clean`.
- **Title/question** are the one part overridden post-hoc from
  `config/test_registry.json` (`:2320-2321`) — labels, not the substantive
  claim text.

So headline/verdict cannot drift from the number *within a single test*
(no serialization boundary between them). They **have** drifted from a
*differently-computed* presentation of the same fact elsewhere: `tests.py:210-214`
documents this happening — `_t_recusal_overall`'s `factor` is computed
deliberately "the same way `ConflictRecusalPanel.tsx` derives its own
headline factor... rather than a literal string," with a code comment
recording that the two had in fact drifted (a hardcoded "~80x" in one place
vs. the frontend panel's live 83x for the same draft's data, caught in a
2026-08-23 defamation-review pass) before being fixed by having the
frontend derive its figure live rather than duplicating it as a string.
This is the one documented instance in the current codebase of the
number/prose coupling being broken by an independent recomputation outside
`tests.py`.

There is no `FINDINGS_SUMMARY.md`- or Investigator-authored text read
inside `run_test_battery()` — the Investigator/Refiner/Explorer prompts
result in hand-added Python code in `tests.py`/`queries.py` (`council
refine`), not a runtime-read artefact.

**INVESTIGATE:** whether all 29 `_t_*` functions follow this same-function
headline/number pattern, or whether any delegate to a shared helper that
introduces a seam — only `_t_threshold_gaming` and `_t_recusal_overall`
were read in full for this section; the rest were confirmed only by
`_GENERATORS` membership and signature.

---

## 5. RENDER LAYER

### Component structure

`frontend/src/components/` (37 files). Registered in the panel routing
table, `PANEL_COMPONENTS` (`frontend/src/registry/components.tsx:31-62`,
27 entries: 13 bespoke components + 14 pointing at the generic
`BatteryTestBody`). The remaining 2 of the 29 battery tests have
`has_deep_dive: false` in `config/test_registry.json` and appear on the
scorecard only, with no registry entry — this accounts for the full
29 → 27 → 13+14 breakdown exactly (README's "23 test panels" figure is
stale against the current 29-row registry).

- **Bespoke panels** (registry-mapped): `ConflictRecusalPanel.tsx`,
  `RecusalTrendPanel.tsx`, `TenderConcentrationPanel.tsx`,
  `DivergencePanel.tsx`, `PowerPanel.tsx`, `SponsorshipNetworkPanel.tsx`,
  `TenurePanel.tsx`, `MayoralAgendaPanel.tsx`, `TransparencyTrendPanel.tsx`,
  `QuestionResponsivenessPanel.tsx`, `EngagementChart.tsx`,
  `ObjectionDosePanel.tsx`, and `TrendsChart.tsx` (exports
  `ContestationChart`, registered under `governance.unanimity_trend`).
- **Generic fallback**: `BatteryTestPanel.tsx` (exports `BatteryTestBody`),
  used for the other 14 registry rows.
- **Shared/shell**: `DrillDown.tsx`, `ValenceChip.tsx`, `SeverityChip.tsx`,
  `ScorecardPanel.tsx`, `OverviewPanel.tsx`, `CouncilHeader.tsx`,
  `CouncillorModal.tsx`, `RatingBand.tsx`, `SiteNav.tsx`, `SiteFooter.tsx`,
  `LatestMeetingStrip.tsx`, `DevModeSwitch.tsx`, `ObjectionResponse.tsx`,
  `Logo.tsx`.
- **Present but not registered** (per README's "retired, kept for reuse"
  list, independently confirmed absent from both `App.tsx` and
  `components.tsx`): `AlignmentHeatmap.tsx`, `CoMoverGraph.tsx`,
  `InterestsChart.tsx`, `PlanningTrendChart.tsx`,
  `PlanningObjectionsPanel.tsx`, `DissentProfilesChart.tsx`,
  `DissentCoalitionsPanel.tsx`. (`TrendsChart.tsx` is on this list in
  README but is in fact live — see §9.)

`frontend/src/pages/`: `AboutPage.tsx`, `AnalysisPage.tsx`,
`ContactPage.tsx`, `MapPage.tsx`, `MethodPage.tsx`, `OverviewPage.tsx`,
`RecordPage.tsx`, `WatchPage.tsx`.

`frontend/src/api.ts` (1,279 lines) holds every panel's TypeScript
interface plus two data-access functions: `get<T>()` (`:7-17`, live fetch
to a FastAPI URL) and `getSnapshot<T>()` (`:27-44`, reads
`/data/{council}/{name}.json` in Publish mode or
`/data/draft/{council}/{name}.json` in Draft mode). **`get()` is unused in
practice**: its own comment reads "Reserved for future interactive API
endpoints" (`:4`), and every entry in the exported `api` object
(`:1214-1278`) calls `getSnapshot()` — none calls `get()`. `api/main.py`
(the FastAPI backend `get()` would target) is independently confirmed dead
(§9).

`frontend/src/hooks/useData.ts` — `useData()` (eager fetch, re-fires on
council-route change) and `useLazyData()` (fetch gated behind a `trigger()`
call, for snapshots too large to load on every visit).

### Charting library and axis/config location

`frontend/package.json`: `recharts@^3.8.1` (primary — bars/lines),
`react-force-graph-2d@^1.29.1` (network views, e.g.
`SponsorshipNetworkPanel.tsx`), `react-leaflet@^4.2.1` + `leaflet@^1.9.4`
(`MapPage.tsx`), `d3-color@^3.1.0` (color manipulation helper only). No
`chart.js`, no plain `d3`.

**No centralized chart-theme/constants file** — no `*theme*`/`*colors*`/
`*palette*` file under `frontend/src`. Colors are inline hex literals
scattered per component (19 separate files carry their own hex-color
literals, including `CoMoverGraph.tsx`, `ConflictRecusalPanel.tsx`,
`PowerPanel.tsx`, `TenderConcentrationPanel.tsx`, and others). The one
shared abstraction is `ValenceChip.tsx` (`:3-13`), which centralizes the
supportive/neutral/critical label+icon mapping via a CSS class
(`valence-chip valence-${valence}`) — but the underlying color values for
that class, and all per-chart bar/line colors, are not centralized.

**INVESTIGATE:** whether a stylesheet (`App.css`/`index.css`, not read in
this pass) centralizes the valence color palette even though per-chart
colors don't route through any shared config.

### Rendered output captured as a static image

**No.** `grep -rniE "html2canvas|puppeteer|playwright.*screenshot|
toDataURL|svg-to-png|dom-to-image"` across `frontend/` and `scripts/`
returns zero hits (confirmed independently, twice). `frontend/package.json`
has no image-capture dependency. Nothing in this codebase ever rasterizes a
rendered panel or chart to a static image file.

---

## 6. AGENTS AND ORCHESTRATION

### Prompt file layout — two directories, one is a dispatcher

Two prompt locations exist and serve different purposes:

- **`docs/agent_prompts/*.txt`** — `conductor.txt`, `editor_scorer.txt`,
  `editor.txt`, `explorer.txt`, `extraction_refine.txt`, `fixer.txt`,
  `inventory_refine.txt`, `refiner.txt`, `renderer.txt`, `researcher.txt`.
  These are the files actually `read_text()`'d by
  `scripts/conductor_loop.py`'s `load_prompt()` and `src/cli.py`'s
  `_cmd_agent_prompt()` (`:1399-1421`) when a `claude -p` subprocess is
  launched. **Confirmed thin dispatchers, not the substantive prompt
  text**: `docs/agent_prompts/explorer.txt`'s entire content is "Read
  docs/investigator/Investigator_prompt.txt in full (Parts 0–5), then
  docs/investigator/Explorer_prompt.txt as your operating mode. Read
  docs/investigator/INVESTIGATIONS.md first per the prompt's own
  instruction." — i.e. it instructs the invoked session to go read the
  real prompt.
- **`docs/investigator/*.txt`, `docs/review/editor/Editor_prompt.txt`,
  `docs/review/fixer/*.txt`, `docs/render/Renderer_prompt.txt`,
  `docs/research/Researcher_prompt.txt`** — the actual, substantive,
  versioned runtime prompts per `docs/MAP.md:9-19`. These are what the
  session reads once dispatched by the thin stub above.

### Agent roster

All confirmed real `claude -p` subprocess calls via
`scripts/conductor_loop.py`'s `run_claude()` (`:154-177`), not scripted
logic, by direct code read:

| Role | Invocation | Prompt dispatch | Cross-run state |
|---|---|---|---|
| Explorer (S3) | `council explore` → `src/cli.py:4864` | `docs/agent_prompts/explorer.txt` → `docs/investigator/Explorer_prompt.txt` | Appends to `docs/investigator/INVESTIGATIONS.md` |
| Refiner (S4) | `council refine` → `:4874` | `refiner.txt` → `docs/investigator/Refiner_prompt.txt` | Self-directing: re-reads `INVESTIGATIONS.md` each run per the CLI help text (`:4869-4872`); not independently verified against the prompt text itself |
| Editor (S8) | `council editor <council> <run_id>` → `:4928-4938` | `editor.txt` → `docs/review/editor/Editor_prompt.txt` | Writes `defamation_review_<n>.json` sidecar in the draft dir |
| Fixer (S8, 3 modes) | `council fixer <track> <council> <run_id>` → `:5020-5030`, tracks from `scripts/conductor_loop.py:60` (`FIXER_TRACKS = {"frontend","pipeline","doc"}`) | `fixer.txt` → `docs/review/fixer/<track>_mode.txt` | Writes `fix_report_<track>_<n>.json` sidecar |
| Renderer (S10, 3 modes) | `council render <mode> <council> <run_id>` → `:4892-4926` | `renderer.txt` → `docs/render/Renderer_prompt.txt` + mode file | None yet — code comment confirms "Not yet wired into any workflow (no calibration data)" (`:4899-4900`), matching README |
| Editor-scorer | `council editor-score` → `_cmd_editor_score()`, `:4974-5018` | `editor_scorer.txt`, gated behind deterministic Layer 1 (`src/editor_score.run_layer1`) | Writes `editor_score_<n>.json/.md` |
| Conductor | **not an agent today** | `docs/agent_prompts/conductor.txt` exists on disk but **nothing loads it** — confirmed by grep across `src/cli.py` and `scripts/*.py` for "conductor.txt": zero hits | Fully scripted instead: `scripts/conductor_loop.py:run_conductor_loop()` (`:227-297`); module docstring explains the agent-role design (`docs/review/CONDUCTOR.md`) was superseded once Editor/Fixer had machine-readable sidecar contracts to key off (`:9-15`) |
| Researcher | **No CLI subcommand** — confirmed by grep of `src/cli.py` for "researcher"/"research": zero hits. `docs/agent_prompts/researcher.txt` exists but is not wired to any `council` command; run some other way per `docs/research/RESEARCH_PROTOCOL.md`'s "own trigger" framing, not verified further in this pass | — | — |

### Invocation mechanics and state

`_cmd_agent_prompt()` (`src/cli.py:1399-1421`) and
`load_prompt()`/`run_claude()` (`scripts/conductor_loop.py`) are the single
shared implementation both the standalone CLI commands and the Conductor
loop call — no duplicated dispatch logic. `run_claude()` strips
`ANTHROPIC_API_KEY` from the child environment and passes
`--setting-sources project,local` (`conductor_loop.py:154-177`) so these
sessions bill on Claude subscription auth, never the pay-per-token API —
enforced twice (env-var strip + settings-source exclusion), per a code
comment tied to a specific prior incident (`:170-176`).

Cross-invocation state that does persist:
- `config/agent_switches.json` (`src/agent_config.py`) — hand-edited,
  genuinely persistent: `data_enrichment_status` (OPEN/FROZEN),
  `researcher_gate_mode` (file-review/auto-merge), `conductor_max_passes`.
- Conductor reads (not writes) the numbered sidecars each pass:
  `latest_review_record()` / `latest_fix_report()`
  (`conductor_loop.py:190-210,213-231`) — state scoped to one draft
  directory across passes of the *same* draft, not across different
  drafts/councils.

**INVESTIGATE:** whether Explorer reads/writes
`investigator/coverage_register.json` — `docs/MAP.md:167-175` states the
register exists but Explorer doesn't read it yet; not independently
verified against `docs/investigator/Explorer_prompt.txt`'s actual text in
this pass.

### Review/validation/QA chain between generation and publish

Exactly one fully-automated, code-only gate; one genuine LLM-judgment
stage with machine-readable contracts; one final code-enforced gate with
two profiles of differing strength.

1. **S7 invariant gate** (`src/invariant_gate.py`) — scripted, no LLM, runs
   inside `council draft` after the battery computes. Four checks in
   `run_invariant_gate()` (`:164-223`): `name-free-schema` (an
   institutional-unit claim must have empty `named_entities`, `:181-190`);
   `name-free-text` (regex-scans every rendered string — title, headline,
   verdict, question, chart labels via `_claim_text()`, `:96-105` — against
   the corpus's real councillor roster via `find_names_in_text()`,
   `:137-161`, explicitly built in response to "the 2026-08-06
   hardcoded-names incident," `:146`); `min-n` (an individual/
   individual_implicating claim needs `n > MIN_N`, config-sourced from
   `config/invariants.json` via `load_min_n()`, `:82-93`); `entity-resolution`
   (an individual claim needs `entity_resolution == "clean"`, `:212-221`).
   Also owns whole-batch tier derivation (`derive_claim_tier()`,
   `:226-239`) and a per-claim variant for the digest surface
   (`derive_claim_tiers()`, `:331-356`, using a small registered set of
   name-stripping "reduction" functions, `INSTITUTIONAL_PROJECTIONS`,
   `:305-309`, covering exactly 3 of the 29 tests today).
2. **Editor + Fixer loop (S8)** — real `claude -p` judgment, standalone
   (`council editor`, `council fixer`) or via the scripted
   `scripts/conductor_loop.py` (`council editor-loop`). Editor writes
   `defamation_review_<n>.json` (`run_id`/`status`/`tracks`); Fixer writes
   `fix_report_<track>_<n>.json`; a `BLOCKED` status halts the loop
   immediately (`escalate_blocked()`, `conductor_loop.py:233-246`). This
   chain **never calls `council publish`** — a stated invariant, and
   structurally true (no `"publish"` subprocess call anywhere in the file).
3. **`council publish` gate** (`src/publish_gate.py`) — code-enforced:
   `verify_draft_integrity()` (`:77-89`) re-hashes every snapshot against
   the draft manifest's recorded SHA-256 and refuses on any mismatch;
   `check_clearance()` (`:130-208`) has two profiles — `"interactive"` is a
   shallow stub (a `--confirm` note ≥10 characters, no identity/content
   verification, explicitly documented in the module docstring as "still
   exactly the minimal stub it always was," `:13-15`); `"auto"` is the real
   code-enforced path, re-reading the latest `defamation_review_<n>.json`
   and requiring its `run_id` to match the exact draft, `status == "PASS"`,
   and empty `tracks` (a PASS with non-empty tracks is treated as an
   inconsistent, untrusted record). `check_not_synthetic()` (`:107-127`)
   separately refuses to publish any council flagged `synthetic` in its
   `COUNCILS` registry entry — live in the DB as the "City of Testville"
   fixture row (§3).

---

## 7. ENTITY HANDLING

Every code path that normalises or canonicalises a name, by layer:

1. **`src/extraction/schemas.py:30`** `_parse_name_string()` — splits a raw
   name string via the `_TITLES` regex (`:23-27`). **Layer: extraction
   time**, inside Pydantic validators, before DB write.
2. **`src/extraction/extractor.py:675`** `_normalise_councillor_name()` —
   strips honorifics, fixes swapped fields, rejoins split surname
   particles, clears placeholders. Called from `_get_or_create_councillor`
   (`:718-752`) and inline in `save_extraction` (`:917-919`). **Layer:
   extraction time (DB write path)** — decides which `Councillor` row a
   new vote/motion attaches to.
3. **`scripts/dedup_councillors.py:227`** `normalise_name()` — same shape
   of logic (honorific stripping, particle rejoining, placeholder
   clearing) as `extractor.py:675`, linked only by a source comment
   (`:224`, "mirrors extractor._normalise_councillor_name") — **a second,
   independently-maintained implementation, not a shared import**. Also
   defines `make_slug` (`:258`) and `is_real_given` (`:263`) with no
   extractor-side equivalents. **Layer: dedup-maintenance script**
   (`council dedup`, wired at `src/cli.py:5334-5342`), run after the fact
   over already-extracted rows.
4. **`src/analysis/queries.py:2052`** `_normalise_contractor()` —
   lowercases, strips company suffixes (`pty ltd`, `p/l`, etc.), strips
   punctuation, collapses whitespace. Companion `_is_redacted_recipient()`
   (`:2031`, regex `_REDACTED_RECIPIENT_RE` at `:2046`) filters
   de-identification placeholders ("Respondent 4," "Tenderer 1") out of
   contractor aggregation. Used at `:2154, 2179-2180`, inside
   `decider_supplier_conflict()` (`:2280`), and at `:2427/2430`. Companion
   `_normalise_tender_ref()` (`:2062`). **Layer: analysis/query time** —
   recomputed fresh on every call, not persisted.
5. **`src/analysis/method.py:544`** `_build_entity_resolution()` →
   `_build_supplier_normalisation()` (`:551`) directly reuses (imports,
   does not reimplement) `_normalise_contractor`/`_is_redacted_recipient`
   from `queries.py` for the `/method` page's public demonstration.
   `_duplicate_extraction_note()` (`:599`) also calls
   `_normalise_contractor` directly (`:604`). **Layer: method-page
   display time**, correctly reusing the analysis layer rather than
   duplicating it.
6. **`src/analysis/record_streets.py`** — `extract_street_name()` (`:47`)
   and `extract_suburb()` (`:65`) are regex token-extraction from
   `Site.address`, not fuzzy name canonicalisation (no variant-collapsing);
   done because `sites.suburb` is 100% NULL in the corpus (`:66-67`
   comment).
7. **`src/analysis/record_councillors.py`** — no normalisation of its own;
   consumes already-resolved `Councillor` rows.

**Duplication finding**: councillor-name normalisation is implemented
twice, independently (`extractor.py:675` and `dedup_councillors.py:227`),
linked only by a comment, not a shared function — a change to one has no
mechanism to propagate to the other. Contractor-name normalisation
(`queries.py:2052`) has a single implementation correctly reused by the
method page.

---

## 8. CONFIG AND CONSTANTS

### Framework references (Nolan / CIPFA / Best Value)

- Prose/methodology lives in `docs/investigator/Investigator_prompt.txt`
  (framework sections at `:395,416,436`; applied narratively at `:618,755-756`).
- `config/test_registry.json` carries a `"principles"` array per test row.
- **`src/analysis/tests.py` also hardcodes the identical framework labels
  as Python string literals** on `TestResult.principle` (declared `str` at
  `:107`) — e.g. `principle="Nolan Integrity, Objectivity · CIPFA-A"`
  (`:225`), and dozens more (`:256,294,316,356,398,417,509,563,593` and on
  through the file). So the framework label exists in **two places kept in
  sync by hand**: the registry's `principles` array and the Python
  source's `principle=` string — neither derives from the other.
- **`frontend/src/components/OverviewPanel.tsx:38-80`** independently
  hardcodes another set of Nolan/CIPFA principle strings (e.g.
  `principle: "Nolan · Accountability, Openness"`, `:38`) as a third,
  separately-maintained copy for the Overview panel's own cross-cutting
  synthesis list.
- Also referenced in prose on `frontend/src/pages/AboutPage.tsx:87-89`,
  `ContactPage.tsx:93`, and `frontend/src/components/ScorecardPanel.tsx:124`.

### Era / date-window boundaries

- `config/council_eras.json` — per-council external-scrutiny windows
  (e.g. `cambridge: {label: "Authorised Inquiry", from: 2018, to: 2021}`),
  loaded via `src/council_eras.py` (`load_council_eras()` `:32`,
  `era_window_for()` `:42`). The module docstring (`:4-10`) states this
  *replaces* a formerly-hardcoded 2018–2021 window that used to live
  directly in `queries.py`'s `_recusal_era()` — already moved to config as
  of this snapshot (residual comments referencing the old hardcoded window
  remain at `queries.py:2496,3102,3377,3406` as historical explanation, not
  as live logic).
- **Still hardcoded, not moved to config**: `tests.py:1119` —
  `modern = [a for a, y in rows if y >= 2015]`, documented by an adjacent
  comment (`:1116`) as "the WA public-tender line: ~$100k pre-Oct-2015,
  $250k after," with `era="2015+ ($250k regime)"` at `:1152`.
  `tests.py:1806` similarly hardcodes `y.year >= 2016`.
- `frontend/src/components/PowerPanel.tsx:135` — hardcoded electoral-term
  boundaries as a JS array literal: `const termOrder = ["2003-07",
  "2007-11", "2011-15", "2015-19", "2019-23", "2023-27"]`.
- `frontend/src/components/SponsorshipNetworkPanel.tsx:258-259` —
  hardcoded years (2007, 2016–19, 2020–23) inside narrative JSX text.

### Other thresholds

- **MIN_N** (invariant-gate minimum sample floor) is properly config-driven:
  `config/invariants.json`, loaded by `load_min_n()`
  (`src/invariant_gate.py:82`), consumed at `:204-209,354`.
- **Ally/opponent vote-alignment thresholds are hardcoded twice,
  independently**: `scripts/build_relationships.py:24-25` defines
  `DEFAULT_ALLY_THRESHOLD = 0.85` / `DEFAULT_OPPONENT_THRESHOLD = 0.40`;
  `src/cli.py:5118,5120` independently redeclares the same numeric
  defaults on the argparse flags rather than importing the script's
  constants. (README's example command shows `--opponent 0.60`, a
  non-default value passed explicitly at the CLI — not a further
  discrepancy in the code itself.)
- **`digest_threshold`** is properly config-driven per row in
  `config/test_registry.json` (most rows `null`; a subset carry an object,
  e.g. lines 93,119,145,219) with no duplicated hardcoded threshold found
  in `src/analysis/digest.py`.

---

## 9. DEAD OR REDUNDANT

1. **`api/main.py`** — confirmed dead. No reference in any
   `.github/workflows/*.yml`, `frontend/package.json`, or any
   `frontend/src/*.ts(x)` fetch call. `fastapi` remains a `pyproject.toml`
   dependency (`:21`) despite this. Matches README's own "legacy... not
   used by the live site" description (`README.md:269-270`).
2. **Frontend "retired" components** — README's list
   (`AlignmentHeatmap`, `CoMoverGraph`, `TrendsChart`, `InterestsChart`,
   `PlanningTrendChart`, `PlanningObjections`, `DissentProfiles`,
   `DissentCoalitions`) is **stale on one entry**: grep of
   `frontend/src/App.tsx` and `frontend/src/registry/components.tsx`
   confirms zero references to `AlignmentHeatmap`, `CoMoverGraph`,
   `InterestsChart`, `PlanningTrendChart`, `PlanningObjectionsPanel`,
   `DissentProfilesChart`, `DissentCoalitionsPanel` — genuinely unwired.
   But **`TrendsChart.tsx` is live**: `registry/components.tsx:16` imports
   `ContestationChart` *from* `../components/TrendsChart`, registered
   under `governance.unanimity_trend` — the file is in active use, just
   under a different exported name than its filename suggests.
3. **`docs/agent_prompts/conductor.txt`** — on disk, but nothing loads it
   (§6). **`investigator/Runner_prompt.txt`** — no live code reference
   (`src/`, `scripts/`, `.github/` all clean); only referenced from other
   docs and historical `INVESTIGATIONS.md` entries, consistent with
   `docs/MAP.md`'s "archived" description.
4. **Two ORM tables are extraction- and profile-only dead ends**:
   `BuildingPermit` and `CommitteeReport` (`src/models/ontology.py:428,371`)
   are referenced only inside `src/analysis/profile.py` (row-counting via
   `_count_via_meeting()`), with zero hits in `queries.py`, `tests.py`,
   `evidence.py`, or any frontend component (see §3 for row counts —
   847 and 911 rows respectively, i.e. populated, just analytically
   unused). The `relationships` table is similarly write-only (§3).
5. **`scripts/dryrun_scraper.py`** — genuinely orphaned: contains a
   hardcoded absolute path
   (`sys.path.insert(0, "/Users/josef/Projects/council-ontology/src")`),
   self-describes as a one-off fix-verification script, zero references
   anywhere else in the repo. Every other apparently-unwired script
   (`extract_wa_elections.py`, `generate_placeholder_data.py`,
   `seed_test_registry.py`, `measure_private_name_patterns.py`,
   `run_state.py`, `check_no_hardcoded_content.py`, `audit_report.py`,
   `wayback_gap_fill.py`, `scraper_audit.py`, `geocode_sites.py`,
   `build_boundaries.py`, `archive_import.py`) turned out to be either a
   documented one-off importer, a CI-invoked script
   (`check_no_hardcoded_content.py` at `.github/workflows/ci.yml:34`), a
   workflow-invoked script (`run_state.py`), or dynamically imported inside
   `src/cli.py` via `from scripts.X import ...` (e.g. `cli.py:5248,5222,
   5204,5182,5158,318`).
6. **Two independent PDF-to-text implementations** with opposite
   pypdf/fitz try-order — `src/extraction/extractor.py:93-116` (fitz
   first) and `src/cli.py:40-64` (pypdf first, subprocess-isolated). Both
   flatten to a single string with no page metadata (§2). Whether this
   divergent duplication is intentional (subprocess isolation needs its
   own minimal-import copy) or accidental drift was not determined in this
   pass.
7. **Loose top-level files**: `cost_report.txt`, `prompt_notes.txt` — no
   reference found anywhere in `src/`, `scripts/`, `docs/`, or
   `README.md`; appear to be scratch/output files not read by any code.
   `council_ontology_article.pages`/`.pdf` — a personal write-up artefact,
   unrelated to the codebase. `.cache/llm_responses/` is live (read by
   `scripts/inventory.py` as the inventory-call cache). `notebooks/` is
   empty.

**INVESTIGATE** (carried over from the forks, not resolved in this pass):
- Whether `sites` has address-level de-duplication (§3).
- Whether `cost_report.txt`/`prompt_notes.txt` are silently regenerated by
  an untracked script.
- Whether `BuildingPermit`/`CommitteeReport`'s near-total analytical
  disuse reflects sparse row counts (it does not — 847/911 rows, see §3 —
  so the more precise framing is "populated but never built on," not
  "sparse").
