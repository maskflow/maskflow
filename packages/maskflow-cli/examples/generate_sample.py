"""Regenerates examples/sample-llm-traffic.jsonl.

EVERYTHING THIS PRODUCES IS SYNTHETIC. Identifiers are generated to be
checksum-/format-valid but are drawn uniformly at random within that shape
and are never looked up against, or taken from, any real registry -- see
`bench/indiapii/generator/identifiers.py`. Names, emails, and addresses are
assembled from the same synthetic pools. Do not treat any value here as
belonging to a real person or organisation.

Run from the repo root:  uv run python packages/maskflow-cli/examples/generate_sample.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

# The synthetic-identifier generators live in the repo's bench/ tree.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from bench.indiapii.generator import identifiers as gen  # noqa: E402

OUT = Path(__file__).parent / "sample-llm-traffic.jsonl"
SEED = 20260513  # DPDP enforcement date -- deterministic output
N = 60

_PROVIDERS = [
    ("openai", "gpt-4o"),
    ("openai", "gpt-4o-mini"),
    ("anthropic", "claude-sonnet-4"),
    ("anthropic", "claude-3-5-haiku"),
    ("google", "gemini-1.5-pro"),
]

# ~1 in 4 records is a clean support query with no PII, so the sample report
# shows a realistic "N of M records contained PII" ratio.
_CLEAN = [
    "How do I reset my password?",
    "What are your business hours on public holidays?",
    "Summarise the attached refund policy in three bullet points.",
    "Draft a polite reminder email about an overdue invoice (no names).",
    "What's the difference between IMPS and NEFT?",
]


def _pii_prompt(rng: random.Random) -> str:
    name = gen.generate_person_name(rng)
    kind = rng.randrange(6)
    if kind == 0:
        dob = f"19{rng.randint(60, 99)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        return (
            f"Run a KYC check for {name}. Aadhaar {gen.generate_aadhaar(rng)}, "
            f"PAN {gen.generate_pan(rng)}, DOB {dob}."
        )
    if kind == 1:
        return (
            f"Customer {name} ({gen.generate_indian_mobile(rng)}) wants a refund to "
            f"UPI {gen.generate_upi_vpa(rng)} -- draft the confirmation message."
        )
    if kind == 2:
        return (
            f"Vendor onboarding: GSTIN {gen.generate_gstin(rng)}, settlement account "
            f"IFSC {gen.generate_ifsc(rng)}, contact {name.split()[0].lower()}@vendor.example."
        )
    if kind == 3:
        return (
            f"Ship the replacement unit to {name}, {gen.generate_indian_address(rng)}. "
            f"Reachable on {gen.generate_indian_mobile(rng)}."
        )
    if kind == 4:
        return (
            f"Cardholder {name} disputes a charge on card "
            f"{_fake_card(rng)}; summarise the case for the ops team."
        )
    return (
        f"Passport {gen.generate_indian_passport(rng)} and driving licence "
        f"{gen.generate_driving_licence(rng)} submitted by {name} for verification."
    )


def _fake_card(rng: random.Random) -> str:
    # A Luhn-valid 16-digit number in a test BIN range (4242...) -- same
    # "valid shape, not a real card" discipline as the other identifiers.
    digits = [4, 2, 4, 2] + [rng.randrange(10) for _ in range(11)]
    checksum = 0
    for idx, d in enumerate(reversed(digits)):
        d = d * 2 if idx % 2 == 0 else d
        checksum += d - 9 if d > 9 else d
    digits.append((10 - checksum % 10) % 10)
    s = "".join(map(str, digits))
    return f"{s[0:4]} {s[4:8]} {s[8:12]} {s[12:16]}"


def main() -> None:
    rng = random.Random(SEED)
    rows: list[dict] = []
    for i in range(N):
        provider, model = _PROVIDERS[i % len(_PROVIDERS)]
        month = 1 + (i * 7) % 8  # spread Jan..Aug 2026
        day = 1 + (i * 13) % 27
        ts = f"2026-{month:02d}-{day:02d}T{9 + i % 9:02d}:{(i * 17) % 60:02d}:00Z"
        content = rng.choice(_CLEAN) if i % 4 == 0 else _pii_prompt(rng)
        rows.append(
            {
                "request_id": f"req_{i:04d}",
                "provider": provider,
                "model": model,
                "created_at": ts,
                "messages": [{"role": "user", "content": content}],
            }
        )
    OUT.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} records -> {OUT}")


if __name__ == "__main__":
    main()
