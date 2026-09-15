# Per-council notes — Cambridge

Non-computable caveats about this specific corpus: things `council profile
cambridge` can't derive from the data because they're facts about the
council or its records system, not statistics over rows. `Investigator_
prompt.txt` Part 0.1 points here; add a matching file for any future
council whose corpus has its own such gaps.

- **Council size: ~13 elected members at any time** (Mayor + Councillors,
  ward-based). Relevant for base-rate interpretation — a "3 of 13
  dissented" finding reads differently than the same fraction on a
  30-member council.
- **A CMS migration dropped 2022 Jan–Apr + Jun and 2023 Jan–Apr + Jun–Jul**
  from the online record (confirmed not recoverable, 2026-06-22). Any
  per-year trend crossing 2022–2023 is undercounted for those specific
  months, not evidence of reduced council activity.
  `profile.span.zero_meeting_months_in_span` reproduces the *shape* of
  this (every zero-meeting month in range) directly from the data; this
  note is the *reason* for that specific stretch.
- **Cambridge holds no ordinary council meeting in January** — a
  standing recess, not a gap. A zero-meeting January should never be
  flagged as an anomaly on its own.
- **Vote coverage is uneven across the 1995–2026 span**: sparse in
  1995–2003 (tens–hundreds of votes/year), dense from 2016 on
  (1,000+/year) as record-keeping matured. Don't read the sparse early
  years as low council activity — check `profile.span.meetings_by_year`
  before drawing any early-vs-late comparison.
- **External-scrutiny window: the state-appointed Authorised Inquiry into
  the Town of Cambridge, ~2018–2021** (`config/council_eras.json`'s
  `"cambridge"` entry). Several flagship findings track behaviour tightening
  under that scrutiny and relaxing after — the Part 2.1 "inquiry" frame,
  concrete and datable for this council specifically.
