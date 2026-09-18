"""
Scraper for the City of Perth (WA) council minutes.

Discovery strategy (confirmed 2026-09-18, SECOND_COUNCIL_PLAN.md 5.2):

  The City of Perth site runs on Sitecore (robots.txt disallows /sitecore,
  /sitecore_files, /sitecore modules) behind Cloudflare's managed JS
  challenge. Every HTML page — including /sitemap.xml — returns
  Cloudflare's "Just a moment..." interstitial (HTTP 403) to a plain HTTP
  client with no browser fingerprint (httpx, curl). This is a different
  CMS (Sitecore, not OpenCities/ASP.NET WebForms) and a different
  bot-protection product (Cloudflare, not Akamai) than Cambridge, so this
  scraper does NOT subclass CambridgeScraper — see base.py's module
  docstring on not forcing reuse that doesn't fit.

  A headless Chromium session (Playwright) passes the challenge — but only
  on a browser context's *first* navigation. Empirically (tested
  2026-09-18): a second `page.goto()` in the same browser context is
  challenged every time regardless of the delay between requests (12s
  still failed), while a brand-new `browser.launch()` + `new_context()`
  per request passes reliably, back-to-back, with no delay needed. So
  discovery here launches one throwaway browser per HTML page fetched,
  rather than reusing a single page/context across the whole crawl the
  way CambridgeScraper's Playwright source does. Slower (a few seconds of
  browser-launch overhead per page) but the only strategy found that
  actually works against this site's protection.

  PDF media assets themselves (under /-/media/...) are NOT behind the
  challenge — a plain httpx GET succeeds (confirmed: curl -I returns 200
  with no browser UA tricks needed) — so only *discovery* (HTML pages)
  needs Playwright; BaseCouncilScraper.download() / run()'s httpx-based
  download loop is unchanged and used as-is. Fair warning for the actual
  extraction session: some of these PDFs are enormous (a single OCM
  agenda or minutes pack was observed at 200-230MB, evidently full-
  resolution scanned attachments) — worth a note in PIPELINE.md's gaps
  when full scraping starts.

  Two listing shapes:

  1. Current year — https://www.perth.wa.gov.au/council/council-meetings
     lists the current year's meetings across two tables ("upcoming" and
     "past this year"), but its Details column only links back to the
     meeting's own subpage (.../council-meetings/<slug>), not the PDFs
     directly — each subpage must be fetched to get the real Agenda/
     Minutes hrefs.
  2. Prior (archived) years — https://www.perth.wa.gov.au/council/
     council-meetings/<year>-meetings (2015-2017) or
     <year>-council-meetings (2018+), paginated via a `?Meetings=N` query
     param (Sitecore SXA pagination) — these DO embed the real PDF hrefs
     directly in the Details column, so no subpage visit is needed once a
     year has been archived off the main listing.

  Filenames already spell "Agenda"/"Minutes" as literal words in the vast
  majority of cases (e.g. "Agenda---OCM---24-February-2026.pdf",
  "20240229---minutes---no-130---city-of-perth.pdf") — base.py's generic
  classify_document_type() already matches these; no MINUTES_SHORTHAND_RE /
  AGENDA_SHORTHAND_RE override is needed.

  Each meeting's Details list also carries non-meeting support docs (audio
  recordings, presentations, registration forms, "Table of Report
  Changes", agenda-briefing-session "Notes" which are workshop notes, not
  formal minutes) labelled distinctly from "Agenda"/"Minutes" in the same
  list. Rather than Cambridge's NOISE_PATTERNS_RE approach (needed because
  its accordion mixes meeting and non-meeting PDFs with no structural
  label), discovery here simply keeps only hrefs classify_document_type()
  resolves to a real type (minutes/agenda/addendum/briefing_notes) and
  drops "unknown" outright — the structured Details list makes the
  keyword/date fallback in is_meeting_document() unnecessary.

Pre-2015 source (added 2026-09-18):

  `_EARLIEST_ARCHIVE_YEAR = 2015` bounds the *live site's* own year-archive
  navigation, not the council's actual history (over a century old; its
  election results alone go back to 1999 — see PIPELINE.md's Perth gaps
  note). Before the current Sitecore CMS, minutes lived at
  perth.wa.gov.au/cou_minutes/ — 404 on the live site now, confirmed by
  hand — but archived by the Wayback Machine. `_discover_wayback_legacy()`
  queries the CDX API for that dead prefix and fetches matches via
  Wayback's `if_` (identity, no UI chrome) endpoint, which is not
  Cloudflare-protected — no Playwright needed for this source. Confirmed
  coverage (checked by hand against actual PDF content, not assumed):
  council-level Ordinary/Special minutes 1996-2006
  (`website_conmins<year>/`, MN/SM prefix), plus five named committees'
  minutes 2005-2007 (`CommitteeMinutes/`) — Design Advisory (da/dac),
  Finance and Budget (fb), Marketing/Sponsorship/International Relations
  (mp/mps). Five more committee-prefix codes (gp, mk, pk, pl, wk) appear
  in the same folder but their sample PDFs had no extractable cover-page
  text to confirm a name against, so they're labelled generically
  ("Committee (XX) — unconfirmed name") rather than guessed.

  A third source, `_discover_documentdb_legacy()`, closes 2007-2013
  (partially — see its own comment above `_DOCUMENTDB_ENTRIES`).

  This is NOT a complete pre-2015 corpus. No working source was found for
  most of 2013 onward or for 2014 — searched (Wayback CDX across that
  whole span, the modern Sitecore path's own Wayback history, the site's
  dead legacy paths) and came up empty, not verified absent. Treat that
  stretch as an open gap, not "nothing exists," per PIPELINE.md's Perth
  gaps note.
"""

