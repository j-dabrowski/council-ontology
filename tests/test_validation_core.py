"""
Unit tests for the pure logic in src/validation/core.py:
  - determine_status() — the PASS / REVIEW / FAIL gate itself
  - _classify_quotes() — three-tier quote matching (full / stripped / paraphrase)
  - compute_paraphrase_rate, compute_coverage, compute_inventory_agreement,
    compute_keyword_gaps — the metrics the gate is fed

All of these take plain strings/lists/dicts and return plain data — no DB
connection, no PDF, no network. That's deliberate: they're the part of the
eval framework that decides whether an extraction is trustworthy, and they
don't need any I/O to test.
"""
from src.validation.core import (
    GAP_KEYWORDS,
    _classify_quotes,
    compute_coverage,
    compute_inventory_agreement,
    compute_keyword_gaps,
    compute_paraphrase_rate,
    determine_status,
)


# ---------------------------------------------------------------------------
# determine_status — the PASS / REVIEW / FAIL gate
# ---------------------------------------------------------------------------

def test_status_fail_on_zero_quotes():
    assert determine_status(para_rate=0.0, cov_ratio=0.5, gap_rate=0.0, quote_count=0) == "FAIL"


def test_status_fail_on_low_completeness():
    assert determine_status(
        para_rate=0.0, cov_ratio=0.5, gap_rate=0.0, quote_count=10, completeness_rate=0.49,
    ) == "FAIL"


def test_status_fail_on_high_paraphrase_and_low_coverage():
    assert determine_status(
        para_rate=0.80, cov_ratio=0.01, gap_rate=0.0, quote_count=10, completeness_rate=1.0,
    ) == "FAIL"


def test_status_review_on_low_coverage_alone():
    assert determine_status(
        para_rate=0.1, cov_ratio=0.02, gap_rate=0.0, quote_count=10, completeness_rate=1.0,
    ) == "REVIEW"


def test_status_review_on_high_paraphrase_rate():
    assert determine_status(
        para_rate=0.50, cov_ratio=0.5, gap_rate=0.0, quote_count=10, completeness_rate=1.0,
    ) == "REVIEW"


def test_status_review_on_high_gap_rate():
    assert determine_status(
        para_rate=0.0, cov_ratio=0.5, gap_rate=0.40, quote_count=10, completeness_rate=1.0,
    ) == "REVIEW"


def test_status_review_on_moderate_completeness():
    assert determine_status(
        para_rate=0.0, cov_ratio=0.5, gap_rate=0.0, quote_count=10, completeness_rate=0.79,
    ) == "REVIEW"


def test_status_pass_on_clean_extraction():
    assert determine_status(
        para_rate=0.1, cov_ratio=0.5, gap_rate=0.1, quote_count=10, completeness_rate=1.0,
    ) == "PASS"


def test_status_agenda_skips_coverage_fail():
    # Agendas naturally have low coverage (recommendation text vs. full agenda) —
    # the coverage-based FAIL/REVIEW branches are skipped for document_type="agenda".
    # A non-agenda doc with this cov_ratio would hit the cov_ratio < 0.03 REVIEW branch.
    assert determine_status(
        para_rate=0.1, cov_ratio=0.001, gap_rate=0.1, quote_count=10,
        completeness_rate=1.0, document_type="agenda",
    ) == "PASS"


def test_status_agenda_still_fails_on_zero_quotes():
    assert determine_status(
        para_rate=0.0, cov_ratio=0.5, gap_rate=0.0, quote_count=0, document_type="agenda",
    ) == "FAIL"


# ---------------------------------------------------------------------------
# _classify_quotes — three-tier matching
# ---------------------------------------------------------------------------

SOURCE = "MOVED by Cr Smith, SECONDED by Cr Jones that the budget be approved. CARRIED."


def test_classify_full_match():
    quotes = [{"entity_table": "motions", "quote_text": "SECONDED by Cr Jones"}]
    [c] = _classify_quotes(quotes, SOURCE)
    assert c["match_type"] == "full"


def test_classify_stripped_match():
    # Word-split artefact: extra internal whitespace that a verbatim match won't
    # survive, but stripping non-alphanumerics recovers it.
    quotes = [{"entity_table": "motions", "quote_text": "SEC ONDED by Cr Jo nes"}]
    [c] = _classify_quotes(quotes, SOURCE)
    assert c["match_type"] == "stripped"


