#!/usr/bin/env python3
"""
Level 1 LLM inventory: one cheap Haiku call per document.

The inventory isn't trying to count every motion in the document. It's trying to
answer: what kind of document is this, and roughly what does it contain?

Text window: first 20,000 chars + last 10,000 chars. For documents under 30,000
chars, the full text is used. For longer documents, the middle section is omitted.

LLM responses are cached by document hash + prompt version in .cache/llm_responses/.
Re-running with the same prompt version costs nothing for already-cached documents.

Outputs:
  data/inventories/{stem}.json   — per-document inventory
  data/inventories/summary.json  — corpus-wide aggregate

Usage:
    python scripts/inventory.py cambridge
    python scripts/inventory.py cambridge --limit 10
    python scripts/inventory.py cambridge --force
    council inventory cambridge [--limit N] [--force] [--quiet]
"""

import argparse
import hashlib
import json
import logging
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import anthropic
from pydantic import BaseModel, Field, field_validator
from pypdf import PdfReader
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

console = Console()
_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants and paths
# ---------------------------------------------------------------------------

FRONT_CHARS = 20_000
BACK_CHARS = 10_000
_SEPARATOR = "\n\n[... middle section omitted ...]\n\n"

INVENTORY_MODEL = "claude-haiku-4-5-20251001"
PROMPT_VERSION = "inventory-v1"
MAX_CONCURRENT = 20

INVENTORIES_DIR = Path("data/inventories")
CACHE_DIR = Path(".cache/llm_responses")
CENSUS_PATH = Path("data/census.json")

_INVENTORY_PROMPT = (
    Path(__file__).parent.parent / "src" / "extraction" / "inventory_prompt.txt"
).read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------

class DocumentInventory(BaseModel):
    meeting_date: Optional[str] = None
    meeting_type: Optional[str] = None
    section_headings: list[str] = Field(default_factory=list)
    motion_count: int = 0
    planning_count: int = 0
    interest_count: int = 0
    petition_count: int = 0
    budget_item_count: int = 0
    other_content: Optional[str] = None

    @field_validator(
        "motion_count", "planning_count", "interest_count", "petition_count", "budget_item_count",
        mode="before",
    )
    @classmethod
    def _coerce_int(cls, v):
        if v is None:
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    @field_validator("section_headings", mode="before")
    @classmethod
    def _coerce_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        return list(v)


# ---------------------------------------------------------------------------
# LLM response cache
# ---------------------------------------------------------------------------

def _cache_path(pdf_path: Path) -> Path:
    h = hashlib.sha256(pdf_path.read_bytes()).hexdigest()[:16]
    return CACHE_DIR / f"{h}_{PROMPT_VERSION}.json"


def _load_cache(pdf_path: Path) -> str | None:
    try:
        p = _cache_path(pdf_path)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))["response"]
    except Exception:
        pass
    return None


