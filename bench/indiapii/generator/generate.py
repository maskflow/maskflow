"""CLI entrypoint for the indiapii-v1.0 synthetic benchmark corpus.

Deterministic: exactly one random.Random(seed) instance is created and
threaded through domain assignment, shuffling, and every document build --
the same --seed always reproduces the same corpus for a given --count.

Every run (sample preview or full write) ends with a self-check pass that
re-validates the corpus against maskflow-pack-india's OWN validate_*()
functions (patterns.py) -- proof that "checksum-VALID" is actually true of
what was generated, not merely asserted (see identifiers.py/hard_negatives.
py's docstrings). Self-check output reports doc id + label + offsets only,
never the matched text itself (CLAUDE.md rule 1) -- even though this
corpus's PII is 100% synthetic, this script never gets in the habit of
printing PII-shaped spans outside of the explicit --sample preview path,
which exists specifically to let a human read the generated documents.

Usage:
    uv run python bench/indiapii/generator/generate.py --sample 10
    uv run python bench/indiapii/generator/generate.py --count 2000 \\
        --out bench/indiapii/data/indiapii-v1.0.jsonl
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
    0, str(Path(__file__).resolve().parents[3] / "packs" / "maskflow-pack-india" / "src")
)

from maskflow_pack_india import patterns  # noqa: E402

from generator import hard_negatives as hn  # noqa: E402
from generator.templates import DOMAINS, generate_document  # noqa: E402

VERSION = "indiapii-v1.0"

_VALIDATORS = {
    "AADHAAR": patterns.validate_aadhaar,
    "PAN": patterns.validate_pan,
    "GSTIN": patterns.validate_gstin,
    "IFSC": patterns.validate_ifsc,
    "UPI_VPA": patterns.validate_upi_vpa,
    "ABHA_ADDRESS": patterns.validate_abha_address,
    "DRIVING_LICENCE": patterns.validate_driving_licence,
    "VEHICLE_REG": patterns.validate_vehicle_reg,
    "INDIAN_MOBILE": patterns.validate_indian_mobile,
}

_HARD_NEGATIVE_MUST_FAIL = {
    hn.NON_VERHOEFF_AADHAAR_SHAPED: patterns.validate_aadhaar,
    hn.PAN_SHAPED_INVOICE_NO: patterns.validate_pan,
    hn.VPA_SHAPED_EMAIL: patterns.validate_upi_vpa,
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
    docs = []
    for i, domain in enumerate(domains, start=1):
        doc_id = f"{VERSION}-{i:05d}"
        docs.append(generate_document(domain, doc_id, rng))
    return docs


def self_check(docs: list[dict]) -> tuple[int, int, list[str]]:
    """Returns (spans_checked, spans_failed, failure_descriptions).
    Failure descriptions carry doc id / label / offsets only -- never the
    underlying text (CLAUDE.md rule 1)."""
    checked = 0
    failures: list[str] = []
    for doc in docs:
        text = doc["text"]
        spans = sorted(doc["entities"], key=lambda e: (e["start"], e["end"]))
        for a, b in zip(spans, spans[1:], strict=False):
            if a["end"] > b["start"]:
                failures.append(f'{doc["id"]}: overlapping spans at offset {a["end"]}')
        for e in spans:
            checked += 1
            value = text[e["start"] : e["end"]]
            label = e["label"]
            if e["value_class"] == "positive" and label in _VALIDATORS:
                if _VALIDATORS[label](value) is None:
                    failures.append(
                        f'{doc["id"]}: {label} at [{e["start"]},{e["end"]}) failed its validator'
                    )
            elif e["value_class"] == "hard_negative" and label in _HARD_NEGATIVE_MUST_FAIL:
                if _HARD_NEGATIVE_MUST_FAIL[label](value) is not None:
                    failures.append(
                        f'{doc["id"]}: hard-negative {label} at [{e["start"]},{e["end"]}) '
                        "unexpectedly passed the real validator"
                    )
    return checked, len(failures), failures


def _print_sample(docs: list[dict]) -> None:
    for doc in docs:
        print("=" * 78)
        print(f'{doc["id"]}  domain={doc["domain"]}  lang={doc["lang"]}')
        print("-" * 78)
        print(doc["text"])
        print("-- entities --")
        for e in sorted(doc["entities"], key=lambda e: e["start"]):
            value = doc["text"][e["start"] : e["end"]]
            loc = f'[{e["start"]:>4},{e["end"]:>4})'
            print(f'  {loc} {e["value_class"]:<13} {e["label"]:<26} {value!r}')
        print()


def _write_jsonl(docs: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")


def _write_readme(docs: list[dict], seed: int, readme_path: Path) -> None:
    domain_counts = Counter(d["domain"] for d in docs)
    label_counts = Counter(e["label"] for d in docs for e in d["entities"])
    total_spans = sum(label_counts.values())
    lines = [
        f"# {VERSION}",
        "",
        "Synthetic India-PII benchmark corpus for maskflow-pack-india. "
        "ALL identifiers in this dataset are synthetic: checksum-valid "
        "(Aadhaar, GSTIN) or format-valid (PAN, IFSC, UPI VPA, ...) values "
        "generated at random and cross-checked against the pack's own "
        "validators (see generator/generate.py's self_check()). "
        "**None of these identifiers belong to any real person, business, "
        "or account.**",
        "",
        f"- Seed: {seed}",
        f"- Documents: {len(docs)}",
        f"- Entity spans: {total_spans}",
        "",
        "## Documents per domain",
        "",
    ]
    for domain, n in sorted(domain_counts.items()):
        lines.append(f"- {domain}: {n}")
    lines += ["", "## Spans per label", ""]
    for label, n in sorted(label_counts.items()):
        lines.append(f"- {label}: {n}")
    lines.append("")
    readme_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the indiapii benchmark corpus")
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--count", type=int, default=2000)
    parser.add_argument(
        "--sample", type=int, default=0, help="Preview N docs to stdout, don't write"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / f"{VERSION}.jsonl",
    )
    args = parser.parse_args()

    count = args.sample if args.sample else args.count
    docs = generate_corpus(count, args.seed)

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
