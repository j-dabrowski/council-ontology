"""Tests for src/privacy.py -- the pattern-based redactor for private
individuals' names in planning quotes (docs/frontend/RECORD_PAGE_PLAN.md
B.1, Step 2).

Hermetic by design (docs/TESTING.md -- nothing in tests/ touches
data/council.db, which is gitignored and absent from CI). The real
"3,000-quote sample" measurement RECORD_PAGE_PLAN.md's Step 2 asks for
runs separately, against the live corpus, via
scripts/measure_private_name_patterns.py -- its output is reported by
hand, not committed, because committing a fixture of real quotes would
recreate the exact privacy problem this redactor exists to fix. What's
committed here is a representative set of every *shape* that script
found in the real data (newline-separated Owner:/Applicant:, the
space-separated ALL-CAPS Landowner:/Applicant: run seen in older-format
minutes, plural Owners:, a bare standalone title), built from invented
names rather than real residents.
"""
from __future__ import annotations

from src.privacy import PLACEHOLDER, contains_private_name_pattern, redact_private_names

# One example per shape actually found in the corpus
# (RECORD_PAGE_PLAN.md A.1 and this step's real-corpus remeasurement),
# reproduced with invented names.
LABELLED_SAMPLES = [
    "Application: 100DA - 2012\nOwner: Mr John Smith & Ms Jane Smith\nApplicant: Mr John Smith & Ms Jane Smith",
    "Application: 0103DA-2012\nOwner: Mr A J Testperson\nApplicant: Pure Base Living",
    "Application: 60DA-2012\nOwner: Michael and Vanessa Sampleford\nApplicant: Fictional Architects",
    "Application: 500DA-2011\nOwners: I Vanderplaas\nApplicant: Example Exclusive Homes",
    (
        "BA/DA REFERENCE: 60DA-2009 LANDOWNER: Dr S A Placeholder APPLICANT: "
        "Delstrat Pty Ltd T/As Seacrest Homes ZONING: Residential R12.5 "
        "LAND AREA: 1191m2 USE CLASS: Dwelling (single): 'P' (permitted)"
    ),
    (
        "BA/DA REFERENCE: 35DA-2007 LANDOWNER: Example Property Investments Pty Ltd "
        "APPLICANT: Greg Sample & Associates acting for Fictional Bank "
        "ZONING: District Centre USE CLASS: Office"
    ),
]

TITLE_ONLY_SAMPLES = [
    "Mr Smith raised an objection about the fence height.",
    "The application was supported by Dr Placeholder's written submission.",
    "Mrs Testperson and Ms Sampleford both spoke against the proposal.",
]

# The documented limit (B.1): no label, no title.
UNCAUGHT_BARE_NAMES = [
    "The objection was lodged by Peter Northcott, a nearby resident.",
    "Council received a submission from Gillian Sampleford regarding overshadowing.",
]


# The invented name (or its surname) that should disappear from each
# entry in LABELLED_SAMPLES once redacted.
LABELLED_SAMPLE_NAMES = [
    "Smith",
    "Testperson",
    "Sampleford",
    "Vanderplaas",
    "Placeholder",
    "Sample",
]


def test_owner_applicant_landowner_label_lines_are_redacted():
    for text, name in zip(LABELLED_SAMPLES, LABELLED_SAMPLE_NAMES):
        redacted = redact_private_names(text)
        assert PLACEHOLDER in redacted, f"no placeholder in: {redacted!r}"
        assert name not in redacted, f"{name!r} survived redaction in: {redacted!r}"
        # The whole labelled span -- label, colon and value -- is gone,
        # not just the value (RECORD_PAGE_PLAN.md Step 3's payload test
        # requires no "Owner:"/"Applicant:" string survive anywhere).
        assert "Owner:" not in redacted and "Owners:" not in redacted
        assert "Applicant:" not in redacted
        assert "LANDOWNER:" not in redacted.upper()
        # A boundary label that ISN'T one of the redacted fields is left
        # alone -- only OWNER/LANDOWNER/APPLICANT values are stripped.
        assert "Application:" in redacted or "APPLICATION" in redacted or "REFERENCE" in redacted


def test_redaction_keeps_non_name_field_content_untouched():
    redacted = redact_private_names(LABELLED_SAMPLES[4])
    assert "BA/DA REFERENCE: 60DA-2009" in redacted
    assert "ZONING: Residential R12.5" in redacted
    assert "LAND AREA: 1191m2" in redacted
    assert "USE CLASS: Dwelling (single): 'P' (permitted)" in redacted
    # Two adjacent labelled fields stay properly spaced apart -- the
    # whitespace between them must survive redaction, not get glued into
    # a removed span (a real bug caught while building this step:
    # "LANDOWNER: [placeholder]APPLICANT:" with no space).
    assert f"{PLACEHOLDER} {PLACEHOLDER} ZONING:" in redacted


def test_bare_personal_title_is_redacted_even_with_no_label():
    for text in TITLE_ONLY_SAMPLES:
        redacted = redact_private_names(text)
        assert PLACEHOLDER in redacted, f"no placeholder in: {redacted!r}"
        assert contains_private_name_pattern(text), f"measurement missed a hit in: {text!r}"


def test_bare_name_with_no_label_or_title_is_not_caught():
    """The documented, permanent limit (RECORD_PAGE_PLAN.md B.1): a name
    with neither an Owner:/Applicant: label nor a personal title in
    front of it passes through untouched. This is not a bug to fix
    quietly -- it's why applicant_name is kept out of every /record
    payload entirely rather than relied on to be caught here."""
    for text in UNCAUGHT_BARE_NAMES:
        assert redact_private_names(text) == text, f"unexpectedly redacted: {text!r}"
        assert not contains_private_name_pattern(text), (
            f"contains_private_name_pattern should not flag a bare, unlabelled name: {text!r}"
        )


def test_redact_before_truncate_not_after():
    """RECORD_PAGE_PLAN.md Step 5: src/cli.py's dose.json export truncates
    apps[].description to 200 chars. Measured directly (see this test):
    the regex's `$`-anchored lookahead means a cut landing anywhere INSIDE
    a captured name is safe either order -- the match still runs to the
    new end-of-string and gets replaced. The one real difference is a cut
    landing inside the LABEL itself, before its colon completes: truncate
    -then-redact leaves a bare, colon-less "Landowner" fragment sitting
    unredacted (not a name -- the regex correctly doesn't recognise an
    incomplete label -- but still a stray artifact), where redact-then
    -truncate never produces one, because the label is always complete
    when the redactor sees it. Pinned here so the safer order (redact
    first, in src/cli.py) doesn't quietly get "simplified" back later."""
    padding = "x" * 170
    text = f"{padding} Landowner: Christopher Northcott-Wellington the third"
    cut = len(padding) + len(" Landowner")  # lands exactly mid-label, before ":"
    truncate_then_redact = redact_private_names(text[:cut])
    redact_then_truncate = redact_private_names(text)[:cut]
    assert truncate_then_redact.endswith("Landowner"), (
        "fixture didn't land mid-label as intended -- adjust padding"
    )
    assert "Landowner" not in redact_then_truncate
    assert "Christopher" not in truncate_then_redact
    assert "Christopher" not in redact_then_truncate


def test_redact_private_names_passes_through_none_and_empty():
    assert redact_private_names(None) is None
    assert redact_private_names("") == ""


def test_contains_private_name_pattern_is_false_on_ordinary_text():
    assert not contains_private_name_pattern(
        "The committee resolved to approve the application subject to conditions."
    )
