"""Multi-adapter benchmark harness for bench/intlpii's synthetic corpus
(intl-pii-v1.0), scoring maskflow-pack-intl's 12 international/US-shaped
entity types.

Deliberately thin: the scoring core (corpus loader, strict/partial-overlap
matching, timed runner, JSON/Markdown report writers, offset recovery) is
imported wholesale from bench.indiapii.harness -- it was written to be
corpus-agnostic and there is no reason to fork it. This package adds only
what is intl-specific: the label vocabulary glosses, each competitor's
raw-label -> canonical-label map (Presidio and mask-privacy are *real*
competitors here -- email / phone / credit card / person / IP / IBAN all
overlap), an intl naive-regex baseline, and the CLI wiring.

The `maskflow` adapter is bench.indiapii.harness's own MaskflowAdapter,
unchanged: it registers BOTH bundled packs, which is the exact
configuration a `pip install maskflow-sdk` user runs. A number that moves
because pack-india's recognizers interact with US-shaped input on this
corpus is a real property of the shipped product, not a harness artifact.

Entry point: `uv run python -m bench.intlpii.harness run`.
"""
