"""[29] Does spending spike at the AUSTRALIAN fiscal-year end (30 June), not December?
Re-bins tender/budget_item dollars by month AND by weeks-to-30-June, normalised by
meeting cadence, split by era. Directly re-specifies finance.eoy_spending [4], which
keyed on December (calendar).
"""
import sqlite3, datetime
db = sqlite3.connect("data/council.db")
c = db.cursor()

# tenders with amount + date (minutes only)
rows = c.execute("""
  SELECT t.amount, m.meeting_date
  FROM tenders t JOIN meetings m ON t.meeting_id=m.id
  WHERE m.document_type='minutes' AND t.amount IS NOT NULL
""").fetchall()

def parse(d):
    return datetime.date.fromisoformat(d[:10])

months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
by_month_amt = [0.0]*12
by_month_n = [0]*12
for a, d in rows:
    dt = parse(d); mo = dt.month
    by_month_amt[mo-1]+=a/1e6; by_month_n[mo-1]+=1

# meeting cadence: count of minutes-meetings per month (normaliser)
cad = c.execute("""SELECT CAST(strftime('%m', meeting_date) AS INT) mo, COUNT(*)
                   FROM meetings WHERE document_type='minutes' GROUP BY mo""").fetchall()
cadence = {mo: n for mo, n in cad}

print("=== Tender $ and awards by CALENDAR month (n awards with amount = %d) ===" % len(rows))
print(f"{'Mo':4s}{'$M':>8s}{'nAwd':>6s}{'meetings':>10s}{'$M/meeting':>12s}")
for i in range(12):
    mtg = cadence.get(i+1,0)
    per = by_month_amt[i]/mtg if mtg else 0
    print(f"{months[i]:4s}{by_month_amt[i]:8.1f}{by_month_n[i]:6d}{mtg:10d}{per:12.2f}")

# weeks-to-30-June bucketing (AU fiscal year ends 30 June)
def weeks_to_june30(dt):
    y = dt.year
    fye = datetime.date(y, 6, 30)
    if dt > fye:  # after 30 June -> next FYE
        fye = datetime.date(y+1, 6, 30)
    return (fye - dt).days // 7

buckets = {"0-2wk to 30Jun":0.0, "3-6wk":0.0, "7-12wk":0.0, "13-26wk":0.0, ">26wk":0.0}
bn = {k:0 for k in buckets}
for a, d in rows:
    w = weeks_to_june30(parse(d))
    if w<=2: k="0-2wk to 30Jun"
    elif w<=6: k="3-6wk"
    elif w<=12: k="7-12wk"
    elif w<=26: k="13-26wk"
    else: k=">26wk"
    buckets[k]+=a/1e6; bn[k]+=1
print("\n=== Tender $ by WEEKS-TO-30-JUNE (fiscal year end) ===")
for k in buckets:
    print(f"  {k:18s} ${buckets[k]:7.1f}M  n={bn[k]}")

# May+June share vs December share, and by era
def era(y):
    if y<2018: return "pre-2018"
    if y<=2021: return "inquiry"
    return "post-2022"
eras = {}
for a,d in rows:
    dt=parse(d); e=era(dt.year)
    eras.setdefault(e, {"total":0.0,"mayjun":0.0,"dec":0.0,"n":0})
    eras[e]["total"]+=a/1e6; eras[e]["n"]+=1
    if dt.month in (5,6): eras[e]["mayjun"]+=a/1e6
    if dt.month==12: eras[e]["dec"]+=a/1e6
print("\n=== May+Jun (fiscal-end) share vs Dec (calendar) share, by era ===")
for e,v in eras.items():
    t=v["total"] or 1
    print(f"  {e:10s} n={v['n']:3d}  total=${t:6.1f}M  May+Jun={v['mayjun']/t*100:4.1f}%  Dec={v['dec']/t*100:4.1f}%")

# overall
tot = sum(by_month_amt)
mayjun = by_month_amt[4]+by_month_amt[5]
dec = by_month_amt[11]
print(f"\nOVERALL: total=${tot:.1f}M  May+Jun={mayjun/tot*100:.1f}% ({(by_month_n[4]+by_month_n[5])} awards)  "
      f"Dec={dec/tot*100:.1f}% ({by_month_n[11]} awards)  even-spread 2mo=~16.7%")
