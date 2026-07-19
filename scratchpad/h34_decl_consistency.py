"""[34] Declaration consistency — does a councillor who declares on a matter declare
EVERY time it recurs? The 'missing declaration' (absence-is-the-signal) test.
Approach: for each councillor x item_number they EVER declared on, find their later
VOTES on motions with the same item_number where declared_interest=0 (silent).
CONFOUND ([23]): item_number is NOT meeting-unique -> most 'same item' matches are
collisions. Provenance-check every candidate before trusting it.
"""
import sqlite3
db = sqlite3.connect("data/council.db"); c = db.cursor()

# councillor x item_reference they declared on, with the meeting/date + description
decl = c.execute("""
  SELECT d.councillor_id, d.item_reference, d.interest_type, m.meeting_date, d.description, m.id
  FROM interest_declarations d JOIN meetings m ON d.meeting_id=m.id
  WHERE d.councillor_id IS NOT NULL AND d.item_reference IS NOT NULL AND TRIM(d.item_reference)<>''
    AND m.document_type='minutes'
""").fetchall()

from collections import defaultdict
declared_on = defaultdict(list)  # (cid, itemref) -> list of (date, type, desc, meeting_id)
for cid, ref, itype, date, desc, mid in decl:
    declared_on[(cid, ref.strip())].append((date, itype, desc, mid))

# now: for each such (cid, ref), find votes by that councillor on motions with
# item_number == ref, in a DIFFERENT meeting, where declared_interest=0
candidates = []
for (cid, ref), decls in declared_on.items():
    decl_meetings = {mid for _,_,_,mid in decls}
    rows = c.execute("""
      SELECT mo.id, mo.item_number, mo.title, m.meeting_date, v.declared_interest, m.id
      FROM votes v JOIN motions mo ON v.motion_id=mo.id JOIN meetings m ON mo.meeting_id=m.id
      WHERE v.councillor_id=? AND mo.item_number=? AND m.document_type='minutes'
    """,(cid, ref)).fetchall()
    for moid, itemn, title, date, di, mid in rows:
        if mid not in decl_meetings and not di:
            candidates.append((cid, ref, moid, title, date, decls))

print(f"declared (cid,item_ref) pairs: {len(declared_on)}")
print(f"candidate SILENT recurrences (voted on same item_number in another meeting, no declaration): {len(candidates)}")

# name lookup
names=dict(c.execute("SELECT id, given_name||' '||family_name FROM councillors"))

# show first 12 candidates with the declaration context to judge same-matter
print("\n=== candidates (judge if same MATTER or item_number collision) ===")
for cid, ref, moid, title, date, decls in candidates[:12]:
    dtypes = {d[1] for d in decls}
    ddesc = decls[0][2][:50] if decls[0][2] else ""
    print(f"\n{names.get(cid,cid)} | item {ref} | silent vote {date[:10]}: {(title or '')[:55]}")
    print(f"   had declared ({','.join(dtypes)}) on: {ddesc}")