import logging
import re
import time
from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup, Tag

from .base import BaseCouncilScraper, MinutesDocument

logger = logging.getLogger(__name__)

BASE_URL = "https://www.perth.wa.gov.au"
LISTING_PATH = "/council/council-meetings"
# Earliest year-archive page confirmed to exist (found via the main
# listing page's own "past years" links, 2026-09-18).
_EARLIEST_ARCHIVE_YEAR = 2015

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# --- Pre-2015 legacy source (module docstring "Pre-2015 source") ----------

_WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"
_LEGACY_URL_PREFIX = "perth.wa.gov.au/cou_minutes/"

# Council-level minutes: .../website_conmins<YEAR>/mn<YYMMDD>...pdf (Ordinary)
# or sm<YYMMDD>...pdf (Special) — both casings of the folder name and of
# the mn/sm prefix appear across years, hence IGNORECASE rather than
# separate patterns.
_LEGACY_COUNCIL_RE = re.compile(r"/(?:website_)?conmins\d{4}/(mn|sm)(\d{2})(\d{2})(\d{2})", re.IGNORECASE)
# Committee minutes: .../CommitteeMinutes/<prefix><YYMMDD>[mins][sp].pdf —
# prefix is 2-3 letters, not always followed by literal "mins" (e.g.
# "mps051129.pdf" has no "mins" at all), so anchor on prefix+date only.
_LEGACY_COMMITTEE_RE = re.compile(r"/CommitteeMinutes/([a-z]{2,3})(\d{2})(\d{2})(\d{2})", re.IGNORECASE)

# Names confirmed 2026-09-18 by reading each committee's own PDF cover
# page via Wayback (title block: "MINUTES / <COMMITTEE NAME> / <date>"),
# or (ldap) a standard WA planning-body acronym spelled out in its own
# filenames ("City of Perth LDAP"). gp/mk/pk/pl/wk/em/ad also appear in
# the legacy sources below but their sample PDFs had no extractable
# cover-page text (image-only pages) — left unnamed rather than guessed;
# see module docstring.
_LEGACY_COMMITTEE_NAMES = {
    "da": "Design Advisory Committee",
    "dac": "Design Advisory Committee",
    "fb": "Finance and Budget Committee",
    "mp": "Marketing, Sponsorship and International Relations Committee",
    "mps": "Marketing, Sponsorship and International Relations Committee",
    "ldap": "Local Development Assessment Panel",
}


def _legacy_year(yy: int) -> int:
    # This legacy archive's confirmed range is 1996-2007 — no century
    # ambiguity: 90-99 -> 19xx, 00-07 -> 20xx.
    return 1900 + yy if yy >= 90 else 2000 + yy


