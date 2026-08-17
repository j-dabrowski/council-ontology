import sqlite3, re
from datetime import datetime, timedelta

con = sqlite3.connect("data/council.db")
con.row_factory = sqlite3.Row

BODIES = {
    "Mindarie Regional Council": ["Mindarie"],
    "Tamala Park Regional Council": ["Tamala Park"],
    "Ocean Gardens (Inc) Board of Management": ["Ocean Gardens"],
}

# get appointments (councillor_id, body, appointment date)
appts = con.execute("""
    SELECT a.councillor_id, a.body_name, m.meeting_date
    FROM appointments a JOIN meetings m ON a.meeting_id = m.id
    WHERE a.body_name IN (%s) AND a.councillor_id IS NOT NULL
      AND m.document_type='minutes'
    ORDER BY a.councillor_id, a.body_name, m.meeting_date
""" % ",".join("?"*len(BODIES)), list(BODIES.keys())).fetchall()

# build windows: per (councillor, body), list of appointment dates -> window = [date, next_date or date+4y)
from collections import defaultdict
by_pair = defaultdict(list)
for r in appts:
    by_pair[(r["councillor_id"], r["body_name"])].append(r["meeting_date"])

windows = []  # (councillor_id, body, start, end)
for (cid, body), dates in by_pair.items():
    dates = sorted(dates)
    for i, d in enumerate(dates):
        start = datetime.strptime(d, "%Y-%m-%d")
        if i+1 < len(dates):
            end = datetime.strptime(dates[i+1], "%Y-%m-%d")
        else:
            end = start + timedelta(days=365*4)
        windows.append((cid, body, start, end))

print(f"Total appointment windows: {len(windows)} across {len(by_pair)} (councillor,body) pairs, {len(BODIES)} bodies")

# now for each body, find motions mentioning it (any keyword), minutes only
all_results = {}
for body, keywords in BODIES.items():
    like_clauses = " OR ".join(["(mo.title LIKE ? OR mo.motion_text LIKE ?)" for _ in keywords])
    params = []
    for k in keywords:
        params += [f"%{k}%", f"%{k}%"]
    motions = con.execute(f"""
        SELECT mo.id, mo.title, m.meeting_date, mo.item_number
        FROM motions mo JOIN meetings m ON mo.meeting_id = m.id
        WHERE ({like_clauses}) AND m.document_type='minutes'
    """, params).fetchall()
    motion_ids = [r["id"] for r in motions]
    motion_dates = {r["id"]: r["meeting_date"] for r in motions}
    if not motion_ids:
        continue
    # votes on these motions
    qmarks = ",".join("?"*len(motion_ids))
    votes = con.execute(f"""
        SELECT v.motion_id, v.councillor_id, v.choice, v.declared_interest
        FROM votes v WHERE v.motion_id IN ({qmarks})
    """, motion_ids).fetchall()

    # which windows apply to this body
    body_windows = [w for w in windows if w[1] == body]

    affiliated_votes = []
    other_votes = []
    for v in votes:
        mdate = datetime.strptime(motion_dates[v["motion_id"]], "%Y-%m-%d")
        is_affiliated = any(w[0] == v["councillor_id"] and w[2] <= mdate < w[3] for w in body_windows)
        if is_affiliated:
            affiliated_votes.append(v)
        else:
            other_votes.append(v)

    n_aff = len(affiliated_votes)
    n_aff_decl = sum(1 for v in affiliated_votes if v["declared_interest"])
    n_oth = len(other_votes)
    n_oth_decl = sum(1 for v in other_votes if v["declared_interest"])
    all_results[body] = dict(n_motions=len(motion_ids), n_aff=n_aff, n_aff_decl=n_aff_decl,
                              n_oth=n_oth, n_oth_decl=n_oth_decl)
    print(f"\n== {body} ==")
    print(f"  motions mentioning body: {len(motion_ids)}")
    print(f"  affiliated-rep votes: {n_aff}, declared: {n_aff_decl} ({100*n_aff_decl/n_aff if n_aff else 0:.1f}%)")
    print(f"  other councillor votes: {n_oth}, declared: {n_oth_decl} ({100*n_oth_decl/n_oth if n_oth else 0:.1f}%)")

    # also show choice breakdown for affiliated
    from collections import Counter
    print("  affiliated choice breakdown:", Counter(v["choice"] for v in affiliated_votes))
