"""[30] Are CONFIDENTIAL tenders systematically the larger-dollar ones?
Pooled cross-sectional: median/IQR + Mann-Whitney rank-sum, confidential vs open
among tenders WITH an extractable amount. DIRECTIONAL ONLY (n_conf tiny).
Do NOT treat NULL-amount confidential tenders as "the big ones" ([25] trap).
"""
import sqlite3, statistics
db = sqlite3.connect("data/council.db")
c = db.cursor()

rows = c.execute("""
  SELECT t.amount, t.is_confidential
  FROM tenders t JOIN meetings m ON t.meeting_id=m.id
  WHERE m.document_type='minutes' AND t.amount IS NOT NULL AND t.amount>0
""").fetchall()

conf = sorted(a for a,ic in rows if ic==1)
open_ = sorted(a for a,ic in rows if not ic)

# overall missingness context
allconf = c.execute("SELECT COUNT(*) FROM tenders t JOIN meetings m ON t.meeting_id=m.id WHERE m.document_type='minutes' AND t.is_confidential=1").fetchone()[0]
print(f"Confidential tenders (minutes): {allconf}; with extractable amount: {len(conf)} ({len(conf)/allconf*100:.0f}%)")
print(f"Open tenders with amount: {len(open_)}")

def q(xs,p):
    if not xs: return 0
    k=(len(xs)-1)*p; f=int(k); ceil=min(f+1,len(xs)-1)
    return xs[f]+(xs[ceil]-xs[f])*(k-f)

for label,xs in [("CONFIDENTIAL",conf),("OPEN",open_)]:
    if xs:
        print(f"\n{label} n={len(xs)}: median=${statistics.median(xs):,.0f}  "
              f"mean=${statistics.mean(xs):,.0f}  Q1=${q(xs,.25):,.0f}  Q3=${q(xs,.75):,.0f}  max=${max(xs):,.0f}")

# Mann-Whitney U (rank-sum), normal approx
def mannwhitney(a,b):
    combined=sorted([(v,'a') for v in a]+[(v,'b') for v in b])
    ranks={}; i=0
    # assign average ranks for ties
    vals=[v for v,_ in combined]
    n=len(vals); r=[0.0]*n
    i=0
    while i<n:
        j=i
        while j+1<n and vals[j+1]==vals[i]: j+=1
        avg=(i+j)/2+1
        for k in range(i,j+1): r[k]=avg
        i=j+1
    Ra=sum(r[idx] for idx,(_,g) in enumerate(combined) if g=='a')
    na,nb=len(a),len(b)
    Ua=Ra-na*(na+1)/2
    mu=na*nb/2
    import math
    sigma=math.sqrt(na*nb*(na+nb+1)/12)
    z=(Ua-mu)/sigma if sigma else 0
    # two-sided p
    p=math.erfc(abs(z)/math.sqrt(2))
    return z,p

if conf and open_:
    z,p=mannwhitney(conf,open_)
    print(f"\nMann-Whitney rank-sum: z={z:.2f}, two-sided p={p:.3f}")
    print("(positive z => confidential ranks HIGHER/larger)")
