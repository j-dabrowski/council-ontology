"""[38] Petitions that vanish — does a petition ever produce a traceable outcome?
Link petition.subject -> later motions on the same matter via distinctive-term overlap.
Expected (per hypothesis): thin free-text linkage, likely a data-linkage null.
'Received and noted' is often the lawful correct disposition -> absence of a follow-up
motion is NOT itself abuse.
"""
import sqlite3, re
db = sqlite3.connect("data/council.db"); c = db.cursor()

petitions = c.execute("""
  SELECT p.id, p.subject, m.meeting_date, m.id, p.signatory_count
  FROM petitions p JOIN meetings m ON p.meeting_id=m.id
  WHERE m.document_type='minutes' AND p.subject IS NOT NULL AND TRIM(p.subject)<>''
""").fetchall()
print(f"petitions with a subject (minutes): {len(petitions)}")

STOP=set("the a an of in to for and or on at by with new project access safe active "
         "street road avenue terrace park path footpath area proposed request petition "
         "city town cambridge development".split())
def keyterms(subj):
    words=re.findall(r"[A-Za-z]{4,}", subj.lower())
    return [w for w in words if w not in STOP]

# preload all motions with date+text
motions = c.execute("""
  SELECT mo.id, lower(COALESCE(mo.title,'')||' '||COALESCE(mo.motion_text,'')), m.meeting_date, mo.outcome
  FROM motions mo JOIN meetings m ON mo.meeting_id=m.id
  WHERE m.document_type='minutes'
""").fetchall()

linked=0; examples=[]
for pid, subj, pdate, pmid, sig in petitions:
    terms=keyterms(subj)
    if len(terms)<1: continue
    # require >=2 distinctive term hits (or 1 rare term) in a motion at/after petition date
    best=None
    for moid, text, mdate, outcome in motions:
        if mdate < pdate: continue
        hits=sum(1 for t in set(terms) if re.search(r'\b'+re.escape(t)+r'\b', text))
        if hits>=2:
            best=(moid, mdate, outcome, hits); break
    if best:
        linked+=1
        if len(examples)<10: examples.append((subj[:45], best[1][:10], best[2], best[3]))

print(f"petitions with >=1 later motion sharing >=2 distinctive terms: {linked} ({linked/len(petitions)*100:.1f}%)")
print("\n=== sample links (judge if genuine same-matter) ===")
for subj, mdate, outcome, hits in examples:
    print(f"  '{subj}' -> motion {mdate} ({outcome}) [{hits} term hits]")
