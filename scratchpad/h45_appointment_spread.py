"""[45] Genre E — does external-body representation (the `appointments`
table) rotate broadly across the chamber, or concentrate in a small
entrenched clique once tenure is controlled for?
"""
import sqlite3
import statistics
from datetime import date

con = sqlite3.connect("data/council.db")
con.row_factory = sqlite3.Row

n_appointed = con.execute(
    "SELECT COUNT(DISTINCT councillor_id) FROM appointments WHERE councillor_id IS NOT NULL"
).fetchone()[0]
n_voted = con.execute("SELECT COUNT(DISTINCT councillor_id) FROM votes").fetchone()[0]
print(f"Distinct councillors ever appointed: {n_appointed} / {n_voted} who ever voted "
      f"({100*n_appointed/n_voted:.1f}%)")

total_slots = con.execute(
    "SELECT COUNT(*) FROM appointments WHERE councillor_id IS NOT NULL"
).fetchone()[0]
top10_slots = con.execute("""
    WITH counts AS (
      SELECT councillor_id, COUNT(*) n FROM appointments
      WHERE councillor_id IS NOT NULL GROUP BY councillor_id ORDER BY n DESC LIMIT 10
    ) SELECT SUM(n) FROM counts
""").fetchone()[0]
print(f"Top-10 appointees hold {top10_slots}/{total_slots} slots "
      f"({100*top10_slots/total_slots:.1f}%) out of {n_appointed} distinct appointees")

# tenure (span of votes, >=20 votes, minutes only) same method as [8]
tenure = {}
for r in con.execute("""
    SELECT v.councillor_id, MIN(m.meeting_date) mn, MAX(m.meeting_date) mx, COUNT(*) nv
    FROM votes v JOIN motions mo ON v.motion_id = mo.id JOIN meetings m ON mo.meeting_id = m.id
    WHERE m.document_type = 'minutes'
    GROUP BY v.councillor_id HAVING nv >= 20
"""):
    span_years = (date.fromisoformat(r["mx"]) - date.fromisoformat(r["mn"])).days / 365.25
    tenure[r["councillor_id"]] = max(span_years, 0.5)

appt_counts = {
    r["councillor_id"]: r["n"]
    for r in con.execute(
        "SELECT councillor_id, COUNT(*) n FROM appointments WHERE councillor_id IS NOT NULL GROUP BY councillor_id"
    )
}
names = {
    r["id"]: f'{r["given_name"]} {r["family_name"]}'
    for r in con.execute("SELECT id, given_name, family_name FROM councillors")
}

rates = [(cid, appt_counts.get(cid, 0), yrs, appt_counts.get(cid, 0) / yrs) for cid, yrs in tenure.items()]
rates.sort(key=lambda x: -x[3])

print(f"\nCohort (>=20 votes): n={len(rates)}, appointed at least once: "
      f"{sum(1 for r in rates if r[1] > 0)}, zero appointments: {sum(1 for r in rates if r[1] == 0)}")
print("Top 10 by appointments-per-year-served:")
for cid, n, yrs, rate in rates[:10]:
    flag = "  (short tenure, small-n note)" if yrs < 2 else ""
    print(f"  {names[cid]}: {n} appts / {yrs:.1f}y = {rate:.2f}/yr{flag}")

allrates = [r[3] for r in rates]
print(f"\nmedian rate: {statistics.median(allrates):.2f}/yr, mean: {statistics.mean(allrates):.2f}/yr")

# exclude denominator<2y outliers per the pre-registered confound check
stable = [r for r in rates if r[2] >= 2]
print(f"Excluding tenure<2y outliers (n={len(rates)-len(stable)} dropped): "
      f"median {statistics.median([r[3] for r in stable]):.2f}/yr, "
      f"mean {statistics.mean([r[3] for r in stable]):.2f}/yr, top rate "
      f"{max(r[3] for r in stable):.2f}/yr ({names[max(stable, key=lambda r: r[3])[0]]})")
