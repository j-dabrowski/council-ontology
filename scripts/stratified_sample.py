"""
Select a stratified 15-20 document sample for Level 3 prompt validation.

Stratifies by era (decade), size bucket, meeting type, and flagged outliers
using Level 0 census data and Level 1 inventory flags.

Usage:
    python scripts/stratified_sample.py cambridge [--count N] [--output-file PATH]
    council sample cambridge [--count N]

Output: space-separated filenames to stdout; summary to stderr. Suitable for:
    council extract --files $(python scripts/stratified_sample.py cambridge)
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

DATA_DIR = _REPO_ROOT / "data"


def load_census() -> list[dict]:
    path = DATA_DIR / "census.json"
    if not path.exists():
        raise FileNotFoundError(f"Census not found at {path}. Run `council census cambridge` first.")
    return json.loads(path.read_text())["documents"]


def load_l1_flags() -> dict[str, list[str]]:
    """Return {filename: [flag, ...]} for docs that have L1 census_comparison flags."""
    inv_dir = DATA_DIR / "inventories"
    result: dict[str, list[str]] = {}
    if not inv_dir.exists():
        return result
    for path in inv_dir.glob("*.json"):
        if path.name == "summary.json":
            continue
        try:
            doc = json.loads(path.read_text())
            flags = doc.get("census_comparison", {}).get("flags", [])
            if flags:
                result[doc["filename"]] = flags
        except Exception:
            pass
    return result


def select_sample(docs: list[dict], l1_flags: dict[str, list[str]], target: int = 18) -> list[str]:
    """
    Greedy stratified selection.

    Slots filled in order:
      1. L1-flagged docs                      (cap: 3)
      2. L0 outlier docs (no keywords / zero) (cap: 3 total between L0+L1)
      3. One doc per (decade × size_bucket) cell, covering the era/size grid
      4. Ensure ≥2 docs per decade
      5. Minority meeting types not yet represented
      6. Pad to target with remaining docs
    """
    OUTLIER_FLAGS = {"no_motion_keywords", "zero_keyword_hits"}
    OUTLIER_CAP = 3

    extractable = [d for d in docs if d.get("extraction_status") != "failed"]
    by_name = {d["filename"]: d for d in extractable}

    selected: list[str] = []
    seen: set[str] = set()

    def add(filename: str) -> bool:
        if filename in seen or filename not in by_name:
            return False
        seen.add(filename)
        selected.append(filename)
        return True

    # 1 + 2: Outliers (L1 first, then L0), capped at OUTLIER_CAP
    for fn in l1_flags:
        if len([s for s in selected if _is_outlier(by_name.get(s, {}), l1_flags)]) >= OUTLIER_CAP:
            break
        add(fn)

    for doc in extractable:
        if sum(1 for s in selected if _is_outlier(by_name[s], l1_flags)) >= OUTLIER_CAP:
            break
        if any(f in OUTLIER_FLAGS for f in doc.get("flags", [])):
            add(doc["filename"])

    # 3. Era × size grid: one doc per (decade, size_bucket) cell.
    # Within each cell prefer Ordinary Council Meetings so the sample isn't
    # dominated by whatever meeting type happens to be first in the list.
    def _type_priority(doc: dict) -> int:
        mt = doc.get("meeting_type", "")
        if "Ordinary" in mt:
            return 0
        if "Special" in mt:
            return 1
        return 2

    # Reserve 4 slots for steps 4+5 (decade balance + meeting type diversity).
    grid_cap = target - 4
    cells_filled: set[tuple] = set()
    for doc in sorted(extractable, key=_type_priority):
        if len(selected) >= grid_cap:
            break
        cell = (doc.get("decade"), doc.get("size_bucket"))
        if None not in cell and cell not in cells_filled:
            if add(doc["filename"]):
                cells_filled.add(cell)

    # 4. Ensure ≥2 per decade
    decade_counts = Counter(by_name[fn].get("decade") for fn in selected)
    for doc in extractable:
        if len(selected) >= target:
            break
        dec = doc.get("decade")
        if dec and decade_counts[dec] < 2:
            if add(doc["filename"]):
                decade_counts[dec] += 1

    # 5. Minority meeting types not yet represented
    types_seen = {by_name[fn].get("meeting_type") for fn in selected}
    priority_types = [
        "Annual General Meeting",
        "Annual General Meeting Of Electors",
        "Special Council Meeting",
        "Electors Meeting",
        "Audit Committee",
        "Public Art Committee",
    ]
    for mtype in priority_types:
        if len(selected) >= target:
            break
        if mtype not in types_seen:
            for doc in extractable:
                if doc.get("meeting_type") == mtype:
                    if add(doc["filename"]):
                        types_seen.add(mtype)
                        break

    # 6. Pad to target
    for doc in extractable:
        if len(selected) >= target:
            break
        add(doc["filename"])

    return selected


def _is_outlier(doc: dict, l1_flags: dict) -> bool:
    OUTLIER_FLAGS = {"no_motion_keywords", "zero_keyword_hits"}
    return (
        doc.get("filename") in l1_flags
        or any(f in OUTLIER_FLAGS for f in doc.get("flags", []))
    )


def _print_summary(sample: list[str], by_name: dict, l1_flags: dict) -> None:
    print(f"\nSample: {len(sample)} documents", file=sys.stderr)
    print("  Decades:", dict(Counter(by_name[fn].get("decade") for fn in sample).most_common()), file=sys.stderr)
    print("  Sizes:  ", dict(Counter(by_name[fn].get("size_bucket") for fn in sample).most_common()), file=sys.stderr)
    print("  Types:", file=sys.stderr)
    for mtype, count in Counter(by_name[fn].get("meeting_type") for fn in sample).most_common():
        print(f"    {count:3d}  {mtype}", file=sys.stderr)
    l1_in = [fn for fn in sample if fn in l1_flags]
    l0_in = [fn for fn in sample if _is_outlier(by_name[fn], l1_flags) and fn not in l1_flags]
    if l1_in:
        print(f"  L1-flagged: {l1_in}", file=sys.stderr)
    if l0_in:
        print(f"  L0-flagged: {l0_in}", file=sys.stderr)


def canonical_sample_path(council: str) -> Path:
    return _REPO_ROOT / "data" / f"{council}_sample.json"


def run(args) -> None:
    import datetime

    docs = load_census()
    l1_flags = load_l1_flags()
    target = getattr(args, "count", 18)
    council = args.council

    sample = select_sample(docs, l1_flags, target=target)
    by_name = {d["filename"]: d for d in docs}

    # Always persist to canonical location so extract-sample and validate-sample
    # reference exactly the same document set.
    canonical = canonical_sample_path(council)
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text(
        json.dumps(
            {
                "council": council,
                "selected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "count": len(sample),
                "files": sample,
            },
            indent=2,
        )
    )
    print(f"Saved sample to {canonical}", file=sys.stderr)

    if getattr(args, "output_file", None):
        Path(args.output_file).write_text("\n".join(sample) + "\n")
        print(f"Wrote {len(sample)} filenames to {args.output_file}", file=sys.stderr)
    else:
        print(" ".join(sample))

    _print_summary(sample, by_name, l1_flags)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("council", help="Council short name (e.g. cambridge)")
    parser.add_argument("--count", type=int, default=18, help="Target sample size (default: 18)")
    parser.add_argument("--output-file", metavar="PATH", help="Write filenames to file instead of stdout")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
