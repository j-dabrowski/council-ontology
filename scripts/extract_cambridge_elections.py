"""
Extract Town of Cambridge election results from Elections WA PDFs (1999-2023).
Outputs a CSV suitable for: council import-terms cambridge <file> --apply

Thin wrapper around the generalised scripts/extract_wa_elections.py
(SECOND_COUNCIL_PLAN.md 5.3) — kept so `python
scripts/extract_cambridge_elections.py` still works unchanged; all parsing
logic and Cambridge's own REPORTS/ward_aliases now live in
extract_wa_elections.py's COUNCIL_CONFIGS["cambridge"].
"""

import sys

from extract_wa_elections import main


def main_cambridge(output_path: str = "data/cambridge_elections_raw.csv"):
    main("cambridge", output_path)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "data/cambridge_elections_raw.csv"
    main_cambridge(out)
