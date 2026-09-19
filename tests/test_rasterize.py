"""
Tests for src/verification/rasterize.py (docs/uplift/migration/
05-verification.md Step 4, V-4). Builds a tiny synthetic 3-page PDF with
PyMuPDF itself rather than depending on a real corpus PDF being present.
"""
from pathlib import Path

import fitz
import pytest

from src.verification.rasterize import image_path_for, rasterize_page, rasterize_pdf


@pytest.fixture
def sample_pdf(tmp_path) -> Path:
    path = tmp_path / "sample.pdf"
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1}")
    doc.save(str(path))
    doc.close()
    return path


def test_image_path_for_is_stable_and_keyed_by_stem_and_page(tmp_path):
    pdf = Path("data/raw/cambridge/abc12345.pdf")
    p1 = image_path_for(pdf, 3, out_root=tmp_path)
    p2 = image_path_for(pdf, 3, out_root=tmp_path)
    assert p1 == p2
    assert "abc12345" in str(p1)
    assert "0003" in p1.name


def test_rasterize_page_writes_a_real_image(sample_pdf, tmp_path):
    out = tmp_path / "out"
    r = rasterize_page(sample_pdf, 1, out_root=out)
    assert r.image_path.exists()
    assert r.width > 0 and r.height > 0
    assert r.page_number == 1


def test_rasterize_page_is_idempotent_without_force(sample_pdf, tmp_path):
    out = tmp_path / "out"
    r1 = rasterize_page(sample_pdf, 1, out_root=out)
    mtime1 = r1.image_path.stat().st_mtime_ns
    r2 = rasterize_page(sample_pdf, 1, out_root=out)
    assert r2.image_path.stat().st_mtime_ns == mtime1
    assert r2.width == r1.width and r2.height == r1.height


def test_rasterize_page_force_overwrites(sample_pdf, tmp_path):
    out = tmp_path / "out"
    r1 = rasterize_page(sample_pdf, 1, out_root=out)
    mtime1 = r1.image_path.stat().st_mtime_ns
    r2 = rasterize_page(sample_pdf, 1, out_root=out, force=True)
    assert r2.image_path.stat().st_mtime_ns >= mtime1


def test_rasterize_page_out_of_range_raises(sample_pdf, tmp_path):
    with pytest.raises(ValueError):
        rasterize_page(sample_pdf, 99, out_root=tmp_path / "out")


def test_rasterize_pdf_renders_every_page_in_order(sample_pdf, tmp_path):
    out = tmp_path / "out"
    pages = rasterize_pdf(sample_pdf, out_root=out)
    assert len(pages) == 3
    assert [p.page_number for p in pages] == [1, 2, 3]
    for p in pages:
        assert p.image_path.exists()
