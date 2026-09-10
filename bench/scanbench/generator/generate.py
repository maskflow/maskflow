"""CLI entrypoint for the scan-log-v1.0 synthetic log corpus.

Deterministic: one random.Random(seed) threaded through shape assignment,
shuffling, and every record build.

Every run ends with a self-check that re-validates the checksum-bearing
gold values (Aadhaar, PAN, GSTIN, IFSC, UPI VPA, Indian mobile, credit
card) against the packs' OWN validators. Self-check output carries doc id /
label / offsets only, never the matched text (CLAUDE.md rule 1); the
--sample path is the one place records are printed.

Usage:
    uv run python bench/scanbench/generator/generate.py --sample 8
    uv run python bench/scanbench/generator/generate.py --count 2000 \\
        --out bench/scanbench/data/scan-log-v1.0.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[3]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "packs" / "maskflow-pack-india" / "src"))
sys.path.insert(0, str(_REPO / "packs" / "maskflow-pack-intl" / "src"))

from maskflow_pack_india import patterns as ind_pat  # noqa: E402
from maskflow_pack_intl import patterns as intl_pat  # noqa: E402

from bench.scanbench.generator.shapes import SHAPES, generate_document  # noqa: E402

VERSION = "scan-log-v1.0"

_POSITIVE_VALIDATORS = {
    "AADHAAR": ind_pat.validate_aadhaar,
    "PAN": ind_pat.validate_pan,
    "GSTIN": ind_pat.validate_gstin,
    "IFSC": ind_pat.validate_ifsc,
    "UPI_VPA": ind_pat.validate_upi_vpa,
    "INDIAN_MOBILE": ind_pat.validate_indian_mobile,
    "CREDIT_CARD": intl_pat.validate_credit_card,
}


def _shape_assignment(count: int, rng: random.Random) -> list[str]:
    base, rem = divmod(count, len(SHAPES))
    shapes: list[str] = []
    for i, s in enumerate(SHAPES):
        shapes.extend([s] * (base + (1 if i < rem else 0)))
    rng.shuffle(shapes)
    return shapes


def generate_corpus(count: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    shapes = _shape_assignment(count, rng)
    return [generate_document(s, f"{VERSION}-{i:05d}", rng) for i, s in enumerate(shapes, start=1)]


def self_check(docs: list[dict]) -> tuple[int, int, list[str]]:
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
            if e["value_class"] == "positive" and e["label"] in _POSITIVE_VALIDATORS:
                if _POSITIVE_VALIDATORS[e["label"]](value) is None:
                    lbl, off = e["label"], f"[{e['start']},{e['end']})"
                    failures.append(f"{doc['id']}: {lbl} at {off} failed its validator")
    return checked, len(failures), failures


def _print_sample(docs: list[dict]) -> None:
    for doc in docs:
        print("=" * 78)
        print(f"{doc['id']}  shape={doc['domain']}")
        print("-" * 78)
        print(doc["text"])
        print("-- entities --")
        for e in sorted(doc["entities"], key=lambda e: e["start"]):
            loc = f"[{e['start']:>4},{e['end']:>4})"
            val = doc["text"][e["start"] : e["end"]]
            print(f"  {loc} {e['value_class']:<13} {e['label']:<18} {val!r}")
        print()


def _write_jsonl(docs: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")


def _write_readme(docs: list[dict], seed: int, path: Path) -> None:
    shape_counts = Counter(d["domain"] for d in docs)
    label_counts = Counter(e["label"] for d in docs for e in d["entities"])
    gold = sorted(
        {e["label"] for d in docs for e in d["entities"] if e["value_class"] == "positive"}
    )
    lines = [
        f"# {VERSION}",
        "",
        "Synthetic **log-shaped** PII corpus for `maskflow scan`. Records are nginx "
        "access lines, structured JSON app logs, multi-line stack traces, LLM request "
        "dumps, and worker-task logs. PII values are synthetic and checksum-valid "
        "where a checksum exists (Aadhaar, PAN, GSTIN, IFSC, UPI VPA, Indian mobile, "
        "credit card), cross-checked against the packs' own validators by "
        "`generator/generate.py`'s `self_check()`. The hard negatives are the "
        "PII-lookalike noise real logs carry -- request/trace ids, UUIDs, git SHAs, "
        "epoch-millis timestamps, internal `10./172.16./192.168.` IPs in log "
        "position, base64/`sk_test_` blobs, `File.java:142` frames. "
        "**None of these values belong to any real person, account, or credential.**",
        "",
        "- License: CC-BY-4.0",
        f"- Seed: {seed}",
        f"- Records: {len(docs)}",
        f"- Gold PII spans: {sum(n for lbl, n in label_counts.items() if lbl in gold)}",
        f"- Decoy spans (log noise, never gold): "
        f"{sum(n for lbl, n in label_counts.items() if lbl not in gold)}",
        "",
        "## Records per shape",
        "",
        *(f"- {s}: {n}" for s, n in sorted(shape_counts.items())),
        "",
        "## Spans per label",
        "",
        *(f"- {lbl}: {n}" for lbl, n in sorted(label_counts.items())),
        "",
        "## Gold entity taxonomy",
        "",
        *(f"- {lbl}" for lbl in gold),
        "",
        "## Known limitations",
        "",
        "- English only; the shapes are hand-authored templates, not sampled from "
        "real production logs.",
        "- `PERSON_NAME` depends on the spaCy NER pass (`--deep`); recall on it "
        "reflects `en_core_web_sm`.",
        "- Internal `10./172.16./192.168.` IPs are scored as decoys: for a "
        "PII-exposure audit a private-range IP is not personal data. MaskFlow has no "
        "private-IP suppression today, so `IP_ADDRESS` precision here is a real "
        "measured property, not a corpus artifact.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the scan-log benchmark corpus")
    ap.add_argument("--seed", type=int, default=20260910)
    ap.add_argument("--count", type=int, default=2000)
    ap.add_argument("--sample", type=int, default=0, help="preview N records, don't write")
    ap.add_argument("--out", type=Path, default=_HERE.parents[1] / "data" / f"{VERSION}.jsonl")
    args = ap.parse_args()

    docs = generate_corpus(args.sample or args.count, args.seed)
    checked, failed, failures = self_check(docs)
    print(f"self-check: {checked} spans checked, {failed} failed", file=sys.stderr)
    for f_desc in failures[:20]:
        print(f"  FAIL: {f_desc}", file=sys.stderr)
    if failed:
        sys.exit(1)

    if args.sample:
        _print_sample(docs)
        return

    _write_jsonl(docs, args.out)
    readme = args.out.with_name(args.out.stem + ".README.md")
    _write_readme(docs, args.seed, readme)
    print(f"wrote {len(docs)} records to {args.out}", file=sys.stderr)
    print(f"wrote manifest to {readme}", file=sys.stderr)


if __name__ == "__main__":
    main()
