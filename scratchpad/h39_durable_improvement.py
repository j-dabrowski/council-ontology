"""[39] Durable-improvement hunt — did ANY conduct tighten during the 2018-21 Inquiry
and HOLD afterward (L-shape), vs dip-and-rebound / reversion (V-shape)?
Sweep before/during/after across the era series. Require >=2 solid post-Inquiry years
before claiming 'held' (2022-2023 corpus gap thins the 'after' window).
"""
import sqlite3
db = sqlite3.connect("data/council.db"); c = db.cursor()
def era(y): return "pre" if y<2018 else ("inq" if y<=2021 else "post")

def show(name, pre, inq, post, better="down", npre="", ninq="", npost=""):
    # 'better' = direction that means IMPROVEMENT
    improved_during = (inq<pre) if better=="down" else (inq>pre)
    held = (post<=pre*1.05 if better=="down" else post>=pre*0.95) and (
            (post<=inq*1.15) if better=="down" else (post>=inq*0.85))
    # L-shape = improved during AND held; V = improved during but reverted
    if improved_during and (post<inq if better=="down" else post>inq) is False and held:
        shape="L (durable)" if held else "?"
    shape = "L-DURABLE" if (improved_during and held) else ("V-REVERT" if improved_during else "no-improve")
    print(f"{name:34s} pre={pre:6.1f}{npre}  inq={inq:6.1f}{ninq}  post={post:6.1f}{npost}  [{shape}] (better={better})")

# 1. contestation rate (share of carried motions with >=1 against) — openness of dissent
rows=c.execute("""SELECT CAST(strftime('%Y',m.meeting_date) AS INT) y, mo.outcome, mo.votes_against
  FROM motions mo JOIN meetings m ON mo.meeting_id=m.id WHERE m.document_type='minutes'""").fetchall()
from collections import defaultdict
agg=defaultdict(lambda:[0,0])
for y,o,va in rows:
    if o!='CARRIED': continue
    e=era(y); agg[e][0]+= (1 if (va or 0)>0 else 0); agg[e][1]+=1
show("contestation% (dissent openness)", *[agg[e][0]/agg[e][1]*100 for e in ("pre","inq","post")], better="up",
     npre=f"(n={agg['pre'][1]})", ninq=f"(n={agg['inq'][1]})", npost=f"(n={agg['post'][1]})")

# 2. confidential share (3 tables)
def conf_share():
    out={}
    for e in ("pre","inq","post"): out[e]=[0,0]
    for tbl in ("tenders","other_items","delegated_decisions"):
        for y,ic in c.execute(f"""SELECT CAST(strftime('%Y',m.meeting_date) AS INT) y, x.is_confidential
              FROM {tbl} x JOIN meetings m ON x.meeting_id=m.id WHERE m.document_type='minutes'"""):
            e=era(y); out[e][0]+= (1 if ic else 0); out[e][1]+=1
    return out
cs=conf_share()
show("confidential item share", *[cs[e][0]/cs[e][1]*100 for e in ("pre","inq","post")], better="down")

# 3. recusal on must-leave (financial+proximity) conflicts — vote-level
rows=c.execute("""SELECT CAST(strftime('%Y',m.meeting_date) AS INT) y, v.choice, v.declared_interest,
     id.interest_type
  FROM votes v JOIN motions mo ON v.motion_id=mo.id JOIN meetings m ON mo.meeting_id=m.id
  LEFT JOIN interest_declarations id ON id.meeting_id=m.id AND id.councillor_id=v.councillor_id
     AND id.item_reference=mo.item_number
  WHERE m.document_type='minutes' AND v.declared_interest=1""").fetchall()
rec=defaultdict(lambda:[0,0])
seen=set()
for y,choice,di,itype in rows:
    if itype in ('FINANCIAL','PROXIMITY'):
        e=era(y); rec[e][0]+= (1 if choice=='ABSENT' else 0); rec[e][1]+=1
show("recusal% on must-leave [19]", *[rec[e][0]/rec[e][1]*100 if rec[e][1] else 0 for e in ("pre","inq","post")],
     better="up", npre=f"(n={rec['pre'][1]})", ninq=f"(n={rec['inq'][1]})", npost=f"(n={rec['post'][1]})")

# 4. public-Q on-notice rate [37] (better = down = more answered live)
import re
TON=re.compile(r'taken on notice|on notice|no response|not answered|deferred|in writing|to be provided|provided later',re.I)
on=defaultdict(lambda:[0,0])
for y,resp in c.execute("""SELECT CAST(strftime('%Y',m.meeting_date) AS INT) y, COALESCE(pq.response_summary,'')
      FROM public_questions pq JOIN meetings m ON pq.meeting_id=m.id WHERE m.document_type='minutes'"""):
    if not resp.strip(): continue
    e=era(y); on[e][0]+= (1 if TON.search(resp) else 0); on[e][1]+=1
show("public-Q on-notice% [37]", *[on[e][0]/on[e][1]*100 for e in ("pre","inq","post")], better="down")

# 5. declared-interest share of all votes (disclosure propensity; better=up=more disclosure)
dv=defaultdict(lambda:[0,0])
for y,di in c.execute("""SELECT CAST(strftime('%Y',m.meeting_date) AS INT) y, v.declared_interest
      FROM votes v JOIN motions mo ON v.motion_id=mo.id JOIN meetings m ON mo.meeting_id=m.id
      WHERE m.document_type='minutes'"""):
    e=era(y); dv[e][0]+= (1 if di else 0); dv[e][1]+=1
show("declared-interest share of votes", *[dv[e][0]/dv[e][1]*100 for e in ("pre","inq","post")], better="up")
