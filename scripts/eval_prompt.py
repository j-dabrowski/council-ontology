# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
Evaluate system prompt quality across benchmark PDFs and models.

Run this after every prompt edit to validate improvements are real and generalised.

Usage:
    python scripts/eval_prompt.py              # full benchmark, all models
    python scripts/eval_prompt.py --quick      # random PDF from benchmark, all 3 models (faster sanity check)
    python scripts/eval_prompt.py --compare    # show delta vs previous run
    python scripts/eval_prompt.py --show       # print latest saved report

Score dimensions (each 0–100, weighted to a combined score):
    meta      (15%)  meeting_date, meeting_type, council_name present and correct
    roster    (20%)  councillors_present non-empty, given names populated
    motions   (30%)  motion_text, outcome, moved_by coverage across all motions
    votes     (15%)  individual or aggregate vote coverage (skipped when not expected)
    planning  (20%)  planning_application object populated when motion is planning-tagged

Agreement bonus (+5 max): cross-model consistency on date, type, motion count, councillors.

Overfitting guard: warns when improvement is concentrated on PDFs recently used in
prompt development (data/model_comparison/) versus the rest of the benchmark.
"""

import argparse
import hashlib
import json
import random
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich import box

from src.extraction.extractor import MinutesExtractor, extract_text_from_pdf, _SYSTEM_PROMPT
from src.extraction.schemas import ExtractedMeeting

# Record=True captures output for saving as plain text alongside the JSON report
console = Console(record=True)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ALL_MODELS = [
    ("Haiku 4.5",  "claude-haiku-4-5-20251001"),
    ("Sonnet 4.6", "claude-sonnet-4-6"),
    ("Opus 4.6",   "claude-opus-4-6"),
]

# Only these models contribute to the combined score and agreement metric.
# Opus is run for reference but excluded from scoring because it hallucinates
# data outside the 80k truncation window, inflating its votes score artificially.
SCORING_MODELS = {"Haiku 4.5", "Sonnet 4.6"}

WEIGHTS = {
    "meta":     0.15,
    "roster":   0.20,
    "motions":  0.30,
    "votes":    0.15,
    "planning": 0.20,
}

BENCHMARK_PATH  = Path("data/eval/benchmark.json")
QUICK_STATE_PATH = Path("data/eval/quick_state.json")
EVAL_DIR        = Path("data/eval")


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _extract_one(
    label: str, model_id: str, text: str,
    pdf_name: str, council_name: str, date_hint: str | None,
) -> tuple[str, ExtractedMeeting | None, str | None]:
    try:
        result = MinutesExtractor(model=model_id).extract(
            text,
            source_hint=f"{pdf_name} [{label}]",
            council_name=council_name,
            meeting_date_hint=date_hint,
        )
        return label, result, None
    except Exception as exc:
        return label, None, str(exc)


def run_extraction(
    pdf_path: Path,
    council_name: str,
    date_hint: str | None,
    models: list[tuple[str, str]],
) -> tuple[dict[str, ExtractedMeeting | None], dict[str, str]]:
    text = extract_text_from_pdf(pdf_path)
    results: dict = {}
    errors: dict = {}
    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        futures = {
            pool.submit(_extract_one, lbl, mid, text, pdf_path.name, council_name, date_hint): lbl
            for lbl, mid in models
        }
        for fut in as_completed(futures):
            lbl, result, err = fut.result()
            if err:
                errors[lbl] = err
                results[lbl] = None
            else:
                results[lbl] = result
    return results, errors


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_model(result: ExtractedMeeting | None, expected: dict) -> dict:
    """Score one model's extraction result. All sub-scores are 0–100."""
    if result is None:
        return {k: 0.0 for k in WEIGHTS} | {"total": 0.0, "n_motions": 0, "error": True}

    motions = result.motions
    n = len(motions)

    # ── meta ─────────────────────────────────────────────────────────────────
    type_ok = bool(result.meeting_type)
    if type_ok and expected.get("meeting_type_contains"):
        type_ok = expected["meeting_type_contains"].lower() in result.meeting_type.lower()
    meta = sum([bool(result.meeting_date), type_ok, bool(result.council_name)]) / 3

    # ── roster ───────────────────────────────────────────────────────────────
    if result.councillors_present:
        n_cr = len(result.councillors_present)
        n_given = sum(1 for c in result.councillors_present if c.given_name and c.given_name.strip())
        # 50% for having councillors at all, 50% for given name quality
        roster = 0.5 + 0.5 * (n_given / n_cr)
    else:
        roster = 0.0

    # ── motions ──────────────────────────────────────────────────────────────
    if n == 0:
        motions_score = 0.0
    else:
        text_cov    = sum(1 for m in motions if m.motion_text) / n
        outcome_cov = sum(1 for m in motions if m.outcome) / n
        mover_cov   = sum(1 for m in motions if m.moved_by) / n
        motions_score = (text_cov + outcome_cov + mover_cov) / 3
        # Penalise if fewer motions than expected
        min_m = expected.get("min_motions", 0)
        if min_m > 0 and n < min_m:
            motions_score *= max(0.2, n / min_m)

    # ── votes ────────────────────────────────────────────────────────────────
    if not expected.get("has_vote_rolls", True):
        # Votes not expected in this document — don't penalise absence
        votes_score = 1.0
    elif n == 0:
        votes_score = 0.0
    else:
        has_vote = sum(
            1 for m in motions
            if m.individual_votes
            or m.votes_for is not None
            or m.votes_against is not None
        ) / n
        votes_score = has_vote
        # Extra check: contested vote expected → at least one motion has against votes
        if expected.get("has_contested_vote"):
            has_split = any(
                any(v.choice == "against" for v in m.individual_votes)
                or (m.votes_against is not None and m.votes_against > 0)
                for m in motions
            )
            if not has_split:
                votes_score *= 0.5

    # ── planning ─────────────────────────────────────────────────────────────
    if expected.get("has_planning_apps") is False:
        # Ground truth says no planning apps — score 1.0 regardless of model tags.
        # Models sometimes tag governance/planning-committee motions as "planning"
        # which would otherwise be penalised for missing planning_application objects.
        planning_score = 1.0
    else:
        p_motions = [m for m in motions if m.tags and "planning" in m.tags]
        if not p_motions:
            # Planning expected but nothing tagged → penalise
            planning_score = 0.0 if expected.get("has_planning_apps") else 1.0
        else:
            planning_score = sum(1 for m in p_motions if m.planning_application) / len(p_motions)

    # ── total ─────────────────────────────────────────────────────────────────
    total = (
        WEIGHTS["meta"]     * meta
        + WEIGHTS["roster"] * roster
        + WEIGHTS["motions"]* motions_score
        + WEIGHTS["votes"]  * votes_score
        + WEIGHTS["planning"]* planning_score
    )

    return {
        "total":    round(total * 100, 1),
        "meta":     round(meta * 100, 1),
        "roster":   round(roster * 100, 1),
        "motions":  round(motions_score * 100, 1),
        "votes":    round(votes_score * 100, 1),
        "planning": round(planning_score * 100, 1),
        "n_motions": n,
        "error":    False,
    }


