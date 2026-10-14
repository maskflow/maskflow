"""Generate indiapii-tabular-v1.0: synthetic Indian-PII *tables* -- the shape
a coding agent's `psql`/`sqlite3`/`cat export.csv` output or a log export
takes -- with labelled spans, for measuring column-header context.

ALL identifiers are SYNTHETIC, produced by bench/indiapii/generator's
checksum/format-valid generators (see that module's docstring). Decoy
columns hold PII-*shaped* values that are not PII (10-digit order IDs that
start 6-9, 11-digit internal account IDs, ...) and are left unlabelled, so
any detection inside them counts as a false positive.

    uv run python -m bench.tabular.generate            # writes the corpus
    uv run python -m bench.tabular.generate --check    # verify it's current
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from bench.indiapii.generator import identifiers as ids

SEED = 20261014
NUM_DOCS = 300
VERSION = "indiapii-tabular-v1.0"
OUT = Path(__file__).resolve().parent / "data" / f"{VERSION}.jsonl"

Gen = Callable[[random.Random], str]


def _bare_mobile(rng: random.Random) -> str:
    return ids.generate_indian_mobile(rng, with_prefix=False).replace(" ", "").replace("-", "")


def _bare_aadhaar(rng: random.Random) -> str:
    return ids.generate_aadhaar(rng).replace(" ", "").replace("-", "")


def _order_id(rng: random.Random) -> str:
    # Decoy: mobile-shaped (10 digits, 6-9 first) but an order number.
    return rng.choice("6789") + "".join(rng.choice("0123456789") for _ in range(9))


def _internal_account_id(rng: random.Random) -> str:
    # Decoy: bank-account-shaped (11 digits) but a SaaS account id.
    return rng.choice("123456789") + "".join(rng.choice("0123456789") for _ in range(10))


def _amount(rng: random.Random) -> str:
    return f"{rng.randint(100, 9_999_999)}.{rng.randint(0, 99):02d}"


def _status(rng: random.Random) -> str:
    return rng.choice(("pending", "verified", "rejected", "on_hold"))


# (label or None for a decoy, header variants, generator)
PII_COLUMNS: list[tuple[str, tuple[str, ...], Gen]] = [
    ("PERSON_NAME", ("name", "customer_name", "Full Name", "applicant"), ids.generate_person_name),
    ("INDIAN_MOBILE", ("mobile", "mobile_no", "Phone", "contact_number", "mob", "msisdn",
                       "Mobile No.", "whatsapp", "मोबाइल"), _bare_mobile),
    ("BANK_ACCOUNT_IN", ("account_no", "acc_no", "Account Number", "bank_account"),
     ids.generate_bank_account),
    ("PIN_CODE", ("pincode", "pin_code", "zipcode", "postal_code"), ids.generate_pin_code),
    ("AADHAAR", ("aadhaar", "aadhaar_no", "uid"), _bare_aadhaar),
    ("PAN", ("pan", "pan_no", "PAN Number"), ids.generate_pan),
    ("UPI_VPA", ("upi", "upi_id", "vpa"), ids.generate_upi_vpa),
    ("IFSC", ("ifsc", "ifsc_code"), ids.generate_ifsc),
]  # fmt: skip

DECOY_COLUMNS: list[tuple[tuple[str, ...], Gen]] = [
    (("order_id", "txn_ref", "invoice_no", "ticket"), _order_id),
    (("account_id", "user_account_id", "account_type_code"), _internal_account_id),
    (("mobile_app_build", "phone_model_code", "test_mobile", "sample_phone"), _order_id),
    (("amount", "balance"), _amount),
]

FORMATS = ("csv", "tsv", "psql", "mysql", "markdown", "sqlite")


def _render(fmt: str, header: list[str], rows: list[list[str]]) -> tuple[str, list[list[int]]]:
    """Render the table; return text plus each data cell's start offset."""
    out: list[str] = []
    starts: list[list[int]] = []
    pos = 0

    def emit(line: str) -> None:
        nonlocal pos
        out.append(line)
        pos += len(line) + 1

    def row_line(cells: list[str], sep: str, lead: str, trail: str) -> tuple[str, list[int]]:
        offsets, line = [], lead
        for k, cell in enumerate(cells):
            if k:
                line += sep
            offsets.append(pos + len(line))
            line += cell
        return line + trail, offsets

    if fmt in ("csv", "tsv", "sqlite"):
        sep = {"csv": ",", "tsv": "\t", "sqlite": "|"}[fmt]
        emit(sep.join(header))
        for r in rows:
            line, offs = row_line(r, sep, "", "")
            starts.append(offs)
            emit(line)
    elif fmt == "psql":
        emit(" " + " | ".join(header))
        emit("-+-".join("-" * max(len(h), 4) for h in header))
        for r in rows:
            line, offs = row_line(r, " | ", " ", "")
            starts.append(offs)
            emit(line)
        emit(f"({len(rows)} rows)")
    else:  # mysql box / markdown
        rule = "+" + "+".join("-" * (len(h) + 2) for h in header) + "+"
        if fmt == "mysql":
            emit(rule)
        emit("| " + " | ".join(header) + " |")
        emit(rule if fmt == "mysql" else "|" + "|".join("---" for _ in header) + "|")
        for r in rows:
            line, offs = row_line(r, " | ", "| ", " |")
            starts.append(offs)
            emit(line)
        if fmt == "mysql":
            emit(rule)
    return "\n".join(out) + "\n", starts