# --- 2007-2013 source: perth.wa.gov.au/documentdb/<id> (added 2026-09-18) --
#
# Between the /cou_minutes/ archive above (dead ~2006/2007) and the
# Sitecore CMS's own year-archive pages (starts 2015), Perth ran a CMS
# that served each document at a flat, sequential-ID URL —
# perth.wa.gov.au/documentdb/<id> — shared across every kind of city
# document, not just council ones (confirmed IDs run 0-3733+ and the vast
# majority are unrelated to Council). Also dead on the live site now.
#
# Two ways these 153 entries were found:
# - **2007-2008 (34 entries, council-level minutes only):** a Wayback
#   snapshot of the site's own "2008 and earlier Council Minutes Archive"
#   page lists these ids directly under explicit year headings — no
#   per-id guessing needed, the archive page itself states the date.
# - **2009-2013 (119 entries, council + committee):** documentdb has no
#   per-council folder or filename convention here — the ID alone means
#   nothing, and finding which IDs are Council minutes/agenda required
#   fetching each candidate's Content-Disposition header via Wayback
#   (~1400 requests, ~15-20 minutes) rather than a single CDX query.
#
# Given that cost and that this is a dead, frozen historical site
# (unlikely to gain new Wayback snapshots), all 153 confirmed results are
# embedded here as a static table rather than re-run live on every
# scrape — the same "REPORTS is a hand-found, hardcoded list" pattern
# scripts/extract_wa_elections.py already uses for the (also frozen)
# Elections WA page indices.
#
# Coverage (checked by hand, 2026-09-18): 2007-01-30 through 2013-02-28.
# The 2007-2008 portion is a complete council-level minutes record (one
# entry per meeting, from the archive page's own listing). The 2009-2013
# portion is scattered — whatever Wayback happened to crawl of a flat
# ~3700-ID space — so treat gaps within that stretch (e.g. very little
# from mid-2012 on) as "not crawled", not "no meeting held". Still no
# source found for the remainder of 2013 or for 2014 — see PIPELINE.md's
# Perth gaps note.
#
# Columns: (documentdb id, Wayback timestamp, meeting date ISO, prefix,
# is_agenda, is_special). Meeting type is derived from prefix via
# _LEGACY_COMMITTEE_NAMES (falling back to a generic "unconfirmed name"
# label) or, for prefix "council", Ordinary/Special Council Meeting per
# is_special. All of these filenames spell "minutes"/"agenda" as literal
# words already, so classify_document_type() labels them correctly with
# no shorthand-regex changes needed.
#
# Reliability note (2026-09-18): the discovery logic and URL construction
# are verified correct (confirmed end-to-end for several entries — real
# PDF bytes downloaded), but a full liveness sweep of all 119 pinned
# (id, timestamp) pairs was not completed — Wayback became unreliable
# under the request volume this investigation had already put through it
# today (most retries came back as connection errors, not real 404s, so
# this is not a measurement of the true failure rate). At least two
# entries are confirmed genuinely gone as of today (ids 1179, 2794 —
# real HTTP 404, not a connection error) and are left in the table rather
# than pruned — BaseCouncilScraper.download() already skips a failed URL
# and logs a warning without aborting the run, so a handful of dead
# entries here is expected, harmless noise, not a bug to chase.
_DOCUMENTDB_ENTRIES: list[tuple[int, str, str, str, bool, bool]] = [
    # 2007-2008: council-level Ordinary/Special minutes only, sourced from a
    # different page than the rest of this table — a Wayback snapshot of
    # "2008 and earlier Council Minutes Archive"
    # (perth.wa.gov.au/web/Council/Council-and-Committee-Meetings/
    # 2008-and-earlier-Council-Minutes-Archive/), which lists these 34
    # documentdb ids directly under explicit "2007"/"2008" headings — no
    # per-id Content-Disposition check needed, since the archive page itself
    # states the date and that it's Council minutes. Timestamps resolved
    # from the same documentdb CDX dump used for the 2009-2013 rows below.
    # No agenda equivalent found on this page (title says "Minutes Archive").
    (621, "20090609132429", "2008-01-29", "council", False, False),  # 29th January
    (647, "20090609132931", "2008-02-19", "council", False, False),  # 19th February
    (682, "20090609133052", "2008-03-11", "council", False, False),  # 11th March
    (720, "20090226222953", "2008-04-01", "council", False, False),  # 1st April
    (754, "20090609133039", "2008-04-22", "council", False, False),  # 22nd April
    (782, "20090609132536", "2008-05-13", "council", False, False),  # 13th May
    (816, "20090609132744", "2008-06-03", "council", False, False),  # 3rd June
    (825, "20090609133700", "2008-06-05", "council", False, True),  # 5th June (special)
    (853, "20090609132516", "2008-06-24", "council", False, False),  # 24th June
    (873, "20090609133304", "2008-07-15", "council", False, False),  # 15th July
    (918, "20090609132417", "2008-08-05", "council", False, False),  # 5th August
    (949, "20090609132635", "2008-08-26", "council", False, False),  # 26th August
    (981, "20090609133230", "2008-09-16", "council", False, False),  # 16th September
    (1007, "20090609132758", "2008-10-07", "council", False, False),  # 7th October
    (1041, "20090609133357", "2008-10-28", "council", False, False),  # 28th October
    (1071, "20090609132319", "2008-11-18", "council", False, False),  # 18th November
    (1099, "20090609133758", "2008-12-16", "council", False, False),  # 16th December
    (363, "20080723051007", "2007-01-30", "council", False, False),  # 30th January
    (362, "20080723050020", "2007-02-20", "council", False, False),  # 20th February
    (361, "20080723050449", "2007-03-13", "council", False, False),  # 13th March
    (360, "20080723050201", "2007-04-03", "council", False, False),  # 3rd April
    (359, "20080723051559", "2007-04-24", "council", False, False),  # 24th April
    (358, "20080723050259", "2007-05-15", "council", False, False),  # 15th May
    (127, "20070831013220", "2007-06-05", "council", False, False),  # 5th June
    (128, "20070831013246", "2007-06-07", "council", False, True),  # 7th June (special)
    (153, "20080723050538", "2007-06-26", "council", False, False),  # 26th June
    (207, "20080723050913", "2007-07-17", "council", False, False),  # 17th July
    (242, "20080723050107", "2007-08-07", "council", False, False),  # 7th August
    (281, "20080723050821", "2007-08-28", "council", False, False),  # 28th August
    (312, "20080723051333", "2007-09-18", "council", False, False),  # 18th September
    (336, "20080723050719", "2007-10-09", "council", False, False),  # 9th October
    (440, "20080723050629", "2007-10-30", "council", False, True),  # 30th October (special)
    (478, "20080723050354", "2007-11-20", "council", False, False),  # 20th November
    (576, "20080723051207", "2007-12-18", "council", False, False),  # 18th December
    # 2009-2013: scattered council + committee docs, found via per-id
    # Content-Disposition checks (module docstring "documentdb id space").
    (1171, "20090917195405", "2009-02-23", "pk", False, False),  # pk_minutes_090223.pdf
    (1173, "20090917195532", "2009-02-24", "mp", False, False),  # mp_minutes_090224.pdf
    (1172, "20091004062701", "2009-02-24", "gp", False, False),  # gp_minutes_090224.pdf
    (1184, "20090917202429", "2009-03-03", "pl", False, False),  # pl_minutes_090303.pdf
    (1183, "20091004214113", "2009-03-03", "fb", False, False),  # fb_minutes_090303.pdf
    (1188, "20090917202315", "2009-03-05", "da", False, False),  # da_minutes_090305.pdf
    (1190, "20090917202945", "2009-03-10", "council", False, False),  # Council_Minutes_090310.pdf
    (1180, "20090917202907", "2009-03-10", "council", True, False),  # Council_Agenda_090310.pdf
    (1179, "20090917203204", "2009-03-10", "council", True, False),  # Council_Agenda_index_090310.pdf
    (1197, "20090917203051", "2009-03-17", "gp", False, False),  # gp_minutes_090317.pdf
    (1187, "20091004214034", "2009-03-17", "gp", True, False),  # gp_agenda_090317.pdf
    (1186, "20091004212929", "2009-03-17", "mp", True, False),  # mp_agenda_090317.pdf
    (1191, "20090917202157", "2009-03-24", "pl", True, False),  # pl_agenda_090324.pdf
    (1319, "20090619100646", "2009-05-19", "mp", False, False),  # mp_minutes_090519.pdf
    (1321, "20090619095859", "2009-06-02", "council", False, False),  # Council_Minutes_090602.pdf
    (1318, "20090619100626", "2009-06-08", "wk", False, False),  # wk_minutes_090608.pdf
    (1314, "20090613181647", "2009-06-08", "pk", False, False),  # pk_minutes_090608.pdf
    (1317, "20090619100424", "2009-06-09", "gp", False, False),  # gp_minutes_090609.pdf
    (1315, "20090613183120", "2009-06-16", "pl", True, False),  # pl_agenda_090616.pdf
    (1339, "20090629141742", "2009-06-16", "fb", False, False),  # fb_minutes_090616.pdf
    (1338, "20090629141720", "2009-06-18", "da", False, False),  # da_minutes_090618.pdf
    (1326, "20090619100446", "2009-06-23", "council", True, False),  # Council_agenda_090623.pdf
    (1342, "20090629141255", "2009-06-30", "mp", True, False),  # mp_agenda_090630.pdf
    (1464, "20090916031941", "2009-09-08", "pl", False, False),  # pl_minutes_090908.pdf
    (1463, "20090916032555", "2009-09-08", "fb", False, False),  # fb_minutes_090908.pdf
    (1468, "20090920205351", "2009-09-22", "gp", True, False),  # gp_agenda_090922.pdf
    (1469, "20090920205430", "2009-09-22", "mp", True, False),  # mp_agenda_090922.pdf
    (1479, "20090930085547", "2009-09-22", "mp", False, False),  # mp_minutes_090922.pdf
    (1480, "20090930085645", "2009-09-22", "gp", False, False),  # gp_minutes_090922.pdf
    (1477, "20110402214414", "2009-09-29", "pl", True, False),  # pl_agenda_090929.pdf
    (1629, "20110303123720", "2010-01-27", "council", False, False),  # Council_Minutes_100127.pdf
    (1648, "20110303124816", "2010-02-16", "council", False, False),  # Council_Minutes_100216.pdf
    (1656, "20110303124957", "2010-02-22", "pk", False, False),  # pk_minutes_100222.pdf
    (1659, "20110303125226", "2010-02-23", "mp", False, False),  # mp_minutes_100223.pdf
    (1654, "20110303125730", "2010-03-02", "pl", True, False),  # pl_agenda_100302.pdf
    (1662, "20110303125859", "2010-03-02", "pk", False, False),  # pk_minutes_100302sp.pdf
    (1668, "20110303125818", "2010-03-02", "pl", False, False),  # pl_minutes_100302.pdf
    (1667, "20110303125631", "2010-03-02", "fb", False, False),  # fb_minutes_100302.pdf
    (1674, "20110303125958", "2010-03-04", "da", False, False),  # da_minutes_100304.pdf
    (1664, "20110303130114", "2010-03-09", "council", True, False),  # Council_agenda_100309.pdf
    (1663, "20110303130039", "2010-03-09", "council", True, False),  # Council_agenda_index_100309.pdf
    (1672, "20110303130456", "2010-03-16", "mp", True, False),  # mp_agenda_100316.pdf
    (1795, "20110303134418", "2010-05-25", "wk", False, False),  # wk_minutes_100525.pdf
    (1800, "20110303134500", "2010-05-27", "da", False, False),  # da_minutes_100527.pdf
    (1818, "20110303134824", "2010-06-01", "council", False, False),  # Council_minutes_100601.pdf
    (1811, "20110303135047", "2010-06-03", "council", False, True),  # Council_Special_Minutes_100603.pdf
    (1805, "20110303135130", "2010-06-08", "mp", True, False),  # mp_agenda_100608.pdf
    (1812, "20110303135412", "2010-06-08", "gp", False, False),  # gp_minutes_100608.pdf
    (1813, "20110303135223", "2010-06-08", "mp", False, False),  # mp_minutes_100608.pdf
    (1815, "20110303135453", "2010-06-09", "pk", False, False),  # pk_minutes_100609.pdf
    (1807, "20110303135738", "2010-06-15", "pl", True, False),  # pl_agenda_100615.pdf
    (1820, "20110303135644", "2010-06-15", "fb", False, False),  # fb_minutes_100615.pdf
    (1822, "20110303140133", "2010-06-22", "council", True, False),  # Council_agenda_100622.pdf
    (1827, "20110303140340", "2010-06-22", "em", False, False),  # em_minutes_100622.pdf
    (1828, "20110303140705", "2010-06-29", "gp", True, False),  # gp_agenda_100629.pdf
    (1830, "20110303140535", "2010-06-29", "mp", True, False),  # mp_agenda_100629.pdf
    (2002, "20110312054759", "2010-09-14", "council", False, False),  # Council_Minutes_100914.pdf
    (1990, "20110312054911", "2010-09-20", "pk", False, False),  # pk_minutes_100920.pdf
    (1996, "20110312055036", "2010-09-20", "wk", False, False),  # wk_minutes_100920.pdf
    (1983, "20110312055349", "2010-09-21", "mp", True, False),  # mp_agenda_100921_schedules.pdf
    (1984, "20110312055607", "2010-09-21", "gp", True, False),  # gp_agenda_100921.pdf
    (1982, "20110312055239", "2010-09-21", "mp", True, False),  # mp_agenda_100921.pdf
    (1985, "20110312055712", "2010-09-21", "gp", True, False),  # gp_agenda_100921_schedules.pdf
    (1989, "20110312055831", "2010-09-21", "gp", False, False),  # gp_minutes_100921.pdf
    (2004, "20110312055458", "2010-09-21", "mp", False, False),  # mp_minutes_100921.pdf
    (1993, "20110312060024", "2010-09-28", "pl", True, False),  # pl_agenda_100928.pdf
    (1994, "20110312060124", "2010-09-28", "pl", True, False),  # pl_agenda_100928_schedules 1.pdf
    (1995, "20110312060240", "2010-09-28", "pl", True, False),  # pl_agenda_100928_schedules 2.pdf
    (2007, "20110312065318", "2010-10-05", "council", True, False),  # Council_agenda_101005.pdf
    (2634, "20120404023221", "2010-11-18", "council", True, True),  # Special Council Meeting agenda 18.11.10.pdf
    (2159, "20110303145310", "2010-12-14", "council", False, False),  # Council_minutes_101214.pdf
    (2181, "20110303145715", "2011-01-17", "wk", False, False),  # wk_minutes_110117.pdf
    (2180, "20110303145638", "2011-01-17", "pk", False, False),  # pk_minutes_110117.pdf
    (2169, "20110303145800", "2011-01-18", "mp", True, False),  # mp_agenda_110118.pdf
    (2170, "20110303145859", "2011-01-18", "mp", True, False),  # mp_agenda_110118_schedules.pdf
    (2172, "20110303150141", "2011-01-18", "gp", True, False),  # gp_agenda_110118_schedules.pdf
    (2171, "20110303150041", "2011-01-18", "gp", True, False),  # gp_agenda_110118.pdf
    (2176, "20110303150418", "2011-01-25", "pl", True, False),  # pl_agenda_110125.pdf
    (2177, "20110303150529", "2011-01-25", "pl", True, False),  # pl_agenda_110125_schedules.pdf
    (2307, "20120324194529", "2011-03-22", "mp", False, False),  # mp_minutes_110322.pdf
    (2304, "20120324210433", "2011-03-29", "fb", False, False),  # fb_minutes_110329.pdf
    (2303, "20120324173306", "2011-03-29", "pl", False, False),  # pl_minutes_110329.pdf
    (2306, "20120324183808", "2011-03-31", "da", False, False),  # da_minutes_110331.pdf
    (2318, "20120324151539", "2011-04-11", "pk", False, False),  # pk_minutes_110411.pdf
    (2308, "20120413035834", "2011-04-12", "mp", True, False),  # mp_agenda_110412.pdf
    (2309, "20120413033824", "2011-04-12", "mp", True, False),  # mp_agenda_110412_schedules.pdf
    (2311, "20120413032932", "2011-04-12", "gp", True, False),  # gp_agenda_110412_schedules.pdf
    (2310, "20120413033807", "2011-04-12", "gp", True, False),  # gp_agenda_110412.pdf
    (2321, "20120324194554", "2011-04-12", "gp", False, False),  # gp_minutes_110412.pdf
    (2316, "20120413033852", "2011-04-19", "pl", True, False),  # pl_agenda_110419.pdf
    (2317, "20120413032326", "2011-04-19", "pl", True, False),  # pl_agenda_110419_schedules.pdf
    (2463, "20120324141115", "2011-07-04", "pk", False, False),  # pk_minutes_110704.pdf
    (2445, "20120408203317", "2011-07-05", "mp", True, False),  # mp_agenda_110705.pdf
    (2468, "20120324174708", "2011-07-05", "gp", False, False),  # gp_minutes_110705.pdf
    (2469, "20120324151510", "2011-07-05", "wk", False, False),  # wk_minutes_110705.pdf
    (2474, "20120324215703", "2011-07-05", "mp", False, False),  # mp_minutes_110705.pdf
    (2464, "20120408204559", "2011-07-12", "pl", True, False),  # pl_agenda_110712.pdf
    (2465, "20120408203437", "2011-07-12", "pl", True, False),  # pl_agenda_110712_schedules.pdf
    (2477, "20120408204352", "2011-07-19", "council", True, False),  # Council_agenda_index_110719.pdf
    (2476, "20120408204332", "2011-07-19", "council", True, False),  # Council_agenda_110719.pdf
    (2617, "20120326034035", "2011-09-20", "council", False, False),  # Council_Minutes_110920.pdf
    (2630, "20120324203951", "2011-09-27", "mp", False, False),  # mp_minutes_110927.pdf
    (2607, "20120404030421", "2011-10-04", "ad", True, False),  # ad_agenda_111004.pdf
    (2627, "20120324230741", "2011-10-04", "fb", False, False),  # fb_minutes_111004.pdf
    (2628, "20120324183750", "2011-10-04", "ad", False, False),  # ad_minutes_111004.pdf
    (2629, "20120324183656", "2011-10-04", "pl", False, False),  # pl_minutes_111004.pdf
    (2635, "20120325003846", "2011-10-06", "da", False, False),  # da_minutes_111006.pdf
    (2621, "20120404023320", "2011-10-11", "council", True, False),  # Council_agenda_111011.pdf
    (2643, "20120404023354", "2011-10-25", "gp", True, False),  # gp_agenda_111025.pdf
    (2644, "20120404022627", "2011-10-25", "gp", True, False),  # gp_agenda_111025_schedules.pdf
    (2645, "20120404025112", "2011-10-25", "mp", True, False),  # mp_agenda_111025.pdf
    (2771, "20120327092801", "2012-01-24", "fb", False, False),  # fb_minutes_120124.pdf
    (2794, "20120327054837", "2012-01-31", "council", False, False),  # Council_Minutes_120131.pdf
    (2784, "20120327042346", "2012-02-14", "pl", True, False),  # pl_agenda_120214_schedules.pdf
    (2798, "20120327023632", "2012-02-21", "council", True, False),  # Council_agenda_120221.pdf
    (2799, "20120327043513", "2012-02-21", "council", True, False),  # Council_agenda_index_120221.pdf
    (3455, "20130423115736", "2012-12-11", "council", False, False),  # Council Minutes 11 December 2012.pdf
    (3446, "20130423051548", "2013-02-28", "ldap", True, False),  # 20130228 - City of Perth LDAP - Agenda - No 8.pdf
    (3481, "20130423051617", "2013-02-28", "ldap", False, False),  # 20130228 - City of Perth LDAP - Minutes - No 8.pdf
]