def score_agreement(results: dict[str, ExtractedMeeting | None]) -> dict:
    """Cross-model agreement score (0–100). Requires ≥2 successful models."""
    valid = {k: v for k, v in results.items() if v is not None}
    if len(valid) < 2:
        return {"total": 0.0, "skipped": True}

    # Date
    dates = {str(v.meeting_date) for v in valid.values() if v.meeting_date}
    date_ok = 1.0 if len(dates) == 1 else 0.0

    # Meeting type (case-insensitive)
    types = {(v.meeting_type or "").lower() for v in valid.values()}
    type_ok = 1.0 if len(types) == 1 else 0.0

    # Motion count stability (1 - coefficient of variation, clamped to 0)
    counts = [len(v.motions) for v in valid.values()]
    mu = statistics.mean(counts)
    cv = statistics.stdev(counts) / mu if len(counts) > 1 and mu > 0 else 0.0
    count_ok = max(0.0, 1.0 - cv)

    # Councillors Jaccard similarity
    name_sets = [
        frozenset(
            f"{c.given_name} {c.family_name}".strip().lower()
            for c in v.councillors_present
        )
        for v in valid.values()
    ]
    if any(name_sets):
        inter = name_sets[0].intersection(*name_sets[1:])
        union = name_sets[0].union(*name_sets[1:])
        jaccard = len(inter) / len(union) if union else 1.0
    else:
        jaccard = 1.0  # all empty → no disagreement

    total = (date_ok + type_ok + count_ok + jaccard) / 4

    return {
        "total":              round(total * 100, 1),
        "date_agree":         bool(date_ok),
        "type_agree":         bool(type_ok),
        "count_cv":           round(cv, 3),
        "councillors_jaccard": round(jaccard, 3),
    }


