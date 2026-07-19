"""[36] What gets closed, not just when — is confidentiality aimed at particular
subject matter? Topical decomposition (not temporal). Bucket confidential items by
theme; compare the confidential-share of each theme against its share of all business.
Legitimate grounds (tenders/legal/HR/contracts/land) expected to dominate; the finding
is only the RESIDUAL contentious-topic excess, if any. Verify clusters via provenance.
"""
import sqlite3, re
db = sqlite3.connect("data/council.db"); c = db.cursor()

rows = []
for tbl in ("tenders","other_items","delegated_decisions"):
    for desc, conf in c.execute(f"""
        SELECT COALESCE(x.description,''), x.is_confidential
        FROM {tbl} x JOIN meetings m ON x.meeting_id=m.id
        WHERE m.document_type='minutes'"""):
        rows.append((tbl, desc.lower(), conf))

# theme keyword buckets (legitimate vs potentially-contentious)
themes = {
    "legal/litigation":   r"legal|litigation|court|claim|settlement|solicitor|counsel|dispute",
    "personnel/HR":       r"\bceo\b|chief executive|staff|employee|personnel|recruit|remuneration|salary|human resource",
    "tender/procurement": r"tender|rft|contract|procure|quotation|supplier|panel",
    "land/property deal": r"lease|land|acquisition|dispose|disposal|purchase of|sale of|easement|freehold|valuation",
    "named development":  r"development|structure plan|precinct|activity centre|rezoning|subdivision|building height",
    "finance/investment": r"investment|reserve|loan|borrow|financial statement|budget|audit",
    "commercial-in-conf": r"commercial|confidential|in-confidence|negotiation|proposal",
}
def theme_of(desc):
    hits=[t for t,pat in themes.items() if re.search(pat, desc)]
    return hits  # can be multiple

# tally: for each theme, total items and confidential items
from collections import defaultdict
tot=defaultdict(int); conf=defaultdict(int)
ALL_tot=0; ALL_conf=0
for tbl, desc, ic in rows:
    ALL_tot+=1; ALL_conf+= (1 if ic else 0)
    for t in theme_of(desc):
        tot[t]+=1; conf[t]+= (1 if ic else 0)

base = ALL_conf/ALL_tot*100
print(f"ALL items (minutes, 3 tables): {ALL_tot}; confidential {ALL_conf} ({base:.1f}%)")
print(f"\n{'theme':22s}{'items':>7s}{'conf':>6s}{'conf%':>7s}{'lift_vs_base':>13s}")
for t in sorted(themes, key=lambda x:-(conf[x]/tot[x] if tot[x] else 0)):
    if tot[t]==0: continue
    rate=conf[t]/tot[t]*100
    print(f"{t:22s}{tot[t]:7d}{conf[t]:6d}{rate:7.1f}{rate/base:13.2f}")

# share of confidential pool by theme (what dominates the closed set)
print(f"\n=== composition of the {ALL_conf} confidential items by theme (can overlap) ===")
for t in sorted(themes, key=lambda x:-conf[x]):
    if conf[t]: print(f"  {t:22s}{conf[t]:4d}  ({conf[t]/ALL_conf*100:4.1f}% of confidential pool)")

# untagged confidential (no theme matched) — how many slip the buckets?
untag=sum(1 for tbl,desc,ic in rows if ic and not theme_of(desc))
print(f"\nconfidential items matching NO theme bucket: {untag}")