def _year_archive_slug(year: int) -> str:
    # 2015-2017 use "<year>-meetings"; 2018+ use "<year>-council-meetings"
    # — confirmed by hand from the year-archive links on the main listing
    # page; no documented reason for the split, just a CMS-authoring
    # inconsistency that predates this scraper.
    return f"{year}-meetings" if year <= 2017 else f"{year}-council-meetings"


def _parse_row_date(text: str) -> date | None:
    # Row dates render as "DD Mon YY", e.g. "24 Feb 26".
    try:
        return datetime.strptime(text.strip(), "%d %b %y").date()
    except ValueError:
        return None


def _fetch_html(pw, url: str, attempts: int = 3, wait_s: float = 4.0) -> tuple[str | None, str | None]:
    """Fetch *url*'s rendered HTML past Cloudflare's managed challenge.

    Launches a fresh browser + context for every attempt — see module
    docstring: reusing one context across navigations gets challenged on
    the second request every time, but a brand-new context passes
    reliably. Returns (html, title); (None, None) if every attempt was
    challenged or errored.
    """
    for attempt in range(attempts):
        browser = None
        try:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=_BROWSER_UA,
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            time.sleep(wait_s)
            title = page.title()
            if "Just a moment" in title:
                logger.info("Cloudflare challenge on %s, retrying (%d/%d)", url, attempt + 1, attempts)
            else:
                html = page.content()
                return html, title
        except Exception as exc:  # noqa: BLE001
            logger.warning("fetch failed (%s), attempt %d/%d: %s", url, attempt + 1, attempts, exc)
        finally:
            if browser is not None:
                browser.close()
        time.sleep(2)
    return None, None