def combined_score(model_scores: dict[str, dict], agreement: dict) -> float:
    """Weighted model average plus agreement bonus (up to +5 points)."""
    valids = [s["total"] for s in model_scores.values() if not s.get("error")]
    if not valids:
        return 0.0
    avg = statistics.mean(valids)
    bonus = agreement.get("total", 0) / 100 * 5  # max +5 when perfect agreement
    return round(min(100.0, avg + bonus), 1)


# ---------------------------------------------------------------------------
# Generalisation warnings
# ---------------------------------------------------------------------------

def generalisation_warnings(
    by_pdf: dict[str, dict],
    prev_by_pdf: dict[str, dict] | None,
) -> list[str]:
    """
    Warn if the score improvement from this run is suspiciously concentrated
    on PDFs that were recently used in prompt development (i.e. appeared in
    data/model_comparison/ in the last 7 days).

    Also warn if any PDF regressed more than 2 standard deviations below the
    average delta.
    """
    if not prev_by_pdf or len(by_pdf) < 2:
        return []

    deltas = {
        pdf: by_pdf[pdf]["combined"] - prev_by_pdf[pdf]["combined"]
        for pdf in by_pdf if pdf in prev_by_pdf
    }
    if len(deltas) < 2:
        return []

    avg = statistics.mean(deltas.values())
    std = statistics.stdev(deltas.values()) if len(deltas) > 1 else 0.0

    # PDFs with recent model_comparison activity = recently used for prompt dev
    recent: set[str] = set()
    comp_dir = Path("data/model_comparison")
    if comp_dir.exists():
        cutoff = datetime.now(timezone.utc).timestamp() - 7 * 86400
        for f in comp_dir.glob("*.json"):
            if f.stat().st_mtime > cutoff:
                stem = f.stem.split("_")[0]
                recent.add(stem + ".pdf")

    warnings = []
    for pdf, delta in sorted(deltas.items(), key=lambda x: -abs(x[1])):
        z = (delta - avg) / std if std > 0 else 0.0
        is_recent = pdf in recent

        if z > 1.5 and is_recent and avg > 1:
            warnings.append(
                f"'{pdf}' improved {delta:+.1f} (avg {avg:+.1f}, z={z:.1f}) "
                f"— recently used in prompt dev, possible overfitting"
            )
        elif delta < avg - 2 * max(std, 1.0) and delta < -2:
            warnings.append(
                f"'{pdf}' regressed {delta:+.1f} while avg changed {avg:+.1f} — check this document"
            )

    if not warnings and len(recent & set(deltas.keys())) > 0 and avg > 3:
        # Subtle case: improvement exists but is evenly distributed
        warnings.append(
            f"Overall +{avg:.1f} improvement appears generalised across benchmark ✓"
        )

    return warnings


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _delta_str(current: float, prev: float | None) -> str:
    if prev is None:
        return ""
    d = current - prev
    if abs(d) < 0.5:
        return "[dim]±0[/dim]"
    color = "green" if d > 0 else "red"
    return f"[{color}]{d:+.1f}[/{color}]"


