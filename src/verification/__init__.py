"""
The harder, model-based verification layers (docs/uplift/migration/
05-verification.md, V-4 onward) — separate from the cheap, zero-model
census checks in `src/analysis/verification.py` (V-1/V-2/V-3), which need
no new infrastructure at all. This package is where that infrastructure
(page rasterisation, precision-pass sampling, recall estimation) lives as
it's built out, one layer at a time, in later phases.
"""