def _extract_rows(html: str) -> list[tuple[date, str, str, Tag | None]]:
    """Parse every meeting row out of a listing page's `.page-table`
    component(s). Returns (meeting_date, meeting_type, meeting_page_url,
    details_cell) — `details_cell` is the row's 4th <td> (may or may not
    contain direct PDF links depending on which listing shape this is).
    """
    soup = BeautifulSoup(html, "html.parser")
    rows_out: list[tuple[date, str, str, Tag | None]] = []
    for table in soup.select(".page-table"):
        for tr in table.select("tbody tr"):
            date_cells = tr.select("td.field-meetingdate .tablesaw-cell-content")
            if not date_cells:
                continue
            meeting_date = _parse_row_date(date_cells[0].get_text())
            if meeting_date is None:
                continue
            meeting_link = tr.select_one("td:nth-of-type(3) a[href]")
            if meeting_link is None:
                continue
            meeting_type = meeting_link.get_text(strip=True)
            meeting_page_url = meeting_link["href"]
            if not meeting_page_url.startswith("http"):
                meeting_page_url = BASE_URL + meeting_page_url
            details_cell = tr.select_one("td:nth-of-type(4)")
            rows_out.append((meeting_date, meeting_type, meeting_page_url, details_cell))
    return rows_out


def _pdf_docs_from(
    container: Tag,
    meeting_date: date,
    meeting_type: str,
    classify,
) -> list[MinutesDocument]:
    """Collect MinutesDocuments from every classifiable PDF link under
    *container* (a row's Details cell, or a whole meeting-subpage soup).
    Drops anything classify_document_type() can't positively identify —
    see module docstring on why that's sufficient noise filtering here.
    """
    docs = []
    for a in container.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".pdf"):
            continue
        url = href if href.startswith("http") else BASE_URL + href
        if classify(url) == "unknown":
            continue
        docs.append(
            MinutesDocument(
                council_short_name="perth",
                meeting_date=meeting_date,
                meeting_type=meeting_type,
                source_url=url,
            )
        )
    return docs


