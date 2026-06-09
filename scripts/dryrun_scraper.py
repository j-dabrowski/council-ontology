#!/usr/bin/env python3
"""
Dry-run: run _collect_from_playwright for 2024 only and print discovered URLs.
Does NOT download any PDFs. Used to verify the fix before re-scraping.
"""
import sys
sys.path.insert(0, "/Users/josef/Projects/council-ontology/src")

from scraper.cambridge import _collect_from_playwright

docs = _collect_from_playwright(since_year=2024, until_year=2024, request_delay=0.3)

print(f"\nDiscovered {len(docs)} documents for 2024:\n")
def classify(url: str) -> str:
    fname = url.rstrip("/").rsplit("/", 1)[-1].lower()
    if "minutes" in fname:
        return "MINUTES"
    if "agenda" in fname or "addendum" in fname:
        return "AGENDA"
    return "UNKNOWN"

for doc in sorted(docs, key=lambda d: d.meeting_date):
    doc_type = classify(doc.source_url)
    print(f"  {doc.meeting_date}  {doc.meeting_type:<35s}  [{doc_type}]  {doc.source_url.split('/')[-1]}")

agenda_count = sum(1 for d in docs if classify(d.source_url) == "AGENDA")
minutes_count = sum(1 for d in docs if classify(d.source_url) == "MINUTES")
unknown_count = len(docs) - agenda_count - minutes_count
print(f"\nSummary: {len(docs)} total  |  {minutes_count} minutes  |  {agenda_count} agendas  |  {unknown_count} unknown")
