"""
Page rasterisation (docs/uplift/migration/05-verification.md Step 4, V-4):
every retained source PDF page rendered to an addressable image, keyed by
`(source_pdf, page)`.

This is a hard prerequisite the target's own ordering puts before any
vision-based verification layer (V-5, V-6, V-8, V-9's image half, V-10) —
none of those can start without it — and also supplies
`03-critic-agents.md`'s C-08 visual critic's rendering need on the other
side (panels, not source pages), sharing the same headless-render-to-image
tooling and `(pdf, page) -> path` addressing convention where practical.

Uses PyMuPDF (`fitz`), already a project dependency (`extract_text_from_pdf`
in `src/extraction/extractor.py` uses it as its own first-choice backend).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

DEFAULT_DPI = 150
DEFAULT_OUT_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "page_images"


@dataclass
class RasterizedPage:
    pdf_path: str      # as given, not resolved — the stable key half of (source_pdf, page)
    page_number: int   # 1-indexed, matching how a human reader cites a page
    image_path: Path
    width: int
    height: int


def image_path_for(pdf_path: Path, page_number: int, out_root: Path = DEFAULT_OUT_ROOT) -> Path:
    """The stable `(source_pdf, page) -> image path` convention, without
    rendering anything — for checking whether a page's image already
    exists, or building a reference to it, without a PDF open.

    Keyed by the PDF's own stem (already this project's unique per-document
    identifier — `data/raw/<council>/<stem>.pdf`) plus a zero-padded 1-
    indexed page number, so paths sort in page order on disk.
    """
    return out_root / pdf_path.stem / f"page-{page_number:04d}.png"


def rasterize_page(
    pdf_path: Path, page_number: int, out_root: Path = DEFAULT_OUT_ROOT, dpi: int = DEFAULT_DPI,
    force: bool = False,
) -> RasterizedPage:
    """Render one page (1-indexed) of `pdf_path` to a PNG. Idempotent: skips
    re-rendering if the image already exists and `force` is false — a page
    render is deterministic given the same PDF bytes and dpi, so a stable
    cache is safe, not stale.
    """
    dest = image_path_for(pdf_path, page_number, out_root)
    if dest.exists() and not force:
        cached = fitz.Pixmap(str(dest))  # reads pixel dimensions from the PNG directly
        return RasterizedPage(
            pdf_path=str(pdf_path), page_number=page_number, image_path=dest,
            width=cached.width, height=cached.height,
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(str(pdf_path)) as doc:
        if not (1 <= page_number <= doc.page_count):
            raise ValueError(
                f"page {page_number} out of range for {pdf_path} ({doc.page_count} pages)"
            )
        page = doc[page_number - 1]
        zoom = dpi / 72  # PDF points are 1/72 inch; fitz's default render is 72 dpi
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        pix.save(str(dest))
        return RasterizedPage(
            pdf_path=str(pdf_path), page_number=page_number, image_path=dest,
            width=pix.width, height=pix.height,
        )


def rasterize_pdf(
    pdf_path: Path, out_root: Path = DEFAULT_OUT_ROOT, dpi: int = DEFAULT_DPI, force: bool = False,
) -> list[RasterizedPage]:
    """Render every page of `pdf_path`. Returns one `RasterizedPage` per
    page, in order."""
    with fitz.open(str(pdf_path)) as doc:
        page_count = doc.page_count
    return [
        rasterize_page(pdf_path, n, out_root=out_root, dpi=dpi, force=force)
        for n in range(1, page_count + 1)
    ]
