"""Recipient-placeholder detection in `awarded_to`.

Regression cover for the 2026-08-31 bug: the redaction check matched only
`respondent%`, so `Tenderer 1` and `Contractor 1` — the same kind of
de-identification placeholder, just a different role noun — were aggregated
as if they were real firms.
"""
from src.analysis.queries import _is_redacted_recipient


def test_placeholder_role_nouns_are_redacted():
    for name in ("Respondent 4", "Tenderer 1", "Contractor 1", "Supplier 2",
                 "Bidder 3", "Proponent 1", "Respondent", "respondent 10",
                 "Contractor #2", "Tenderer - 1"):
        assert _is_redacted_recipient(name), name


def test_real_firm_names_are_not_redacted():
    # The trap cases: real corpus firms whose names start with, or contain,
    # a placeholder role noun. Only a bare "<noun> <digits>" is a placeholder.
    for name in ("Fleetcare Pty Ltd", "Roads 2000", "Albarossa Pty Ltd ACN 131 350 340",
                 "Major Motors - Isuzu FVR 900", "Contractor Services Pty Ltd",
                 "Supplier Solutions Australia", "Respondent Group Holdings"):
        assert not _is_redacted_recipient(name), name
