"""Builds a synthetic JSONL corpus with known synthetic PII for the fuzz
gate. Every identifier is generated (checksum-valid where a checksum
exists) by bench.indiapii.generator -- never a real value.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from bench.indiapii.generator import identifiers as gen

# Zero-width joiner / non-joiner and an RTL mark -- the round-trip-hostile
# characters CLAUDE.md rule 5 calls out, planted next to real PII.
_ZW = "‍"
_RTL = "‏"


def build_corpus(path: Path, *, n: int = 400, seed: int = 7) -> set[str]:
    """Write `n` records to `path`; return every raw PII string injected."""
    rng = random.Random(seed)
    injected: set[str] = set()
    lines: list[str] = []

    for i in range(n):
        aadhaar = gen.generate_aadhaar(rng)
        pan = gen.generate_pan(rng)
        gstin = gen.generate_gstin(rng)
        ifsc = gen.generate_ifsc(rng)
        upi = gen.generate_upi_vpa(rng)
        mobile = gen.generate_indian_mobile(rng)
        email = f"user{i}.{rng.randint(1000, 9999)}@example.com"
        name = gen.generate_person_name(rng)
        injected.update({aadhaar, pan, gstin, ifsc, upi, mobile, email, name})

        variants = [
            f"KYC for {name}: Aadhaar {aadhaar}, PAN {pan}. GSTIN {gstin}.",
            # PII adjacent to a placeholder-lookalike
            f"<EMAIL_1> is not real; the real one is {email} and UPI {upi}.",
            # zero-width chars planted inside the surrounding text
            f"Contact{_ZW} {mobile}{_RTL} for the account at IFSC {ifsc}.",
            # PII that also looks date-ish nearby
            f"On 2026-01-02 we verified {name} ({aadhaar}) via {email}.",
        ]
        text = variants[i % len(variants)]
        lines.append(
            json.dumps(
                {
                    "messages": [{"role": "user", "content": text}],
                    "model": rng.choice(["gpt-4o", "claude-sonnet-4", "gemini-1.5-pro"]),
                    "provider": rng.choice(["openai", "anthropic", "google"]),
                    "ts": f"2026-0{rng.randint(1, 9)}-1{rng.randint(0, 8)}T09:00:00",
                }
            )
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Drop anything trivially short that would false-positive a substring
    # search (e.g. a 4-char name fragment) -- the gate is about identifiers.
    return {v for v in injected if len(v) >= 6}
