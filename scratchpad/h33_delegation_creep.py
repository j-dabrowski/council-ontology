"""[33] Delegation creep — is decision-making drifting out of the elected chamber?
delegated_decisions share vs council motions over years. CRITICAL confound check:
is delegated_decisions EXTRACTION COVERAGE stable across eras, or does it grow
(manufacturing a spurious rise)? Coverage-normalise; Inquiry as shock boundary.
"""
import sqlite3
db = sqlite3.connect("data/council.db"); c = db.cursor()

# delegated_decisions per year (minutes only)
dd = dict(c.execute("""
  SELECT CAST(strftime('%Y', m.meeting_date) AS INT) y, COUNT(*)
  FROM delegated_decisions d JOIN meetings m ON d.meeting_id=m.id
  WHERE m.document_type='minutes' GROUP BY y"""))
# council motions per year (denominator)
mo = dict(c.execute("""
  SELECT CAST(strftime('%Y', m.meeting_date) AS INT) y, COUNT(*)
  FROM motions x JOIN meetings m ON x.meeting_id=m.id
  WHERE m.document_type='minutes' GROUP BY y"""))
# minutes meetings per year (coverage denominator)
mtg = dict(c.execute("""
  SELECT CAST(strftime('%Y', meeting_date) AS INT) y, COUNT(*)
  FROM meetings WHERE document_type='minutes' GROUP BY y"""))
# how many meetings CONTAIN >=1 delegated_decision (coverage proxy)
mtg_with_dd = dict(c.execute("""
  SELECT y, COUNT(*) FROM (
    SELECT CAST(strftime('%Y', m.meeting_date) AS INT) y, m.id
    FROM meetings m JOIN delegated_decisions d ON d.meeting_id=m.id
    WHERE m.document_type='minutes' GROUP BY m.id
  ) GROUP BY y"""))

print(f"{'yr':4s}{'delegated':>10s}{'motions':>9s}{'dd/mot%':>9s}{'meetings':>9s}{'mtgWdd':>7s}{'cover%':>8s}")
years=sorted(set(list(dd)+list(mo)))
for y in years:
    d=dd.get(y,0); m_=mo.get(y,0); t=mtg.get(y,0); tw=mtg_with_dd.get(y,0)
    share=d/m_*100 if m_ else 0
    cover=tw/t*100 if t else 0
    print(f"{y:4d}{d:10d}{m_:9d}{share:9.1f}{t:9d}{tw:7d}{cover:8.0f}")

# era summary
def era(y): return "pre-2018" if y<2018 else ("inquiry" if y<=2021 else "post-2022")
agg={}
for y in years:
    e=era(y); agg.setdefault(e,{"dd":0,"mo":0,"mtg":0,"mtgdd":0})
    agg[e]["dd"]+=dd.get(y,0); agg[e]["mo"]+=mo.get(y,0)
    agg[e]["mtg"]+=mtg.get(y,0); agg[e]["mtgdd"]+=mtg_with_dd.get(y,0)
print("\n=== by era ===")
for e,v in agg.items():
    print(f"  {e:10s} delegated={v['dd']:4d}  motions={v['mo']:5d}  dd/mot={v['dd']/v['mo']*100 if v['mo'] else 0:4.1f}%  "
          f"meeting-coverage={v['mtgdd']/v['mtg']*100 if v['mtg'] else 0:3.0f}% ({v['mtgdd']}/{v['mtg']} meetings list any delegated)")