def print_report(run: dict, prev_run: dict | None, all_runs: list[dict] | None = None) -> None:
    prev_by_pdf = (prev_run or {}).get("by_pdf")

    sha = run["prompt_sha"]
    prev_sha = (prev_run or {}).get("prompt_sha", "")
    sha_changed = prev_sha and sha != prev_sha

    console.rule(
        f"[bold]Prompt Eval[/bold]  "
        f"[dim]SHA {sha}[/dim]"
        + (f"  ← [dim]{prev_sha}[/dim]" if sha_changed else "")
    )
    if prev_run:
        console.print(
            f"[dim]Comparing vs run at {prev_run['generated_at'][:19]}[/dim]"
            + ("  [yellow](same prompt — re-run)[/yellow]" if not sha_changed else "")
        )

    # ── Summary table ──────────────────────────────────────────────────────
    tbl = Table(box=box.SIMPLE, pad_edge=False, show_header=True)
    tbl.add_column("PDF", style="cyan", min_width=28)
    tbl.add_column("Score", justify="right", min_width=8)
    for dim in WEIGHTS:
        tbl.add_column(dim.capitalize()[:6], justify="right", min_width=7)
    tbl.add_column("Agree", justify="right", min_width=6)
    tbl.add_column("Motions", justify="right", min_width=7)

    all_combined = []
    for pdf, data in run["by_pdf"].items():
        prev_pdf = (prev_by_pdf or {}).get(pdf)
        combined = data["combined"]
        delta_s = _delta_str(combined, prev_pdf["combined"] if prev_pdf else None)

        valid_scores = [s for s in data["model_scores"].values() if not s.get("error")]
        avg = {dim: statistics.mean(s[dim] for s in valid_scores) for dim in WEIGHTS} if valid_scores else {}
        avg_motions = statistics.mean(s["n_motions"] for s in valid_scores) if valid_scores else 0

        tbl.add_row(
            pdf,
            f"{combined:.1f} {delta_s}",
            *[f"{avg.get(d, 0):.0f}" for d in WEIGHTS],
            f"{data['agreement']['total']:.0f}",
            f"{avg_motions:.1f}",
        )
        all_combined.append(combined)

    if all_combined:
        overall = round(statistics.mean(all_combined), 1)
        prev_overall = (prev_run or {}).get("overall", {}).get("total")
        delta_s = _delta_str(overall, prev_overall)
        tbl.add_section()
        tbl.add_row(
            "[bold]OVERALL[/bold]",
            f"[bold]{overall:.1f}[/bold] {delta_s}",
            *[""] * (len(WEIGHTS) + 2),
        )

    console.print(tbl)

    # ── Per-model breakdown ────────────────────────────────────────────────
    console.rule("[bold]Per-model scores[/bold]")
    for pdf, data in run["by_pdf"].items():
        mtbl = Table(
            title=f"[cyan]{pdf}[/cyan]",
            box=box.SIMPLE, pad_edge=False, title_style="bold",
        )
        mtbl.add_column("Model", min_width=12)
        mtbl.add_column("Score", justify="right", min_width=6)
        for dim in WEIGHTS:
            mtbl.add_column(dim.capitalize()[:6], justify="right", min_width=6)
        mtbl.add_column("Motions", justify="right", min_width=7)

        for model_label in run["models"]:
            s = data["model_scores"].get(model_label, {"error": True})
            is_ref = model_label not in run.get("scoring_models", SCORING_MODELS)
            label_col = f"[dim]{model_label} (unused)[/dim]" if is_ref else model_label
            if s.get("error"):
                mtbl.add_row(label_col, "[red]ERROR[/red]", *["–"] * (len(WEIGHTS) + 1))
            else:
                score_col = f"[dim]{s['total']:.1f}[/dim]" if is_ref else f"{s['total']:.1f}"
                mtbl.add_row(
                    label_col,
                    score_col,
                    *[f"{s[d]:.0f}" for d in WEIGHTS],
                    str(s["n_motions"]),
                )

        agree = data["agreement"]
        agree_detail = (
            f"  agreement {agree['total']:.0f}/100"
            + (f"  date={'✓' if agree.get('date_agree') else '✗'}"
               f"  type={'✓' if agree.get('type_agree') else '✗'}"
               f"  councillors={agree.get('councillors_jaccard', 0):.2f}"
               if not agree.get("skipped") else "  (single model)")
        )
        mtbl.caption = f"[dim]{agree_detail}[/dim]"
        console.print(mtbl)

        # ── Score history for this PDF ─────────────────────────────────────
        if all_runs:
            history: list[str] = []
            for r in all_runs:
                pdf_data = r.get("by_pdf", {}).get(pdf)
                if pdf_data:
                    scoring_totals = [
                        s["total"] for lbl, s in pdf_data.get("model_scores", {}).items()
                        if lbl in SCORING_MODELS and not s.get("error")
                    ]
                    if scoring_totals:
                        min_s = min(scoring_totals)
                        sha = r.get("prompt_sha", "")[:4]
                        history.append(f"{min_s:.0f}[dim]({sha})[/dim]")
            if history:
                console.print(f"  [dim]history (min model score): {' → '.join(history[-10:])}[/dim]\n")

    # ── Generalisation warnings ────────────────────────────────────────────
    if run.get("generalisation_warnings"):
        console.rule("[bold]Generalisation[/bold]")
        for w in run["generalisation_warnings"]:
            color = "yellow" if "possible overfitting" in w or "regressed" in w else "green"
            console.print(f"  [{color}]{w}[/{color}]")

    console.print()


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_run(run: dict, console_text: str) -> Path:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem = f"eval_{ts}"
    json_path = EVAL_DIR / f"{stem}.json"
    txt_path  = EVAL_DIR / f"{stem}.txt"
    latest_json = EVAL_DIR / "latest.json"
    latest_txt  = EVAL_DIR / "latest.txt"

    body = json.dumps(run, indent=2, default=str)
    json_path.write_text(body, encoding="utf-8")
    latest_json.write_text(body, encoding="utf-8")

    txt_path.write_text(console_text, encoding="utf-8")
    latest_txt.write_text(console_text, encoding="utf-8")

    return json_path