def _save_cache(pdf_path: Path, response: str) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        p = _cache_path(pdf_path)
        p.write_text(
            json.dumps(
                {"response": response, "cached_at": datetime.now(timezone.utc).isoformat()},
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        _log.warning("Cache write failed for %s: %s", pdf_path.name, exc)


# ---------------------------------------------------------------------------
# Text window
# ---------------------------------------------------------------------------

def _extract_text(pdf_path: Path) -> str | None:
    try:
        reader = PdfReader(str(pdf_path))
        parts = [t for page in reader.pages if (t := page.extract_text())]
        return "\n\n".join(parts)
    except Exception:
        return None


def _build_window(text: str) -> tuple[str, bool]:
    """Return (window_text, was_truncated)."""
    if len(text) <= FRONT_CHARS + BACK_CHARS:
        return text, False
    return text[:FRONT_CHARS] + _SEPARATOR + text[-BACK_CHARS:], True


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

_client: anthropic.Anthropic | None = None
_client_lock = threading.Lock()


def _get_client() -> anthropic.Anthropic:
    global _client
    with _client_lock:
        if _client is None:
            _client = anthropic.Anthropic()
    return _client


def _call_api(window: str) -> str:
    @retry(
        retry=retry_if_exception_type((anthropic.APIConnectionError, anthropic.APIStatusError)),
        wait=wait_exponential(multiplier=1, min=4, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _do() -> str:
        msg = _get_client().messages.create(
            model=INVENTORY_MODEL,
            max_tokens=1_024,
            system=_INVENTORY_PROMPT,
            messages=[{"role": "user", "content": window}],
        )
        return msg.content[0].text

    return _do()


def _parse_response(raw: str) -> DocumentInventory:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw.strip(), flags=re.MULTILINE)
    return DocumentInventory.model_validate_json(raw)


# ---------------------------------------------------------------------------
# Census cross-reference
# ---------------------------------------------------------------------------

def _compare_census(
    inventory: DocumentInventory,
    census_record: dict | None,
    window_truncated: bool,
) -> dict:
    if census_record is None:
        return {"available": False, "flags": []}

    est_motions = census_record.get("estimated_motions", 0)
    est_planning = census_record.get("estimated_planning_items", 0)
    est_interests = census_record.get("estimated_interest_declarations", 0)

    flags: list[str] = []

    # Overcounting is suspicious regardless of window size
    if est_motions > 5 and inventory.motion_count > est_motions * 2:
        flags.append("l1_overcounts_motions")

    # For non-truncated docs (full text sent), significant mismatch in either direction
    if not window_truncated and est_motions > 5:
        ratio = inventory.motion_count / est_motions
        if ratio < 0.4 or ratio > 2.0:
            flags.append("l1_mismatch_full_doc")

    return {
        "available": True,
        "census_estimated_motions": est_motions,
        "census_estimated_planning": est_planning,
        "census_estimated_interests": est_interests,
        "window_truncated": window_truncated,
        "flags": flags,
    }


# ---------------------------------------------------------------------------
# Per-document processing
# ---------------------------------------------------------------------------

def _process_one(pdf_path: Path, census_record: dict | None) -> dict:
    base = {
        "filename": pdf_path.name,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }

    text = _extract_text(pdf_path)
    if text is None:
        return {**base, "status": "error", "error": "PDF text extraction failed"}
    if not text.strip():
        return {**base, "status": "error", "error": "PDF text is empty"}

    window, truncated = _build_window(text)

    raw = _load_cache(pdf_path)
    cache_hit = raw is not None
    if raw is None:
        raw = _call_api(window)
        _save_cache(pdf_path, raw)

    inventory = _parse_response(raw)
    comparison = _compare_census(inventory, census_record, truncated)

    return {
        **base,
        "status": "ok",
        "cache_hit": cache_hit,
        "full_text_chars": len(text),
        "text_window_chars": len(window),
        "window_truncated": truncated,
        "inventory": inventory.model_dump(),
        "census_comparison": comparison,
    }


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _write_summary() -> None:
    """Build summary from all inventory files on disk (not just the current run)."""
    all_records: list[dict] = []
    for p in sorted(INVENTORIES_DIR.glob("*.json")):
        if p.name == "summary.json":
            continue
        try:
            all_records.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass

    ok = [r for r in all_records if r.get("status") == "ok"]
    errors = [r for r in all_records if r.get("status") != "ok"]

    type_counts: dict[str, int] = {}
    for r in ok:
        mt = r.get("inventory", {}).get("meeting_type") or "unknown"
        type_counts[mt] = type_counts.get(mt, 0) + 1

    def _avg(key: str) -> float:
        vals = [r["inventory"].get(key, 0) for r in ok if "inventory" in r]
        return round(sum(vals) / len(vals), 1) if vals else 0.0

    flagged = [
        {"filename": r["filename"], "flags": r["census_comparison"]["flags"]}
        for r in ok
        if r.get("census_comparison", {}).get("flags")
    ]

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_inventoried": len(all_records),
        "total_ok": len(ok),
        "total_errors": len(errors),
        "meeting_type_distribution": dict(sorted(type_counts.items(), key=lambda x: -x[1])),
        "average_counts": {
            "motions": _avg("motion_count"),
            "planning": _avg("planning_count"),
            "interests": _avg("interest_count"),
            "petitions": _avg("petition_count"),
            "budget_items": _avg("budget_item_count"),
        },
        "flagged_documents": flagged,
    }

    INVENTORIES_DIR.mkdir(parents=True, exist_ok=True)
    (INVENTORIES_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def run(args) -> None:
    council_key: str = args.council
    limit: int | None = getattr(args, "limit", None)
    force: bool = getattr(args, "force", False)
    quiet: bool = getattr(args, "quiet", False)

    raw_dir = Path("data/raw") / council_key
    if not raw_dir.exists():
        console.print(f"[red]No raw directory for '{council_key}'. Run scrape first.[/red]")
        raise SystemExit(1)

    # Load census for cross-referencing
    census_by_filename: dict[str, dict] = {}
    if CENSUS_PATH.exists():
        try:
            data = json.loads(CENSUS_PATH.read_text(encoding="utf-8"))
            for rec in data.get("documents", []):
                census_by_filename[rec["filename"]] = rec
        except Exception:
            pass
    if not census_by_filename:
        console.print(
            "[yellow]No census data found. Run 'council census' first for cross-referencing.[/yellow]"
        )

    all_pdfs = sorted(raw_dir.glob("*.pdf"))
    if not all_pdfs:
        console.print(f"[yellow]No PDFs found in {raw_dir}.[/yellow]")
        return

    # Incremental: skip completed inventories unless --force
    to_process: list[Path] = []
    already_done = 0
    for pdf in all_pdfs:
        inv_path = INVENTORIES_DIR / f"{pdf.stem}.json"
        if not force and inv_path.exists():
            try:
                if json.loads(inv_path.read_text(encoding="utf-8")).get("status") == "ok":
                    already_done += 1
                    continue
            except Exception:
                pass
        to_process.append(pdf)

    if not force and already_done:
        console.print(
            f"[dim]Incremental: {already_done} cached, {len(to_process)} to process[/dim]"
        )

    if limit:
        to_process = to_process[:limit]

    if not to_process:
        console.print("[green]All inventories are up-to-date. Use --force to re-run.[/green]")
        _write_summary()
        return

    console.print(
        f"[dim]Model: {INVENTORY_MODEL}  |  Prompt: {PROMPT_VERSION}  |  "
        f"Max concurrent: {MAX_CONCURRENT}[/dim]"
    )
    INVENTORIES_DIR.mkdir(parents=True, exist_ok=True)

    n_ok = 0
    n_error = 0
    n_cache = 0
    results: list[dict] = []

    n_total = len(to_process)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        disable=quiet,
    ) as progress:
        task = progress.add_task(f"Inventorying {n_total} PDFs…", total=n_total)

        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as pool:
            futures = {
                pool.submit(_process_one, pdf, census_by_filename.get(pdf.name)): pdf
                for pdf in to_process
            }
            n_completed = 0
            for fut in as_completed(futures):
                pdf = futures[fut]
                try:
                    record = fut.result()
                except Exception as exc:
                    record = {
                        "filename": pdf.name,
                        "status": "error",
                        "error": str(exc),
                        "scanned_at": datetime.now(timezone.utc).isoformat(),
                    }

                inv_path = INVENTORIES_DIR / f"{pdf.stem}.json"
                inv_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

                if record["status"] == "ok":
                    n_ok += 1
                    if record.get("cache_hit"):
                        n_cache += 1
                else:
                    n_error += 1
                    if not quiet:
                        console.print(
                            f"  [red]✗[/red]  {pdf.name}: {record.get('error', 'unknown error')}"
                        )

                results.append(record)
                n_completed += 1
                remaining = n_total - n_completed
                progress.update(
                    task,
                    advance=1,
                    description=(
                        f"Inventorying {n_total} PDFs… ({remaining} remaining)"
                        if remaining > 0
                        else f"Inventorying {n_total} PDFs… done"
                    ),
                )

    _write_summary()

    api_calls = n_ok - n_cache
    console.print(
        f"[bold]Done:[/bold] {n_ok} ok "
        f"({n_cache} cache hits, {api_calls} API calls)"
        + (f", [red]{n_error} errors[/red]" if n_error else "")
    )
    if not quiet:
        console.print(f"[dim]→ {INVENTORIES_DIR}[/dim]")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Level 1 LLM inventory: one cheap Haiku call per document.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("council", help="Council key (e.g. cambridge)")
    parser.add_argument("--limit", "-n", type=int, default=None, metavar="N",
                        help="Process at most N PDFs")
    parser.add_argument("--force", action="store_true",
                        help="Re-run even if inventory already exists (cached LLM responses still reused)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress progress output")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
