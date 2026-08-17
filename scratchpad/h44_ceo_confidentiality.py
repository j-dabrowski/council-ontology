"""[44] Genre D — is CEO/personnel-matter business confidential above the
[36] base rate, and did it move with the Inquiry / CEO-turnover era?

Reuses the [9]/[19] pre-2018 / inquiry-2018-21 / post-2022 era boundaries.
"""
import sqlite3

con = sqlite3.connect("data/council.db")
con.row_factory = sqlite3.Row

total, conf = con.execute("""
    SELECT COUNT(*), SUM(is_confidential) FROM other_items
    WHERE description LIKE '%Chief Executive Officer%' OR description LIKE '%CEO%'
""").fetchone()
print(f"CEO-related other_items: n={total}, confidential={conf} ({100*conf/total:.1f}%)")

btotal, bconf = con.execute("SELECT COUNT(*), SUM(is_confidential) FROM other_items").fetchone()
print(f"All other_items base rate: n={btotal}, confidential={bconf} ({100*bconf/btotal:.1f}%)")
print(f"Lift: {(conf/total)/(bconf/btotal):.2f}x")

print("\nBy era (minutes only):")
for row in con.execute("""
    SELECT
      CASE WHEN m.meeting_date < '2018-01-01' THEN 'pre-2018'
           WHEN m.meeting_date < '2022-01-01' THEN 'inquiry'
           ELSE 'post-2022' END AS era,
      COUNT(*) n, SUM(oi.is_confidential) c
    FROM other_items oi JOIN meetings m ON oi.meeting_id = m.id
    WHERE m.document_type='minutes'
      AND (oi.description LIKE '%Chief Executive Officer%' OR oi.description LIKE '%CEO%')
    GROUP BY era
    ORDER BY CASE era WHEN 'pre-2018' THEN 1 WHEN 'inquiry' THEN 2 ELSE 3 END
"""):
    print(f"  {row['era']}: n={row['n']}, confidential={row['c']} ({100*row['c']/row['n']:.1f}%)")
