"""[31] Genuine absenteeism vs recusal — decompose each councillor's ABSENT rate.
Partition ABSENT votes by whether the councillor declared an interest on THAT
motion (vote-level declared_interest flag, per motion x councillor by UNIQUE
constraint — NOT the item_reference join, per [23] caveat). Filter to real voting
councillors (exclude the 197 zero-vote placeholders automatically: they have no votes).
"""
import sqlite3
db = sqlite3.connect("data/council.db"); c = db.cursor()

# every vote in minutes: councillor, choice, declared_interest
rows = c.execute("""
  SELECT v.councillor_id, v.choice, v.declared_interest,
         cl.given_name || ' ' || cl.family_name AS name
  FROM votes v
  JOIN motions mo ON v.motion_id=mo.id
  JOIN meetings m ON mo.meeting_id=m.id
  JOIN councillors cl ON v.councillor_id=cl.id
  WHERE m.document_type='minutes'
""").fetchall()

from collections import defaultdict
tot=defaultdict(int); absent=defaultdict(int); absent_decl=defaultdict(int); absent_nodecl=defaultdict(int)
names={}
for cid,choice,decl,name in rows:
    tot[cid]+=1; names[cid]=name
    if choice=='ABSENT':
        absent[cid]+=1
        if decl: absent_decl[cid]+=1
        else: absent_nodecl[cid]+=1

# overall
tot_v=sum(tot.values()); tot_abs=sum(absent.values())
tot_abs_decl=sum(absent_decl.values()); tot_abs_nodecl=sum(absent_nodecl.values())
print(f"OVERALL: {tot_v} votes, {tot_abs} ABSENT ({tot_abs/tot_v*100:.1f}%)")
print(f"  of ABSENT: {tot_abs_decl} recusal (declared) = {tot_abs_decl/tot_abs*100:.0f}%; "
      f"{tot_abs_nodecl} genuine-absence (no declaration) = {tot_abs_nodecl/tot_abs*100:.0f}%")

# per-councillor, min 100 votes; rank by the TWO components separately
elig=[cid for cid in tot if tot[cid]>=100]
print(f"\n=== Councillors with >=100 votes (n={len(elig)}) — ABSENT decomposition ===")
print(f"{'name':22s}{'votes':>6s}{'abs%':>6s}{'recus%':>7s}{'genAbs%':>8s}")
for cid in sorted(elig, key=lambda x: -absent[x]/tot[x]):
    v=tot[cid]; a=absent[cid]
    print(f"{names[cid][:21]:22s}{v:6d}{a/v*100:6.1f}{absent_decl[cid]/v*100:7.2f}{absent_nodecl[cid]/v*100:8.2f}")
