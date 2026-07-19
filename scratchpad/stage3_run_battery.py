"""Stage 3 — verification run of the standard 23-test battery.
Confirms results match the documented [BATTERY] entry (6 supportive / 10 neutral
/ 5 critical / 2 not-computable). Does NOT write scorecard.json / does NOT publish.
"""
from src.storage.database import init_db, make_session_factory
from src.models import Council
from src.analysis.tests import run_test_battery, battery_summary

engine = init_db()
session = make_session_factory(engine)()
council = session.query(Council).filter_by(short_name="Cambridge").first()
cid = council.id

results = run_test_battery(session, cid)
summ = battery_summary(results)

print("=== BATTERY SUMMARY ===")
print(summ)
print(f"total tests: {len(results)}")
print()
print("=== PER-TEST ===")
for r in results:
    ok = "OK " if r.data_ok else "NODATA"
    print(f"[{ok}] {r.valence:11s} {r.grade:28s} {r.test_id:40s} n={r.n}")