def test_classify_paraphrase_when_not_in_source():
    quotes = [{"entity_table": "motions", "quote_text": "this text does not appear anywhere"}]
    [c] = _classify_quotes(quotes, SOURCE)
    assert c["match_type"] == "paraphrase"
    assert c["norm_start"] is None and c["norm_end"] is None


# ---------------------------------------------------------------------------
# compute_paraphrase_rate
# ---------------------------------------------------------------------------

def test_paraphrase_rate_mixed():
    classified = [
        {"entity_table": "motions", "quote_text": "a", "match_type": "full"},
        {"entity_table": "motions", "quote_text": "b", "match_type": "stripped"},
        {"entity_table": "motions", "quote_text": "c", "match_type": "paraphrase", "partial_match": None},
        {"entity_table": "motions", "quote_text": "d", "match_type": "paraphrase", "partial_match": None},
    ]
    paraphrased, stripped, total, rate, examples = compute_paraphrase_rate(classified)
    assert (paraphrased, stripped, total) == (2, 1, 4)
    assert rate == 0.5
    assert len(examples) == 2


def test_paraphrase_rate_empty_is_zero_not_divide_by_zero():
    assert compute_paraphrase_rate([]) == (0, 0, 0, 0.0, [])


# ---------------------------------------------------------------------------
# compute_coverage
# ---------------------------------------------------------------------------

def test_coverage_full_span_covers_everything():
    classified = [{"norm_start": 0, "norm_end": len(SOURCE)}]
    assert compute_coverage(classified, SOURCE) == 1.0


def test_coverage_unmatched_quotes_contribute_nothing():
    classified = [{"norm_start": None, "norm_end": None}]
    assert compute_coverage(classified, SOURCE) == 0.0


def test_coverage_empty_window_is_zero():
    assert compute_coverage([], "") == 0.0


# ---------------------------------------------------------------------------
# compute_inventory_agreement
# ---------------------------------------------------------------------------

def test_inventory_agreement_both_zero_is_clean():
    result = compute_inventory_agreement({"inventory": {"motion_count": 0}}, {"motion_count": 0})
    assert result["motion_count"] == {"l1": 0, "extracted": 0, "ratio": 1.0, "flag": False}


def test_inventory_agreement_l1_zero_extracted_nonzero_flags():
    result = compute_inventory_agreement({"inventory": {"motion_count": 0}}, {"motion_count": 5})
    assert result["motion_count"]["flag"] is True
    assert result["motion_count"]["ratio"] == float("inf")


def test_inventory_agreement_within_tolerance_not_flagged():
    result = compute_inventory_agreement({"inventory": {"motion_count": 10}}, {"motion_count": 9})
    assert result["motion_count"]["flag"] is False


def test_inventory_agreement_outside_tolerance_flags():
    result = compute_inventory_agreement({"inventory": {"motion_count": 10}}, {"motion_count": 2})
    assert result["motion_count"]["flag"] is True


# ---------------------------------------------------------------------------
# compute_keyword_gaps
# ---------------------------------------------------------------------------

def test_keyword_gap_covered_by_matched_span():
    text = "MOVED by Cr Smith that the budget be approved."
    classified = [{"norm_start": 0, "norm_end": len(text)}]
    result = compute_keyword_gaps(classified, text, gap_keywords={"MOVED": r"\bMOVED\b"})
    assert result["total_hits"] == 1
    assert result["uncovered_hits"] == 0
    assert result["gap_rate"] == 0.0


def test_keyword_gap_uncovered_keyword_is_flagged():
    text = "MOVED by Cr Smith that the budget be approved."
    classified = []  # no matched spans at all
    result = compute_keyword_gaps(classified, text, gap_keywords={"MOVED": r"\bMOVED\b"})
    assert result["total_hits"] == 1
    assert result["uncovered_hits"] == 1
    assert result["gap_rate"] == 1.0
    assert result["gap_examples"][0]["keyword"] == "MOVED"


def test_keyword_gap_no_hits_is_zero_not_divide_by_zero():
    result = compute_keyword_gaps([], "no relevant keywords here", gap_keywords=GAP_KEYWORDS)
    assert result["total_hits"] == 0
    assert result["gap_rate"] == 0.0