def generate_doc(rng: random.Random, index: int) -> dict[str, object]:
    fmt = FORMATS[index % len(FORMATS)]
    pii = rng.sample(PII_COLUMNS, k=rng.randint(1, 4))
    decoys = rng.sample(DECOY_COLUMNS, k=rng.randint(0, 2))
    columns: list[tuple[str | None, str, Gen]] = [(None, "id", lambda r: "")]
    columns += [(label, rng.choice(headers), gen) for label, headers, gen in pii]
    columns += [(None, rng.choice(headers), gen) for headers, gen in decoys]
    columns.append((None, "status", _status))
    first, *rest = columns
    rng.shuffle(rest)
    columns = [first, *rest]

    n_rows = rng.choice((3, 5, 12, 40, 120))
    rows = [
        [str(i) if label is None and header == "id" else gen(rng) for label, header, gen in columns]
        for i, _ in enumerate(range(n_rows), 1)
    ]
    text, starts = _render(fmt, [h for _, h, _ in columns], rows)

    entities = []
    for r, row in enumerate(rows):
        for c, (label, _, _) in enumerate(columns):
            if label is not None:
                start = starts[r][c]
                entities.append({"start": start, "end": start + len(row[c]), "label": label})
                assert text[start : start + len(row[c])] == row[c]
    return {
        "id": f"{VERSION}-{index + 1:05d}",
        "text": text,
        "entities": entities,
        "domain": fmt,
        "lang": "en",
    }


def generate() -> list[dict[str, object]]:
    rng = random.Random(SEED)
    return [generate_doc(rng, i) for i in range(NUM_DOCS)]


def _serialise(docs: list[dict[str, object]]) -> str:
    return "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in docs)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m bench.tabular.generate")
    parser.add_argument("--check", action="store_true", help="fail if the corpus is stale")
    args = parser.parse_args()
    docs = generate()
    body = _serialise(docs)
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != body:
            print(f"{OUT} is stale -- rerun without --check", file=sys.stderr)
            return 1
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8")
    labels = Counter(e["label"] for d in docs for e in d["entities"])  # type: ignore[attr-defined]
    print(f"wrote {len(docs)} docs, {sum(labels.values())} spans -> {OUT}")
    for label, n in sorted(labels.items()):
        print(f"  {label}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