def load_latest() -> dict | None:
    p = EVAL_DIR / "latest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def load_all_runs() -> list[dict]:
    """Return all saved eval runs, oldest first, excluding latest.json (it's a symlink)."""
    runs = []
    for p in sorted(EVAL_DIR.glob("eval_*.json")):
        try:
            runs.append(json.loads(p.read_text()))
        except Exception:
            pass
    return runs


def print_history(runs: list[dict]) -> None:
    if not runs:
        console.print("[yellow]No eval history found. Run the eval first.[/yellow]")
        return

    # Collect all PDF names seen across runs
    all_pdfs: list[str] = []
    seen: set[str] = set()
    for r in runs:
        for pdf in r.get("by_pdf", {}):
            if pdf not in seen:
                all_pdfs.append(pdf)
                seen.add(pdf)

    tbl = Table(box=box.SIMPLE, pad_edge=False, show_header=True)
    tbl.add_column("#",        justify="right", style="dim", min_width=3)
    tbl.add_column("Date",     min_width=16)
    tbl.add_column("SHA",      min_width=9, style="dim")
    tbl.add_column("Models",   min_width=8, style="dim")
    tbl.add_column("Overall",  justify="right", min_width=8)
    for pdf in all_pdfs:
        tbl.add_column(pdf[:20], justify="right", min_width=10)

    prev_overall: float | None = None
    prev_sha = ""
    for i, run in enumerate(runs, 1):
        ts   = run.get("generated_at", "")[:16].replace("T", " ")
        sha  = run.get("prompt_sha", "?")
        models_s = ",".join(m[:1] for m in run.get("models", []))  # e.g. "H,S,O"
        overall  = run.get("overall", {}).get("total", 0.0)

        # Delta vs previous run
        if prev_overall is not None:
            d = overall - prev_overall
            if abs(d) < 0.5:
                delta_s = "[dim]±0[/dim]"
            else:
                color = "green" if d > 0 else "red"
                delta_s = f"[{color}]{d:+.1f}[/{color}]"
            overall_s = f"{overall:.1f} {delta_s}"
        else:
            overall_s = f"{overall:.1f}"

        # SHA change marker
        sha_s = sha if sha != prev_sha else f"[dim]{sha}[/dim]"

        # Per-PDF scores
        pdf_cols = []
        for pdf in all_pdfs:
            pdf_data = run.get("by_pdf", {}).get(pdf)
            if pdf_data:
                pdf_cols.append(f"{pdf_data['combined']:.1f}")
            else:
                pdf_cols.append("[dim]–[/dim]")

        tbl.add_row(str(i), ts, sha_s, models_s, overall_s, *pdf_cols)
        prev_overall = overall
        prev_sha = sha

    console.rule("[bold]Eval history[/bold]")
    console.print(tbl)
    console.print(f"[dim]{len(runs)} run(s) in {EVAL_DIR}[/dim]\n")


# ---------------------------------------------------------------------------
# Quick-mode sticky state
# ---------------------------------------------------------------------------

def load_quick_state() -> dict:
    if QUICK_STATE_PATH.exists():
        try:
            return json.loads(QUICK_STATE_PATH.read_text())
        except Exception:
            pass
    return {}


def save_quick_state(state: dict) -> None:
    QUICK_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


PASS_THRESHOLD = 95  # min individual scoring-model score required to move to the next PDF

