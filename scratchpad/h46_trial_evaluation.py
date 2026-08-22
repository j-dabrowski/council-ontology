"""
H46 [Genre F — Effectiveness/3.5]: Are declared trials/pilots in Cambridge
minutes evaluated against their own stated purpose before being made
permanent, discontinued, or silently left to lapse?

Approach: pull every 'minutes' motion whose title contains trial/pilot
(case-insensitive), then for each, search ALL later motions (any table,
any date after) for a keyword overlap (shared distinctive word from the
trial's title, ignoring stopwords) combined with an evaluation-language
hit (review/outcome/report/evaluation/assessment/final/permanent/
discontinu/extend/lapse) within a 5-year window. This is a coarse proxy
(word-overlap, not semantic), so results are hand-checked below, not
taken as ground truth alone.
"""
import re
import sqlite3
from collections import defaultdict

STOPWORDS = {
    "the", "a", "an", "of", "and", "to", "in", "for", "at", "on", "by",
    "trial", "pilot", "project", "town", "cambridge", "council", "proposed",
    "approval", "approved", "deferred", "referral", "amendment", "final",
    "motion", "as", "carried", "lost", "with", "from",
}
EVAL_KEYWORDS = [
    "review", "outcome", "report", "evaluation", "evaluat", "assessment",
    "final", "permanent", "discontinu", "extend", "extension", "lapse",
    "cease", "results", "finalisation", "finalization",
]

conn = sqlite3.connect("data/council.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

trials = cur.execute(
    """
    SELECT mo.id, m.meeting_date, mo.title, mo.motion_text
    FROM motions mo JOIN meetings m ON m.id = mo.meeting_id
    WHERE m.document_type='minutes'
      AND (mo.title LIKE '%trial%' OR mo.title LIKE '%pilot%')
    ORDER BY m.meeting_date
    """
).fetchall()

all_motions = cur.execute(
    """
    SELECT mo.id, m.meeting_date, mo.title
    FROM motions mo JOIN meetings m ON m.id = mo.meeting_id
    WHERE m.document_type='minutes'
    ORDER BY m.meeting_date
    """
).fetchall()

def keywords(title):
    words = re.findall(r"[a-zA-Z]+", title.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 3}

def has_eval_language(title):
    t = title.lower()
    return any(k in t for k in EVAL_KEYWORDS)

results = []
for t in trials:
    kws = keywords(t["title"])
    t_date = t["meeting_date"]
    followups = []
    for m in all_motions:
        if m["id"] == t["id"]:
            continue
        if m["meeting_date"] <= t_date:
            continue
        # within 5 years
        y_gap = (int(m["meeting_date"][:4]) - int(t_date[:4]))
        if y_gap > 5:
            continue
        mkws = keywords(m["title"])
        overlap = kws & mkws
        if overlap and has_eval_language(m["title"]):
            followups.append((m["meeting_date"], m["title"], sorted(overlap)))
    results.append((t["meeting_date"], t["title"], followups))

n_with_followup = sum(1 for r in results if r[2])
print(f"Trial/pilot motions found: {len(results)}")
print(f"With a keyword-overlap + eval-language followup within 5yrs: {n_with_followup}")
print(f"Without any such followup: {len(results) - n_with_followup}\n")

for date, title, followups in results:
    tag = "FOLLOWUP" if followups else "NO-FOLLOWUP-FOUND"
    print(f"[{tag}] {date}  {title}")
    for fdate, ftitle, overlap in followups:
        print(f"          -> {fdate}  {ftitle}   (overlap: {overlap})")
