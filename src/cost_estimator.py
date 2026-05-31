"""
Shared cost estimation for all LLM pipeline stages.

Uses census.json char counts when available — avoids slow PDF re-reads.
Covers inventory (Level 1) and extraction (Levels 3b / 5).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CHARS_PER_TOKEN = 4

# ─── Inventory constants ────────────────────────────────────────────────────

INVENTORY_MAX_CHARS = 30_000          # 20k front + 10k back window
INVENTORY_OUTPUT_TOKENS_PER_DOC = 400  # small fixed schema

# ─── Extraction constants ───────────────────────────────────────────────────

EXTRACT_DEFAULT_MAX_CHARS = 80_000

# Output token estimates by census size bucket (calibrated on Cambridge corpus).
# The 64k-per-doc worst-case assumption overestimates by ~5×.
_EXTRACT_OUTPUT_BY_BUCKET: dict[str, int] = {
    "tiny":   2_500,
    "small":  6_000,
    "medium": 12_000,
    "large":  18_000,
    "failed": 0,
}
_EXTRACT_OUTPUT_FALLBACK = 12_000

# ─── Model pricing ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _ModelPricing:
    label: str
    input_per_mtok: float
    output_per_mtok: float


MODELS: dict[str, _ModelPricing] = {
    "haiku":        _ModelPricing("Haiku 4.5",          1.00,  5.00),
    "haiku-batch":  _ModelPricing("Haiku 4.5 (batch)",  0.50,  2.50),
    "sonnet":       _ModelPricing("Sonnet 4.6",          3.00, 15.00),
    "sonnet-batch": _ModelPricing("Sonnet 4.6 (batch)", 1.50,  7.50),
    "opus":         _ModelPricing("Opus 4.6",            5.00, 25.00),
    "opus-batch":   _ModelPricing("Opus 4.6 (batch)",   2.50, 12.50),
}


def model_key_from_string(model_id: str) -> str:
    """Map a model ID (e.g. 'claude-haiku-4-5-20251001') to a MODELS key."""
    lm = model_id.lower()
    if "haiku" in lm:
        return "haiku"
    if "sonnet" in lm:
        return "sonnet"
    if "opus" in lm:
        return "opus"
    return "haiku"


# ─── CostEstimate ───────────────────────────────────────────────────────────


@dataclass
class CostEstimate:
    stage: str            # "inventory" | "extract"
    model_key: str        # key into MODELS
    n_docs: int
    input_tokens: int
    output_tokens: int
    max_chars: int | None  # None = full document (multi-chunk)

    @property
    def model(self) -> _ModelPricing:
        return MODELS[self.model_key]

    def _cost(self, key: str) -> float:
        m = MODELS[key]
        return (
            self.input_tokens  / 1_000_000 * m.input_per_mtok
            + self.output_tokens / 1_000_000 * m.output_per_mtok
        )

    @property
    def standard_cost(self) -> float:
        return self._cost(self.model_key)

    @property
    def batch_cost(self) -> float | None:
        bk = self.model_key + "-batch"
        return self._cost(bk) if bk in MODELS else None


# ─── Census helpers ─────────────────────────────────────────────────────────


def load_census(census_path: Path | str = "data/census.json") -> dict[str, dict]:
    """Return {filename: record} from census.json, or {} if unavailable."""
    p = Path(census_path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {r["filename"]: r for r in data.get("documents", [])}
    except Exception:
        return {}


# ─── Prompt overhead ────────────────────────────────────────────────────────


def _inventory_overhead_tokens() -> int:
    try:
        txt = (
            Path(__file__).parent / "extraction" / "inventory_prompt.txt"
        ).read_text(encoding="utf-8")
        return len(txt) // CHARS_PER_TOKEN
    except Exception:
        return 1_500


def _extraction_overhead_tokens() -> int:
    try:
        from src.extraction.extractor import _SYSTEM_PROMPT
        return (len(_SYSTEM_PROMPT) + 120) // CHARS_PER_TOKEN
    except Exception:
        return 4_000


# ─── Estimators ─────────────────────────────────────────────────────────────


def estimate_inventory(
    pdfs: list[Path],
    census: dict[str, dict] | None = None,
) -> CostEstimate:
    """Estimate Level 1 inventory cost. Always Haiku."""
    if census is None:
        census = load_census()
    overhead = _inventory_overhead_tokens()
    total_input = 0
    for pdf in pdfs:
        raw_chars = census.get(pdf.name, {}).get("char_count", INVENTORY_MAX_CHARS)
        effective = min(raw_chars, INVENTORY_MAX_CHARS)
        total_input += effective // CHARS_PER_TOKEN + overhead
    total_output = len(pdfs) * INVENTORY_OUTPUT_TOKENS_PER_DOC
    return CostEstimate(
        stage="inventory",
        model_key="haiku",
        n_docs=len(pdfs),
        input_tokens=total_input,
        output_tokens=total_output,
        max_chars=INVENTORY_MAX_CHARS,
    )


def estimate_extraction(
    pdfs: list[Path],
    max_chars: int | None,
    model_key: str,
    census: dict[str, dict] | None = None,
) -> CostEstimate:
    """
    Estimate extraction (Level 3b / Level 5) cost.

    max_chars=None means full-document multi-chunk extraction.
    """
    if census is None:
        census = load_census()
    overhead = _extraction_overhead_tokens()
    total_input = 0
    total_output = 0
    for pdf in pdfs:
        rec = census.get(pdf.name, {})
        raw_chars = rec.get("char_count") or EXTRACT_DEFAULT_MAX_CHARS
        size_bucket = rec.get("size_bucket", "")
        if max_chars is None:
            # Multi-chunk: ceiling division
            n_chunks = max(1, (raw_chars + EXTRACT_DEFAULT_MAX_CHARS - 1) // EXTRACT_DEFAULT_MAX_CHARS)
            total_input += raw_chars // CHARS_PER_TOKEN + overhead * n_chunks
        else:
            effective = min(raw_chars, max_chars)
            total_input += effective // CHARS_PER_TOKEN + overhead
            n_chunks = 1
        out_per_chunk = _EXTRACT_OUTPUT_BY_BUCKET.get(size_bucket, _EXTRACT_OUTPUT_FALLBACK)
        total_output += out_per_chunk * n_chunks
    return CostEstimate(
        stage="extract",
        model_key=model_key,
        n_docs=len(pdfs),
        input_tokens=total_input,
        output_tokens=total_output,
        max_chars=max_chars,
    )


# ─── Display ────────────────────────────────────────────────────────────────


def format_preflight(estimate: CostEstimate) -> str:
    """Compact cost summary for display immediately before a command runs."""
    if estimate.max_chars is None:
        window = "full document"
    elif estimate.max_chars >= 1000:
        window = f"{estimate.max_chars // 1000}k chars"
    else:
        window = f"{estimate.max_chars:,} chars"

    header = (
        f"[dim]Cost estimate[/dim]  "
        f"[bold]{estimate.stage}[/bold] · "
        f"{estimate.model.label} · {window}"
    )
    tokens_line = (
        f"  {estimate.n_docs:,} doc{'s' if estimate.n_docs != 1 else ''}  ·  "
        f"input ~{estimate.input_tokens // 1_000:,}k tokens  ·  "
        f"output ~{estimate.output_tokens // 1_000:,}k tokens"
    )
    cost_parts = [
        f"Standard [bold green]${estimate.standard_cost:.2f}[/bold green]"
    ]
    if estimate.batch_cost is not None:
        cost_parts.append(
            f"Batch [bold green]${estimate.batch_cost:.2f}[/bold green]"
            f"[dim] (50% off, up to 24h)[/dim]"
        )
    note = ""
    if estimate.stage == "inventory":
        note = "  [dim](cached responses reused free — actual may be lower)[/dim]"
    cost_line = "  " + "  ·  ".join(cost_parts) + note

    return "\n".join([header, tokens_line, cost_line])
