import sqlite3
from datetime import date

con = sqlite3.connect("data/council.db")
con.row_factory = sqlite3.Row

rows = con.execute("""
    SELECT t.amount, m.meeting_date
    FROM tenders t JOIN meetings m ON t.meeting_id = m.id
    WHERE m.document_type='minutes' AND t.amount IS NOT NULL AND t.amount > 0
""").fetchall()

def in_preelection(d):
    dt = date.fromisoformat(d)
    if dt.year % 2 == 1:  # odd year
        return date(dt.year,4,1) <= dt <= date(dt.year,10,31)
    return False

pre_amt = sum(r["amount"] for r in rows if in_preelection(r["meeting_date"]))
pre_n = sum(1 for r in rows if in_preelection(r["meeting_date"]))
rest_amt = sum(r["amount"] for r in rows if not in_preelection(r["meeting_date"]))
rest_n = sum(1 for r in rows if not in_preelection(r["meeting_date"]))
total_amt = pre_amt+rest_amt
total_n = pre_n+rest_n

# window is 7 months of every 4-year (48-month) cycle = 7/48 = 14.6% of time if elections always fall Apr-Oct
# but "pre-election" occurs once per 2-yr cycle -> odd years only, so window = 7 months every 24 months = 29.2% of calendar time... but 4-yr terms, elections held every 2 years for half the seats typically. Let's just report share.
print(f"Pre-election window (Apr-Oct odd yr): n={pre_n}, ${pre_amt:,.0f} ({100*pre_amt/total_amt:.1f}% of $, {100*pre_n/total_n:.1f}% of n)")
print(f"Rest of cycle: n={rest_n}, ${rest_amt:,.0f} ({100*rest_amt/total_amt:.1f}% of $, {100*rest_n/total_n:.1f}% of n)")
print(f"Total: n={total_n}, ${total_amt:,.0f}")
# window length share: Apr-Oct = 7 months, out of 24-month full election cycle -> 29.2%
print(f"Window is 7/24 = {700/24:.1f}% of the biennial cycle by calendar time (expected share if flat)")

# per era split
for lo,hi,label in [(1995,2017,"pre-2018"),(2018,2021,"inquiry"),(2022,2026,"post-2022")]:
    sub = [r for r in rows if lo <= int(r["meeting_date"][:4]) <= hi]
    pa = sum(r["amount"] for r in sub if in_preelection(r["meeting_date"]))
    pn = sum(1 for r in sub if in_preelection(r["meeting_date"]))
    ta = sum(r["amount"] for r in sub)
    tn = len(sub)
    if ta:
        print(f"  {label}: pre-election ${pa:,.0f}/{pn} of total ${ta:,.0f}/{tn} = {100*pa/ta:.1f}% $ / {100*pn/tn:.1f}% n")
