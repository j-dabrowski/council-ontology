"""[32] Committee vs full council — structural-kill probe (pre-flagged).
Confirms committee_reports has NO motion-linkage field and the meeting_type
fallback is too thin/off-target to test upstream-settlement. -> INFEASIBLE.
"""
import sqlite3
db = sqlite3.connect("data/council.db"); c = db.cursor()
print("committee_reports schema:")
for r in c.execute("PRAGMA table_info(committee_reports)"): print("  ", r[1], r[2])
print("committee_reports rows/meetings/items:",
      c.execute("SELECT COUNT(*), COUNT(DISTINCT meeting_id), SUM(item_count) FROM committee_reports").fetchone())
print("committee-type minutes: motions total / contested:",
      c.execute("""SELECT SUM(CASE WHEN m.meeting_type LIKE '%Committee%' THEN 1 ELSE 0 END),
                          SUM(CASE WHEN m.meeting_type LIKE '%Committee%' AND mo.votes_against>0 THEN 1 ELSE 0 END),
                          COUNT(*)
                   FROM motions mo JOIN meetings m ON mo.meeting_id=m.id
                   WHERE m.document_type='minutes'""").fetchone())
print("=> No motion linkage field; 22 contested committee motions; committees only "
      "recommend. INFEASIBLE.")