def pick_quick_entry(entries: list[dict], last_score: float | None, current_fname: str | None) -> dict:
    """
    Sticky random selection:
    - If the weakest scoring model hasn't reached PASS_THRESHOLD, keep using this PDF.
    - Once the weakest model hits PASS_THRESHOLD (or there's no state), pick a different random PDF.
    Using the minimum model score (not combined) avoids the agreement bonus masking real gaps.
    """
    if current_fname and (last_score is None or last_score < PASS_THRESHOLD):
        match = next((e for e in entries if e["filename"] == current_fname), None)
        if match:
            return match
    # Need a new pick — avoid repeating the same one if there are alternatives
    candidates = [e for e in entries if e["filename"] != current_fname] or entries
    return random.choice(candidates)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate extraction prompt quality across benchmark PDFs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--quick",   action="store_true", help="Random PDF from benchmark, all 3 models (faster sanity check)")
    parser.add_argument("--compare", action="store_true", help="Show delta vs previous run")
    parser.add_argument("--show",    action="store_true", help="Print latest saved report, no API calls")
    parser.add_argument("--history", action="store_true", help="Show score history across all saved runs")
    parser.add_argument("--no-save", action="store_true", help="Don't write report to disk")
    args = parser.parse_args()

    all_runs = load_all_runs()

    if args.history:
        print_history(all_runs)
        return

    if args.show:
        prev = load_latest()
        if not prev:
            console.print("[red]No saved eval found — run without --show first.[/red]")
            raise SystemExit(1)
        print_report(prev, None, all_runs)
        return

    if not BENCHMARK_PATH.exists():
        console.print(f"[red]Benchmark not found: {BENCHMARK_PATH}[/red]")
        raise SystemExit(1)

    benchmark = json.loads(BENCHMARK_PATH.read_text())
    entries = benchmark["pdfs"]
    quick_state = {}
    if args.quick:
        quick_state = load_quick_state()
        current_fname = quick_state.get("current_pdf")
        last_score    = quick_state.get("last_score")

        # Saturation check: find the most recent score for every benchmark PDF
        # across all saved runs. If every PDF has passed PASS_THRESHOLD, the
        # benchmark is saturated — cycling adds no signal.
        latest_score_by_pdf: dict[str, float] = {}
        for r in reversed(all_runs):
            for fname, data in r.get("by_pdf", {}).items():
                if fname not in latest_score_by_pdf:
                    ms = {lbl: s for lbl, s in data.get("model_scores", {}).items() if lbl in SCORING_MODELS}
                    if ms and not any(s.get("error") for s in ms.values()):
                        latest_score_by_pdf[fname] = min(s["total"] for s in ms.values())

        all_fnames = {e["filename"] for e in entries}
        saturated = (
            all_fnames.issubset(latest_score_by_pdf)
            and all(latest_score_by_pdf[f] >= PASS_THRESHOLD for f in all_fnames)
        )
        if saturated:
            console.print(
                f"[green bold]Benchmark saturated[/green bold] — all {len(all_fnames)} PDFs "
                f"have every scoring model ≥{PASS_THRESHOLD}.\n"
                f"[dim]Add more PDFs to data/eval/benchmark.json to continue iterating, "
                f"or run [bold]python scripts/eval_prompt.py --compare[/bold] for a full final check.[/dim]"
            )
            return

        pick = pick_quick_entry(entries, last_score, current_fname)
        is_new = pick["filename"] != current_fname
        if is_new and current_fname:
            console.print(
                f"[green]✓ '{current_fname}' passed (all models ≥{PASS_THRESHOLD}) — moving to new PDF[/green]"
            )
        runs_on = 1 if is_new else quick_state.get("runs_on_current", 0) + 1
        status = f"run {runs_on} on this PDF" if runs_on > 1 else "first run"
        console.print(
            f"[dim]--quick: '{pick['filename']}' — {pick.get('label', '')}  ({status})[/dim]\n"
        )
        entries = [pick]
    models = [(lbl, mid) for lbl, mid in ALL_MODELS if lbl in SCORING_MODELS]
    model_labels = [lbl for lbl, _ in models]
    scoring_labels = model_labels
    ref_labels = [lbl for lbl, _ in ALL_MODELS if lbl not in SCORING_MODELS]

    prev_run = load_latest() if args.compare else None
    prompt_sha = hashlib.sha256(_SYSTEM_PROMPT.encode()).hexdigest()[:8]

    console.print(
        f"\nEvaluating [bold]{len(entries)} PDFs[/bold] × "
        f"[bold]{len(scoring_labels)} model{'s' if len(scoring_labels) > 1 else ''}[/bold]  "
        f"[dim]prompt SHA {prompt_sha}[/dim]\n"
    )

    by_pdf: dict[str, dict] = {}

    for entry in entries:
        fname      = entry["filename"]
        council    = entry.get("council", "cambridge")
        c_name     = entry.get("council_name", "City of Cambridge")
        expected   = entry.get("expected", {})
        label      = entry.get("label", fname)
        pdf_path   = Path("data/raw") / council / fname

        if not pdf_path.exists():
            console.print(f"  [yellow]skip {fname} — file not found[/yellow]")
            continue

        manifest_path = Path("data/raw") / council / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        date_hint = manifest.get(fname, {}).get("meeting_date")

        console.print(f"  [bold]{fname}[/bold]  [dim]{label}[/dim]")

        results, errors = run_extraction(pdf_path, c_name, date_hint, models)

        model_scores: dict[str, dict] = {}
        for lbl in model_labels:
            model_scores[lbl] = score_model(results.get(lbl), expected)
            s = model_scores[lbl]
            is_ref = lbl not in SCORING_MODELS
            if is_ref:
                status = f"[dim]✗ ERROR (unused)[/dim]" if s.get("error") else f"[dim]{s['total']:.0f} (unused)[/dim]"
                console.print(f"    [dim]{lbl:<14}[/dim] {status}")
            else:
                status = f"[red]✗ ERROR[/red]" if s.get("error") else f"[green]✓[/green] {s['total']:.0f}"
                console.print(f"    {lbl:<14} {status}")

        scoring_results = {lbl: r for lbl, r in results.items() if lbl in SCORING_MODELS}
        scoring_scores  = {lbl: s for lbl, s in model_scores.items() if lbl in SCORING_MODELS}
        agreement = score_agreement(scoring_results)
        combined  = combined_score(scoring_scores, agreement)
        console.print(f"    [bold]combined {combined:.1f}[/bold]  agreement {agreement['total']:.0f}\n")

        # Serialise extraction outputs so they can be read for prompt diagnosis
        extractions = {}
        for lbl, result in results.items():
            if result is not None:
                extractions[lbl] = json.loads(result.model_dump_json())

        by_pdf[fname] = {
            "label":        label,
            "combined":     combined,
            "model_scores": model_scores,
            "agreement":    agreement,
            "errors":       errors,
            "extractions":  extractions,
        }

    if not by_pdf:
        console.print("[red]No PDFs processed.[/red]")
        return

    overall = round(statistics.mean(d["combined"] for d in by_pdf.values()), 1)
    warnings = generalisation_warnings(by_pdf, (prev_run or {}).get("by_pdf"))

    run = {
        "generated_at":              datetime.now(timezone.utc).isoformat(),
        "prompt_sha":                prompt_sha,
        "models":                    model_labels,
        "scoring_models":            list(SCORING_MODELS),
        "overall":                   {"total": overall},
        "by_pdf":                    by_pdf,
        "generalisation_warnings":   warnings,
    }

    # Update sticky state for next --quick run
    if args.quick and by_pdf and not args.no_save:
        picked_fname = entries[0]["filename"]
        pdf_data = by_pdf.get(picked_fname, {})
        # Use minimum individual scoring-model score as the pass signal,
        # not combined (which is inflated by the agreement bonus).
        # Any scoring model that errored counts as 0 — a PDF with a partial
        # failure must not be treated as passed.
        model_scores_for_pdf = {
            lbl: s for lbl, s in pdf_data.get("model_scores", {}).items()
            if lbl in SCORING_MODELS
        }
        any_error = any(s.get("error") for s in model_scores_for_pdf.values())
        if any_error:
            min_model_score = 0.0
        else:
            scoring_totals = [s["total"] for s in model_scores_for_pdf.values()]
            min_model_score = min(scoring_totals) if scoring_totals else 0.0
        save_quick_state({
            "current_pdf":      picked_fname,
            "last_score":       min_model_score,
            "runs_on_current":  1 if picked_fname != quick_state.get("current_pdf") else quick_state.get("runs_on_current", 0) + 1,
        })

    print_report(run, prev_run, all_runs)

    if not args.no_save:
        path = save_run(run, console.export_text(clear=False))
        console.print(f"[dim]Saved → {path}[/dim]")
        console.print(f"[dim]     → {EVAL_DIR / 'latest.txt'} (plain text, readable by Claude)[/dim]\n")


if __name__ == "__main__":
    main()
