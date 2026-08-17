import sqlite3
from datetime import date, timedelta

con = sqlite3.connect("data/council.db")
con.row_factory = sqlite3.Row

SHOCK = date(2006,6,27)

rows = con.execute("""
    SELECT mo.id, mo.outcome, mo.votes_against, m.meeting_date
    FROM motions mo JOIN meetings m ON mo.meeting_id = m.id
    WHERE m.document_type='minutes' AND mo.outcome='CARRIED'
""").fetchall()

def dt(r): return date.fromisoformat(r["meeting_date"])

for months in [12, 18, 24]:
    before = [r for r in rows if SHOCK - timedelta(days=30*months) <= dt(r) < SHOCK]
    after  = [r for r in rows if SHOCK <= dt(r) < SHOCK + timedelta(days=30*months)]
    bn, an = len(before), len(after)
    bc = sum(1 for r in before if r["votes_against"] and r["votes_against"]>0)
    ac = sum(1 for r in after if r["votes_against"] and r["votes_against"]>0)
    print(f"window +/-{months}mo: before n={bn} contested={bc} ({100*bc/bn if bn else 0:.1f}%); after n={an} contested={ac} ({100*ac/an if an else 0:.1f}%)")

# election dates nearby for confound check
print("nearest odd-year elections: Oct 2005, Oct 2007")

# delegated_decisions coverage around this period
dd = con.execute("""
    SELECT m.meeting_date FROM delegated_decisions dd JOIN meetings m ON dd.meeting_id=m.id
    WHERE m.document_type='minutes' AND m.meeting_date BETWEEN '2004-01-01' AND '2009-01-01'
""").fetchall()
print(f"delegated_decisions rows 2004-2009: {len(dd)}")

# confidential share (other_items+tenders+delegated_decisions+budget_items) before/after, +/-18mo
def conf_share(lo, hi):
    total=0; conf=0
    for tbl in ["tenders","other_items","delegated_decisions","budget_items"]:
        for r in con.execute(f"""
            SELECT is_confidential FROM {tbl} x JOIN meetings m ON x.meeting_id=m.id
            WHERE m.document_type='minutes' AND m.meeting_date >= ? AND m.meeting_date < ?
        """, (lo.isoformat(), hi.isoformat())):
            total+=1
            conf+= r[0] or 0
    return conf, total

for months in [12,18,24]:
    c_b, t_b = conf_share(SHOCK - timedelta(days=30*months), SHOCK)
    c_a, t_a = conf_share(SHOCK, SHOCK + timedelta(days=30*months))
    print(f"confidential share +/-{months}mo: before {c_b}/{t_b} ({100*c_b/t_b if t_b else 0:.1f}%); after {c_a}/{t_a} ({100*c_a/t_a if t_a else 0:.1f}%)")
