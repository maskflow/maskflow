"""CLI entrypoint for the intl-pii-v1.0 synthetic benchmark corpus.

Deterministic: exactly one random.Random(seed) instance is threaded through
domain assignment, shuffling, and every document build -- the same --seed
reproduces the same corpus for a given --count.

Every run ends with a self-check that re-validates the corpus against
maskflow-pack-intl's OWN validators (patterns.py) -- proof that
"checksum-VALID" is actually true of what was generated, not merely
asserted. Self-check output reports doc id + label + offsets only, never
the matched text (CLAUDE.md rule 1); the --sample path is the one place
generated documents are printed, so a human can read them.

Usage:
    uv run python bench/intlpii/generator/generate.py --sample 8
    uv run python bench/intlpii/generator/generate.py --count 1800 \\
        --out bench/intlpii/data/intl-pii-v1.0.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(
    0, str(Path(__file__).resolve().parents[3] / "packs" / "maskflow-pack-intl" / "src")
)

from maskflow_pack_intl import patterns  # noqa: E402

from generator import hard_negatives as hn  # noqa: E402
from generator.templates import DOMAINS, generate_document  # noqa: E402

VERSION = "intl-pii-v1.0"


def _validate_ssn(value: str) -> float | None:
    return (
        patterns.validate_ssn_dashed(value) if "-" in value else patterns.validate_ssn_plain(value)
    )


_POSITIVE_VALIDATORS = {
    "CREDIT_CARD": patterns.validate_credit_card,
    "IBAN": patterns.validate_iban,
    "SSN": _validate_ssn,
}

_HARD_NEGATIVE_MUST_FAIL = {
    hn.CC_LUHN_INVALID: patterns.validate_credit_card,
    hn.SSN_INVALID_AREA: patterns.validate_ssn_dashed,
    hn.IBAN_BAD_CHECKSUM: patterns.validate_iban,
}


def _domain_assignment(count: int, rng: random.Random) -> list[str]:
    base, rem = divmod(count, len(DOMAINS))
    domains: list[str] = []
    for i, d in enumerate(DOMAINS):
        domains.extend([d] * (base + (1 if i < rem else 0)))
    rng.shuffle(domains)
    return domains


def generate_corpus(count: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    domains = _domain_assignment(count, rng)
    return [generate_document(d, f"{VERSION}-{i:05d}", rng) for i, d in enumerate(domains, start=1)]


def self_check(docs: list[dict]) -> tuple[int, int, list[str]]:
    """Returns (spans_checked, spans_failed, failure_descriptions). Failure
    descriptions carry doc id / label / offsets only -- never the underlying
    text (CLAUDE.md rule 1)."""
    checked = 0
    failures: list[str] = []
    for doc in docs:
        text = doc["text"]
        spans = sorted(doc["entities"], key=lambda e: (e["start"], e["end"]))
        for a, b in zip(spans, spans[1:], strict=False):
            if a["end"] > b["start"]:
                failures.append(f"{doc['id']}: overlapping spans at offset {a['end']}")
        for e in spans:
            checked += 1
            value = text[e["start"] : e["end"]]
            label = e["label"]
            if e["value_class"] == "positive" and label in _POSITIVE_VALIDATORS:
                if _POSITIVE_VALIDATORS[label](value) is None:
                    failures.append(
                        f"{doc['id']}: {label} at [{e['start']},{e['end']}) failed its validator"
                    )
            elif e["value_class"] == "hard_negative" and label in _HARD_NEGATIVE_MUST_FAIL:
                if _HARD_NEGATIVE_MUST_FAIL[label](value) is not None:
                    failures.append(
                        f"{doc['id']}: hard-negative {label} at [{e['start']},{e['end']}) "
                        "unexpectedly passed the real validator"
                    )
    return checked, len(failures), failures


def _print_sample(docs: list[dict]) -> None:
    for doc in docs:
        print("=" * 78)
        print(f"{doc['id']}  domain={doc['domain']}  lang={doc['lang']}")
        print("-" * 78)
        print(doc["text"])
        print("-- entities --")
        for e in sorted(doc["entities"], key=lambda e: e["start"]):
            value = doc["text"][e["start"] : e["end"]]
            loc = f"[{e['start']:>4},{e['end']:>4})"
            print(f"  {loc} {e['value_class']:<13} {e['label']:<16} {value!r}")
        print()


def _write_jsonl(docs: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")


def _write_readme(docs: list[dict], seed: int, readme_path: Path) -> None:
    domain_counts = Counter(d["domain"] for d in docs)
    label_counts = Counter(e["label"] for d in docs for e in d["entities"])
    positive_labels = sorted(
        {e["label"] for d in docs for e in d["entities"] if e["value_class"] == "positive"}
    )
    lines = [
        f"# {VERSION}",
        "",
        "Synthetic international-PII benchmark corpus for `maskflow-pack-intl`. "
        "ALL values in this dataset are synthetic: checksum-valid (CREDIT_CARD via "
        "Luhn, IBAN via mod-97), drawn from real-but-never-assigned ranges (SSN area "
        "numbers, the NANP `555-01xx` fiction range for phone numbers), or "
        "structurally valid to their published format with no real-world backing "
        "(EMAIL, AWS_KEY, API_KEY, JWT, IP_ADDRESS, ADDRESS, PERSON_NAME, "
        "DATE_OF_BIRTH). Every checksum-bearing value is cross-checked against the "
        "pack's own validators by `generator/generate.py`'s `self_check()`. "
        "**None of these values belong to any real person, account, or credential.**",
        "",
        "- License: CC-BY-4.0",
        f"- Seed: {seed}",
        f"- Documents: {len(docs)}",
        "- Entity spans (gold, positive only): "
        f"{sum(n for lbl, n in label_counts.items() if lbl in positive_labels)}",
        "- Decoy spans (hard negatives, never gold): "
        f"{sum(n for lbl, n in label_counts.items() if lbl not in positive_labels)}",
        "",
        "## Documents per domain",
        "",
        *(f"- {d}: {n}" for d, n in sorted(domain_counts.items())),
        "",
        "## Spans per label",
        "",
        *(f"- {label}: {n}" for label, n in sorted(label_counts.items())),
        "",
        "## Entity taxonomy (gold)",
        "",
        *(f"- {label}" for label in positive_labels),
        "",
        "## Known limitations",
        "",
        "- English only; no code-mixed or OCR'd input (that discipline lives in `indiapii-v1.0`).",
        "- `PERSON_NAME` and `DATE_OF_BIRTH` depend on the spaCy NER pass; recall on "
        "them reflects `en_core_web_sm`, not a ceiling.",
        "- `API_KEY` covers OpenAI / Anthropic / GitHub / Google shapes; no "
        "Slack `xox*` token -- a random one still trips GitHub's push-protection "
        "scanner. The pack's `API_KEY_RE` covers that branch; this corpus does not.",
        "- Generic PII is not a surface MaskFlow competes on (Presidio / mask-privacy "
        "own it). This corpus exists to publish a measured number, not to claim a win.",
        "",
        "## Citation",
        "",
        "```",
        f"MaskFlow {VERSION} synthetic international-PII benchmark corpus. "
        "MIT-licensed project, CC-BY-4.0 dataset. https://github.com/maskflow/maskflow",
        "```",
        "",
    ]
    readme_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the intl-pii benchmark corpus")
    parser.add_argument("--seed", type=int, default=20260910)
    parser.add_argument("--count", type=int, default=1800)
    parser.add_argument(
        "--sample", type=int, default=0, help="Preview N docs to stdout, don't write"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / f"{VERSION}.jsonl",
    )
    args = parser.parse_args()

    docs = generate_corpus(args.sample or args.count, args.seed)

    checked, failed, failures = self_check(docs)
    print(f"self-check: {checked} spans checked, {failed} failed", file=sys.stderr)
    for f_desc in failures[:20]:
        print(f"  FAIL: {f_desc}", file=sys.stderr)
    if failed:
        print("self-check FAILED -- not writing output", file=sys.stderr)
        sys.exit(1)

    if args.sample:
        _print_sample(docs)
        return

    _write_jsonl(docs, args.out)
    readme_path = args.out.with_name(args.out.stem + ".README.md")
    _write_readme(docs, args.seed, readme_path)
    print(f"wrote {len(docs)} documents to {args.out}", file=sys.stderr)
    print(f"wrote manifest to {readme_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
