"""Regenerate packages/maskflow-js/tests/fixtures.json from maskflow-pack-intl's
Python fixtures.

Run via `uv run python scripts/generate_js_fixtures.py` (from the repo root)
whenever packs/maskflow-pack-intl/tests/fixtures/pii_samples.py changes, so
the JS port's test suite stays honest against the same source of truth as the
Python tests. Only the regex/structural types the JS port covers are included
(PERSON_NAME and DATE_OF_BIRTH need spaCy NER, which has no JS equivalent
here).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packs" / "maskflow-pack-intl" / "tests"))

import maskflow_pack_intl  # noqa: E402,F401 -- registers the 12 recognizers
from fixtures import pii_samples  # noqa: E402

JS_SUPPORTED_TYPES = {
    "EMAIL",
    "PHONE",
    "SSN",
    "CREDIT_CARD",
    "IP_ADDRESS",
    "AWS_KEY",
    "API_KEY",
    "JWT",
    "IBAN",
    "ADDRESS",
}

positive = []
for sample in pii_samples.POSITIVE_SAMPLES:
    expected = [
        {"type": pii_type.value, "value": value}
        for pii_type, value in sample.expected
        if pii_type.value in JS_SUPPORTED_TYPES
    ]
    if expected:
        positive.append({"text": sample.text, "expected": expected})

output = {
    "positive": positive,
    "negative": list(pii_samples.NEGATIVE_SAMPLES),
}

out_path = ROOT / "packages" / "maskflow-js" / "tests" / "fixtures.json"
out_path.write_text(json.dumps(output, indent=2) + "\n")
print(
    f"Wrote {len(positive)} positive samples, "
    f"{len(output['negative'])} negative samples to {out_path}"
)
