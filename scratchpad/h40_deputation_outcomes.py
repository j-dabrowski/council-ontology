"""[40] Engagement that moves outcomes — do deputations visibly flip a decision?
Link each deputation to its item via the item code embedded in topic ('Item DV12.31 ...')
-> motions.item_number in the SAME meeting. Compare deputation-items' outcomes to the
base rate, CONTROLLING for contentiousness ([3] confound: deputations are drawn to
already-contentious items). Small n of clear flips -> directional/illustrative.
"""
import sqlite3, re
db = sqlite3.connect("data/council.db"); c = db.cursor()

# extract item code from deputation topic
dep = c.execute("""SELECT d.meeting_id, d.topic FROM deputations d JOIN meetings m ON d.meeting_id=m.id
                   WHERE m.document_type='minutes' AND d.topic IS NOT NULL""").fetchall()
CODE=re.compile(r'\b((?:DV|CR|CCS|OCM|DA|CDS|PD|EP)\s?\d{1,2}[.\-/]\d{1,3}(?:\.\d+)?)', re.I)
def code_of(topic):
    m=CODE.search(topic.replace(' ',''))  # tolerate 'DV 12.31'
    if m: return m.group(1).upper().replace(' ','')
    m2=re.search(r'item\s+([A-Z0-9.\-/]+)', topic, re.I)
    return m2.group(1).upper() if m2 else None

dep_items=set()  # (meeting_id, item_number)
for mid, topic in dep:
    cd=code_of(topic)
    if cd: dep_items.add((mid, cd))
print(f"deputations: {len(dep)}; with an extractable item code: {len(dep_items)} distinct (meeting,item)")

# all motions with outcome + contentiousness, keyed (meeting_id, item_number)
mo = c.execute("""SELECT m.id, UPPER(REPLACE(mo.item_number,' ','')), mo.outcome, mo.votes_against, mo.title
  FROM motions mo JOIN meetings m ON mo.meeting_id=m.id
  WHERE m.document_type='minutes' AND mo.item_number IS NOT NULL""").fetchall()

def bucket(o):
    return "diverted" if o in ('DEFERRED','LOST','WITHDRAWN','LAPSED') else ("CARRIED" if o=='CARRIED' else "other")

dep_key=dep_items
matched=0
dep_out={"CARRIED":0,"diverted":0,"other":0}
nondep_out={"CARRIED":0,"diverted":0,"other":0}
dep_contested_out={"CARRIED":0,"diverted":0}
nondep_contested_out={"CARRIED":0,"diverted":0}
examples=[]
for mid, itemn, outcome, va, title in mo:
    is_dep=(mid, itemn) in dep_key
    b=bucket(outcome)
    if is_dep:
        matched+=1; dep_out[b]+=1
        if (va or 0)>0 and b in ("CARRIED","diverted"): dep_contested_out[b]+=1
        if b=="diverted" and len(examples)<10: examples.append((itemn, outcome, va, (title or '')[:45]))
    else:
        nondep_out[b]+=1
        if (va or 0)>0 and b in ("CARRIED","diverted"): nondep_contested_out[b]+=1

print(f"deputation items matched to a motion: {matched}")
def rate(d):
    t=d["CARRIED"]+d["diverted"]+d.get("other",0);
    return d["diverted"]/t*100 if t else 0
print(f"\nALL items:")
print(f"  deputation items  : diverted(deferred/lost/withdrawn)={dep_out['diverted']}  carried={dep_out['CARRIED']}  -> divert%={rate(dep_out):.1f}")
print(f"  non-deputation    : diverted={nondep_out['diverted']}  carried={nondep_out['CARRIED']}  -> divert%={rate(nondep_out):.1f}")
def crate(d):
    t=d["CARRIED"]+d["diverted"]; return d["diverted"]/t*100 if t else 0
print(f"\nCONTESTED items only (votes_against>0) — controls the [3] confound:")
print(f"  deputation contested: diverted={dep_contested_out['diverted']} carried={dep_contested_out['CARRIED']} -> divert%={crate(dep_contested_out):.1f}")
print(f"  non-dep contested   : diverted={nondep_contested_out['diverted']} carried={nondep_contested_out['CARRIED']} -> divert%={crate(nondep_contested_out):.1f}")
print("\n=== sample deputation items that diverted ===")
for itemn, outcome, va, title in examples:
    print(f"  {itemn} {outcome} (against={va}) {title}")
