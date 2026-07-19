"""[35] Are conflicts declared when Council awards tenders, and do winners match
declared councillor connections? Part 3.3 decider x supplier join.
(1) declaration rate on tender-award motions vs chamber base rate.
(2) name-match tenders.awarded_to (457 named, 45.6% NULL excluded) vs councillor
    surnames -> flag decider<->winner pairs with no declaration on the award vote.
Restrict match to NAMED awards; NULL winner = extraction gap, NOT concealment.
"""
import sqlite3, re
db = sqlite3.connect("data/council.db"); c = db.cursor()

# base declaration rate across all votes (minutes)
base = c.execute("""SELECT AVG(CASE WHEN v.declared_interest THEN 1.0 ELSE 0 END)
  FROM votes v JOIN motions mo ON v.motion_id=mo.id JOIN meetings m ON mo.meeting_id=m.id
  WHERE m.document_type='minutes'""").fetchone()[0]

# identify tender-award motions by title/text
tender_motions = c.execute("""
  SELECT mo.id FROM motions mo JOIN meetings m ON mo.meeting_id=m.id
  WHERE m.document_type='minutes' AND (
    lower(mo.title) LIKE '%tender%' OR lower(mo.title) LIKE '% rft %' OR lower(mo.title) LIKE 'rft %'
    OR lower(mo.title) LIKE '%contract%award%' OR lower(mo.motion_text) LIKE '%accept the tender%'
    OR lower(mo.motion_text) LIKE '%awards%contract%' OR lower(mo.motion_text) LIKE '%rft %')
""").fetchall()
tm_ids = [r[0] for r in tender_motions]
print(f"tender-award motions identified: {len(tm_ids)}")

if tm_ids:
    qmarks=",".join("?"*len(tm_ids))
    votes_on_tm = c.execute(f"""SELECT COUNT(*), SUM(CASE WHEN declared_interest THEN 1 ELSE 0 END)
        FROM votes WHERE motion_id IN ({qmarks})""", tm_ids).fetchone()
    nv, nd = votes_on_tm[0], votes_on_tm[1] or 0
    print(f"votes on tender-award motions: {nv}; with declaration: {nd} ({nd/nv*100:.2f}%)")
    print(f"chamber base declaration rate: {base*100:.2f}%")

# Part 2: name-match awarded_to vs councillor surnames
councillor_surnames = c.execute("""
  SELECT DISTINCT family_name, id, given_name||' '||family_name FROM councillors
  WHERE family_name IS NOT NULL AND LENGTH(family_name)>=4
    AND id IN (SELECT DISTINCT councillor_id FROM votes)""").fetchall()
awards = c.execute("""SELECT t.id, t.awarded_to, t.amount FROM tenders t JOIN meetings m ON t.meeting_id=m.id
  WHERE m.document_type='minutes' AND t.awarded_to IS NOT NULL AND TRIM(t.awarded_to)<>''
    AND t.awarded_to NOT LIKE 'Respondent%'""").fetchall()
print(f"\nnamed non-Respondent awards: {len(awards)}; real-councillor surnames tested: {len(councillor_surnames)}")

hits=[]
for tid, firm, amt in awards:
    fl=firm.lower()
    for surname, cid, cname in councillor_surnames:
        s=surname.lower().strip()
        if re.search(r'\b'+re.escape(s)+r'\b', fl):
            hits.append((firm, amt, cname, surname))
print(f"surname-in-firm matches (RAW, expect mostly false positives on common surnames): {len(hits)}")
for firm, amt, cname, surname in hits[:20]:
    print(f"   '{firm}' (${amt}) ~ {cname} [{surname}]")