class PerthScraper(BaseCouncilScraper):
    """
    Discovers and downloads City of Perth council minutes/agenda PDFs.

    Every HTML page on perth.wa.gov.au is behind Cloudflare's managed
    challenge, so discover() drives its own headless-Chromium fetches
    (one throwaway browser per page — see module docstring) rather than
    the httpx `client` argument `run()` passes in. That client is still
    used, unmodified, for the actual PDF downloads afterward — those are
    not challenge-protected.

    Args:
        since_year: Only include meetings from this year onward. `None`
            includes all archived years back to `_EARLIEST_ARCHIVE_YEAR`.
        request_delay: Seconds to sleep between page fetches. Not needed
            to dodge the Cloudflare challenge itself (a fresh browser
            context handles that), but kept as a polite pacing knob.
    """

    BASE_URL = BASE_URL

    # Legacy (pre-2015) filenames never spell "minutes"/"agenda" as words —
    # e.g. "mn960123.pdf", "da070510mins.pdf", "mps051129.pdf" — so they'd
    # otherwise classify "unknown". No AGENDA_SHORTHAND_RE: the legacy
    # archive has no agenda-equivalent documents at all, only post-meeting
    # minutes, for either council or committee meetings.
    MINUTES_SHORTHAND_RE = re.compile(
        r"^(mn|sm)\d{6}"
        r"|^(da|dac|fb|mp|mps|gp|mk|pk|pl|wk)\d{6}",
        re.IGNORECASE,
    )

    def __init__(
        self,
        since_year: int | None = None,
        request_delay: float = 0.5,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.since_year = since_year
        self.request_delay = request_delay

    @property
    def council_short_name(self) -> str:
        return "perth"

    def discover(self, client: httpx.Client) -> list[MinutesDocument]:  # noqa: C901
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "The Perth scraper requires Playwright "
                "(pip install '.[browser]' && playwright install chromium) — "
                "every HTML page on this site is behind a Cloudflare JS "
                "challenge that a plain HTTP client cannot pass."
            ) from exc

        current_year = date.today().year
        since_year = self.since_year or _EARLIEST_ARCHIVE_YEAR

        docs: list[MinutesDocument] = []
        seen: set[str] = set()

        with sync_playwright() as pw:
            for year in range(current_year, max(since_year, _EARLIEST_ARCHIVE_YEAR) - 1, -1):
                if year == current_year:
                    year_docs = self._discover_current_year(pw)
                else:
                    year_docs = self._discover_archive_year(pw, year)
                for d in year_docs:
                    if d.source_url not in seen:
                        seen.add(d.source_url)
                        docs.append(d)

        # Below _EARLIEST_ARCHIVE_YEAR the live site has nothing (no
        # year-archive page exists) — that's a limit of the current CMS's
        # own navigation, not evidence the council's records start there
        # (PIPELINE.md's Perth gaps note). Two dead-CMS legacy sources,
        # both archived by the Wayback Machine rather than the live site.
        for d in self._discover_wayback_legacy(client, since_year):
            if d.source_url not in seen:
                seen.add(d.source_url)
                docs.append(d)
        for d in self._discover_documentdb_legacy(since_year):
            if d.source_url not in seen:
                seen.add(d.source_url)
                docs.append(d)

        logger.info("Discovered %d minutes/agenda PDFs total", len(docs))
        return docs

    def _discover_current_year(self, pw) -> list[MinutesDocument]:
        """The current year has no archive page yet — its listing page only
        links to each meeting's own subpage, which must be visited to find
        the real PDF hrefs (the listing's own Details column just repeats
        a link back to that subpage, labelled "Agenda & Minutes")."""
        url = BASE_URL + LISTING_PATH
        html, _title = _fetch_html(pw, url)
        if html is None:
            logger.warning("Could not load %s past the Cloudflare challenge", url)
            return []
        rows = _extract_rows(html)
        logger.info("Current-year listing (%d): %d meeting rows", date.today().year, len(rows))

        docs: list[MinutesDocument] = []
        for i, (meeting_date, meeting_type, meeting_page_url, _details) in enumerate(rows):
            if self.request_delay and i:
                time.sleep(self.request_delay)
            sub_html, sub_title = _fetch_html(pw, meeting_page_url)
            if sub_html is None:
                logger.warning("Could not load meeting page %s", meeting_page_url)
                continue
            sub_rows = _extract_rows(sub_html)
            # Meeting subpages don't reuse the listing's .page-table
            # wrapper — their Details list lives under .meeting-wrapper /
            # .meeting-detail-list instead — so fall back to scanning the
            # whole page for classifiable PDF links when no table row
            # shape is found.
            container: Tag = (
                sub_rows[0][3] if (sub_rows and sub_rows[0][3] is not None)
                else BeautifulSoup(sub_html, "html.parser")
            )
            docs.extend(
                _pdf_docs_from(container, meeting_date, meeting_type, self.classify_document_type)
            )
        return docs

    def _discover_archive_year(self, pw, year: int) -> list[MinutesDocument]:
        slug = _year_archive_slug(year)
        url = f"{BASE_URL}{LISTING_PATH}/{slug}"
        html, title = _fetch_html(pw, url)
        if html is None:
            logger.warning("Could not load %s past the Cloudflare challenge", url)
            return []
        if title and "Page not found" in title:
            logger.info("No archive page for %d (%s) — skipping", year, slug)
            return []

        docs: list[MinutesDocument] = list(self._docs_from_year_html(html, year))

        # Pagination: Sitecore SXA numbers pages via ?Meetings=N.
        soup = BeautifulSoup(html, "html.parser")
        page_nums = [
            int(a.get_text(strip=True))
            for a in soup.select("a.sxa-paginationnumber")
            if a.get_text(strip=True).isdigit()
        ]
        max_page = max(page_nums) if page_nums else 1

        for n in range(2, max_page + 1):
            if self.request_delay:
                time.sleep(self.request_delay)
            page_url = f"{url}?Meetings={n}"
            page_html, _t = _fetch_html(pw, page_url)
            if page_html is None:
                logger.warning("Could not load %s", page_url)
                continue
            docs.extend(self._docs_from_year_html(page_html, year))

        return docs

    def _docs_from_year_html(self, html: str, year: int) -> list[MinutesDocument]:
        docs = []
        for meeting_date, meeting_type, _page_url, details_cell in _extract_rows(html):
            if meeting_date.year != year or details_cell is None:
                continue
            docs.extend(
                _pdf_docs_from(details_cell, meeting_date, meeting_type, self.classify_document_type)
            )
        return docs

    def _discover_wayback_legacy(self, client: httpx.Client, since_year: int) -> list[MinutesDocument]:
        """Pre-2015 source — see module docstring "Pre-2015 source".

        Not Cloudflare-protected (Wayback, not perth.wa.gov.au directly),
        so this uses the httpx `client` `discover()` already receives —
        no Playwright browser needed for this source.
        """
        if since_year >= _EARLIEST_ARCHIVE_YEAR:
            return []

        try:
            resp = client.get(
                _WAYBACK_CDX,
                params={
                    "url": _LEGACY_URL_PREFIX,
                    "matchType": "prefix",
                    "output": "json",
                    "collapse": "urlkey",
                    "filter": "mimetype:application/pdf",
                    "limit": "2000",
                },
                timeout=60,
            )
            resp.raise_for_status()
            rows = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Wayback CDX query failed for legacy Perth minutes: %s", exc)
            return []

        data_rows = rows[1:] if rows and rows[0] and rows[0][0] == "urlkey" else rows

        docs: list[MinutesDocument] = []
        for row in data_rows:
            timestamp, original = row[1], row[2]

            m = _LEGACY_COUNCIL_RE.search(original)
            if m:
                kind, yy, mm, dd = m.groups()
                meeting_type = (
                    "Ordinary Council Meeting" if kind.lower() == "mn" else "Special Council Meeting"
                )
            else:
                m = _LEGACY_COMMITTEE_RE.search(original)
                if not m:
                    continue
                prefix, yy, mm, dd = m.groups()
                meeting_type = _LEGACY_COMMITTEE_NAMES.get(
                    prefix.lower(), f"Committee ({prefix.upper()}) — unconfirmed name"
                )

            try:
                meeting_date = date(_legacy_year(int(yy)), int(mm), int(dd))
            except ValueError:
                logger.debug("Unparseable legacy date in %s", original)
                continue
            if meeting_date.year < since_year:
                continue

            docs.append(
                MinutesDocument(
                    council_short_name="perth",
                    meeting_date=meeting_date,
                    meeting_type=meeting_type,
                    source_url=f"https://web.archive.org/web/{timestamp}if_/{original}",
                )
            )

        logger.info(
            "Wayback legacy source: %d Perth minutes/committee PDFs (1996-2007 archive)", len(docs)
        )
        return docs

    def _discover_documentdb_legacy(self, since_year: int) -> list[MinutesDocument]:
        """2007-2013 source — see module docstring "_DOCUMENTDB_ENTRIES"
        comment above. Static table, not a live query — see that comment
        for why. Pure in-memory filtering, no network call at all.

        The documentdb/<id> URL path is a bare number — unlike the other
        two sources, nothing in it spells "minutes"/"agenda", so
        classify_document_type() would call every one of these "unknown".
        Appending a synthesised `#<type>_<date>.pdf` URL fragment fixes
        that: fragments are never sent to the server (confirmed — httpx
        still fetches the right bytes), but classify_document_type() reads
        it as part of the "filename" it inspects, same as a real one
        would. The real original filename (which does vary — e.g.
        "pk_minutes_090223.pdf") is preserved in the _DOCUMENTDB_ENTRIES
        table as an inline comment for anyone auditing this by hand.
        """
        if since_year >= _EARLIEST_ARCHIVE_YEAR:
            return []

        docs: list[MinutesDocument] = []
        for doc_id, timestamp, iso_date, prefix, is_agenda, is_special in _DOCUMENTDB_ENTRIES:
            meeting_date = date.fromisoformat(iso_date)
            if meeting_date.year < since_year:
                continue
            if prefix == "council":
                meeting_type = "Special Council Meeting" if is_special else "Ordinary Council Meeting"
            else:
                meeting_type = _LEGACY_COMMITTEE_NAMES.get(
                    prefix, f"Committee ({prefix.upper()}) — unconfirmed name"
                )
            kind = "agenda" if is_agenda else "minutes"
            fragment = f"{prefix}_{kind}_{iso_date.replace('-', '')}.pdf"
            docs.append(
                MinutesDocument(
                    council_short_name="perth",
                    meeting_date=meeting_date,
                    meeting_type=meeting_type,
                    source_url=(
                        f"https://web.archive.org/web/{timestamp}if_/"
                        f"http://www.perth.wa.gov.au/documentdb/{doc_id}#{fragment}"
                    ),
                )
            )

        logger.info("documentdb legacy source: %d Perth minutes/agenda PDFs (2007-2013, partial)", len(docs))
        return docs
