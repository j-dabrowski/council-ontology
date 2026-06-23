"""
Re-import LLM extraction responses from the local archive into the database.

The archive is written automatically during every extraction run (sync or batch).
Use this script to rebuild the database from archived responses without making
any new API calls.

Usage (via CLI):
    council archive-import cambridge <run_id> [--force]

Usage (standalone):
    python scripts/archive_import.py cambridge <run_id> [--force]

Archive location: data/llm_archive/
List available runs: council archive-status cambridge
"""
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import json_repair
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

console = Console()


def run(
    council: str,
    run_id: str,
    force: bool = False,
    data_dir: Path = Path("data"),
) -> None:
    archive_dir = data_dir / "llm_archive" / run_id
    manifest_path = archive_dir / "manifest.json"

    if not manifest_path.exists():
        console.print(f"[red]Archive manifest not found: {manifest_path}[/red]")
        console.print("[dim]List available runs: council archive-status cambridge[/dim]")
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text())
    archive_council = manifest.get("council")
    if archive_council and archive_council != council:
        console.print(
            f"[yellow]Warning: archive is for council '{archive_council}', "
            f"importing into '{council}'[/yellow]"
        )

    chunk_files = sorted(
        f for f in archive_dir.glob("*.json") if f.name != "manifest.json"
    )
    if not chunk_files:
        console.print(f"[red]No chunk files found in {archive_dir}[/red]")
        sys.exit(1)

    # Load and group chunks by stem (custom_id format: {stem}__c{i}of{n})
    by_stem: dict[str, list] = defaultdict(list)
    unreadable = 0
    for cf in chunk_files:
        try:
            entry = json.loads(cf.read_text())
        except Exception as exc:
            console.print(f"  [yellow]⚠[/yellow] Could not read {cf.name}: {exc}")
            unreadable += 1
            continue
        cid = entry.get("custom_id", cf.stem)
        stem = cid.split("__c")[0] if "__c" in cid else cf.stem
        by_stem[stem].append(entry)

    for stem in by_stem:
        by_stem[stem].sort(key=lambda e: e.get("chunk_idx", 0))

    console.print(
        f"[dim]{len(chunk_files)} chunk files → {len(by_stem)} documents"
        + (f" ({unreadable} unreadable)" if unreadable else "")
        + f"[/dim]"
    )

    from src.extraction.extractor import (
        _merge_chunk_results,
        _parse_date_from_text,
        extract_text_from_pdf,
        save_extraction,
    )
    from src.extraction.schemas import ExtractedMeeting
    from src.models import Council as _Council
    from src.models import Meeting as _Meeting
    from src.storage.database import init_db, make_session_factory

    engine = init_db()
    session = make_session_factory(engine)()

    try:
        from src.cli import COUNCILS
        short_name = COUNCILS[council]["short_name"] if council in COUNCILS else council
    except (ImportError, KeyError):
        short_name = council

    council_row = session.query(_Council).filter_by(short_name=short_name).first()
    if not council_row:
        console.print(f"[red]Council not found in DB: {short_name}[/red]")
        console.print("[dim]Run 'council extract' at least once first to register the council.[/dim]")
        sys.exit(1)
    council_id = council_row.id
    council_full_name = council_row.name

    raw_dir = data_dir / "raw" / council
    manifest_file = raw_dir / "manifest.json"
    pdf_manifest = json.loads(manifest_file.read_text()) if manifest_file.exists() else {}

    succeeded = 0
    failed = 0
    skipped = 0
    failures: list[dict] = []

    console.print(Panel(
        f"Archive import: [bold]{len(by_stem)}[/bold] documents · "
        f"[bold]{council}[/bold] · run [cyan]{run_id}[/cyan]",
        style="blue",
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Importing...", total=len(by_stem))

        for stem, chunk_entries in sorted(by_stem.items()):
            pdf_path_str = chunk_entries[0].get("pdf_path", f"data/raw/{council}/{stem}.pdf")
            pdf_path = Path(pdf_path_str)
            pdf_name = pdf_path.name

            progress.update(task, description=f"[cyan]{pdf_name}[/cyan]")

            if not force:
                existing = session.query(_Meeting).filter_by(
                    minutes_pdf_path=str(pdf_path)
                ).first()
                if existing:
                    skipped += 1
                    progress.advance(task)
                    continue

            # Parse raw responses for each chunk
            parsed_chunks: list[ExtractedMeeting] = []
            chunk_failed = False
            for entry in chunk_entries:
                if entry.get("status") == "error" or not entry.get("raw_response"):
                    console.print(
                        f"  [red]✗[/red] {pdf_name} "
                        f"[chunk {entry.get('chunk_idx', '?')}]: archived as error"
                    )
                    chunk_failed = True
                    break

                raw = entry["raw_response"]
                # Strip markdown fences (same as extraction path)
                raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
                raw = re.sub(r"\s*```$", "", raw.strip(), flags=re.MULTILINE)

                try:
                    parsed = ExtractedMeeting.model_validate_json(raw)
                except Exception:
                    repaired = json_repair.repair_json(raw)
                    try:
                        parsed = ExtractedMeeting.model_validate_json(repaired)
                        console.print(
                            f"  [yellow]⚠[/yellow] {pdf_name}: JSON repaired "
                            f"(chunk {entry.get('chunk_idx', '?')})"
                        )
                    except Exception as exc:
                        console.print(f"  [red]✗[/red] {pdf_name}: parse failed: {exc}")
                        chunk_failed = True
                        failures.append({"filename": pdf_name, "error": str(exc)})
                        break
                parsed_chunks.append(parsed)

            if chunk_failed or not parsed_chunks:
                failed += 1
                progress.advance(task)
                continue

            # Apply chunk-0 metadata overrides (mirrors MinutesExtractor logic)
            date_hint = chunk_entries[0].get("meeting_date_hint")
            base = parsed_chunks[0]
            overrides: dict = {}
            if council_full_name and not base.council_name:
                overrides["council_name"] = council_full_name
            if not base.meeting_date and date_hint:
                try:
                    overrides["meeting_date"] = date.fromisoformat(date_hint)
                except ValueError:
                    pass
            if overrides:
                parsed_chunks[0] = base.model_copy(update=overrides)

            extracted = (
                _merge_chunk_results(parsed_chunks)
                if len(parsed_chunks) > 1
                else parsed_chunks[0]
            )

            # Re-read PDF text for provenance (char-offset resolution)
            raw_text: "str | None" = None
            if pdf_path.exists():
                try:
                    raw_text = extract_text_from_pdf(pdf_path)
                except Exception as exc:
                    console.print(
                        f"  [yellow]⚠[/yellow] {pdf_name}: could not re-read PDF ({exc}); "
                        "provenance incomplete"
                    )
            else:
                console.print(
                    f"  [yellow]⚠[/yellow] {pdf_name}: PDF not found; provenance incomplete"
                )

            if not extracted.meeting_date and not date_hint and raw_text:
                parsed_date = _parse_date_from_text(raw_text)
                if parsed_date:
                    extracted = extracted.model_copy(update={"meeting_date": parsed_date})

            meta = pdf_manifest.get(pdf_name, {})
            doc_type = chunk_entries[0].get("document_type") or meta.get("document_type")

            try:
                meeting_id = save_extraction(
                    session,
                    council_id,
                    extracted,
                    pdf_path if pdf_path.exists() else None,
                    text=raw_text,
                    pdf_url=meta.get("source_url"),
                    document_type=doc_type,
                )
                console.print(
                    f"  [green]✓[/green] {pdf_name} → meeting {meeting_id} "
                    f"({extracted.meeting_date}, {len(extracted.motions)} motions)"
                )
                succeeded += 1
            except Exception as exc:
                session.rollback()
                console.print(f"  [red]✗[/red] {pdf_name}: {exc}")
                failed += 1
                failures.append({"filename": pdf_name, "error": str(exc)})
            finally:
                progress.advance(task)

    session.close()
    console.print(
        f"\n[bold]Done:[/bold] {succeeded} imported, {failed} failed, {skipped} skipped"
    )

    # Mark run as imported in manifest and index
    now = datetime.now(timezone.utc).isoformat()
    manifest["imported"] = True
    manifest["imported_at"] = now
    manifest_path.write_text(json.dumps(manifest, indent=2))

    index_file = data_dir / "llm_archive" / "index.json"
    if index_file.exists():
        try:
            index = json.loads(index_file.read_text())
            for entry in index:
                if entry.get("run_id") == run_id:
                    entry["imported"] = True
                    entry["imported_at"] = now
                    break
            index_file.write_text(json.dumps(index, indent=2))
        except Exception as exc:
            console.print(f"[yellow]Warning: could not update archive index: {exc}[/yellow]")

    if failures:
        console.print("\n[bold]Failures:[/bold]")
        for f in failures:
            console.print(f"  {f['filename']}: {f['error']}")


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(
        description="Re-import LLM extraction responses from local archive into DB"
    )
    p.add_argument("council", help="Council key (e.g. cambridge)")
    p.add_argument("run_id", help="Archive run ID (use 'council archive-status' to list)")
    p.add_argument("--force", action="store_true", help="Re-import already-extracted docs")
    p.add_argument("--data-dir", default="data", help="Root data directory (default: data)")
    args = p.parse_args()
    run(args.council, args.run_id, force=args.force, data_dir=Path(args.data_dir))


if __name__ == "__main__":
    main()
