"""[37] Public-question responsiveness — answered, or quietly 'taken on notice'?
Schema CONFIRMED viable (response_summary 93% populated). Classify each question's
response as answered-in-meeting vs taken-on-notice/deferred vs blank; trend by year
with Inquiry shock; coverage-normalise. Validate against extraction_evidence.
"""
import sqlite3, re
db = sqlite3.connect("data/council.db"); c = db.cursor()

rows = c.execute("""
  SELECT CAST(strftime('%Y', m.meeting_date) AS INT) y, COALESCE(pq.response_summary,'')
  FROM public_questions pq JOIN meetings m ON pq.meeting_id=m.id
  WHERE m.document_type='minutes'
""").fetchall()

TON = re.compile(r'taken on notice|on notice|will be provided|to be provided|provided later|'
                 r'response.*(later|subsequent)|no response|not answered|deferred|'
                 r'will respond|responded to in writing|provide.*writing|answer.*writing', re.I)

def classify(resp):
    r=resp.strip()
    if not r: return "blank"
    if TON.search(r): return "on_notice"
    return "answered"

from collections import defaultdict
by_year=defaultdict(lambda:{"answered":0,"on_notice":0,"blank":0})
tot={"answered":0,"on_notice":0,"blank":0}
for y,resp in rows:
    c2=classify(resp); by_year[y][c2]+=1; tot[c2]+=1

N=len(rows)
print(f"total public questions (minutes): {N}")
for k in ("answered","on_notice","blank"):
    print(f"  {k:10s} {tot[k]:5d}  ({tot[k]/N*100:.1f}%)")

def era(y): return "pre-2018" if y<2018 else ("inquiry" if y<=2021 else "post-2022")
eagg=defaultdict(lambda:{"answered":0,"on_notice":0,"blank":0})
for y,resp in rows: eagg[era(y)][classify(resp)]+=1
print("\n=== by era: on-notice share (of non-blank) ===")
for e in ("pre-2018","inquiry","post-2022"):
    v=eagg[e]; nonblank=v["answered"]+v["on_notice"]
    print(f"  {e:10s} answered={v['answered']:4d} on_notice={v['on_notice']:3d} blank={v['blank']:3d}  "
          f"on-notice%={v['on_notice']/nonblank*100 if nonblank else 0:4.1f}%")

print("\n=== year trend (on-notice share of non-blank) ===")
for y in sorted(by_year):
    v=by_year[y]; nb=v["answered"]+v["on_notice"]
    if nb==0: continue
    print(f"  {y}  n={nb+v['blank']:4d}  on-notice={v['on_notice']/nb*100:4.1f}%  blank={v['blank']}")
