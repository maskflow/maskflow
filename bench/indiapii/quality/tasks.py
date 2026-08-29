"""Builds the 200-task indiapii-quality-v1.0 task spec set: for each of
summarize/draft_reply/extract_fields, samples documents (without
replacement within a task type) from the existing indiapii-v1.0 corpus and
pairs each with a domain (see prompts.py for the actual instruction text).
extract_fields tasks also carry a gold answer, read straight off the
corpus's own gold entity spans -- the same ground truth the detection
harness scores against, so this benchmark's field-accuracy metric costs
nothing extra to trust.

Task specs reference their source document by id rather than embedding its
text, so quality-v1.0.jsonl stays a thin index over indiapii-v1.0.jsonl
(loaded once per run via bench.indiapii.harness.corpus.load_corpus) instead
of duplicating a second copy of the corpus.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from bench.indiapii.harness.corpus import Document

VERSION = "indiapii-quality-v1.0"

TASK_TYPES: tuple[str, ...] = ("summarize", "draft_reply", "extract_fields")

# task_type -> how many of the 200 tasks it gets. 200 doesn't split evenly
# by 3; extract_fields takes the one-fewer slot since it's the only type
# restricted to a subset of domains (EXTRACT_FIELD_SCHEMAS below).
TASK_TYPE_COUNTS: dict[str, int] = {"summarize": 67, "draft_reply": 67, "extract_fields": 66}

# domain -> {field_name: entity_label}, the fields an extract_fields task
# for that domain asks for -- a curated subset of the domain's own gold
# entity types (see bench/indiapii/generator/templates.py), not "every
# label this domain ever contains."
EXTRACT_FIELD_SCHEMAS: dict[str, dict[str, str]] = {
    "kyc_form": {
        "applicant_name": "PERSON_NAME",
        "aadhaar": "AADHAAR",
        "pan": "PAN",
        "mobile": "INDIAN_MOBILE",
        "address": "INDIAN_ADDRESS",
        "pin_code": "PIN_CODE",
    },
    "loan_application": {
        "applicant_name": "PERSON_NAME",
        "pan": "PAN",
        "aadhaar": "AADHAAR",
        "bank_account": "BANK_ACCOUNT_IN",
        "ifsc": "IFSC",
        "mobile": "INDIAN_MOBILE",
        "address": "INDIAN_ADDRESS",
        "pin_code": "PIN_CODE",
    },
    "hr_record": {
        "employee_name": "PERSON_NAME",
        "pan": "PAN",
        "aadhaar": "AADHAAR",
        "bank_account": "BANK_ACCOUNT_IN",
        "ifsc": "IFSC",
        "mobile": "INDIAN_MOBILE",
        "address": "INDIAN_ADDRESS",
    },
    "insurance_claim": {
        "policyholder_name": "PERSON_NAME",
        "vehicle_reg": "VEHICLE_REG",
        "driving_licence": "DRIVING_LICENCE",
        "bank_account": "BANK_ACCOUNT_IN",
        "ifsc": "IFSC",
        "mobile": "INDIAN_MOBILE",
    },
    "medical_note": {
        "patient_name": "PERSON_NAME",
        "abha_number": "ABHA_NUMBER",
        "address": "INDIAN_ADDRESS",
        "pin_code": "PIN_CODE",
    },
    "bank_chat": {
        "upi_vpa": "UPI_VPA",
        "bank_account": "BANK_ACCOUNT_IN",
        "ifsc": "IFSC",
        "mobile": "INDIAN_MOBILE",
    },
    "support_ticket": {
        "customer_name": "PERSON_NAME",
        "upi_vpa": "UPI_VPA",
        "mobile": "INDIAN_MOBILE",
    },
}


@dataclass(frozen=True)
class Task:
    id: str
    doc_id: str
    domain: str
    task_type: str
    # extract_fields only -- field_name -> gold value, or None when this
    # document's domain schema names a field the document didn't include
    # (some templates make a field optional, e.g. support_ticket's address).
    gold_fields: dict[str, str | None] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "doc_id": self.doc_id,
            "domain": self.domain,
            "task_type": self.task_type,
            "gold_fields": self.gold_fields,
        }


def _first_value_per_label(doc: Document, schema: dict[str, str]) -> dict[str, str | None]:
    by_label: dict[str, str] = {}
    for start, end, label in sorted(doc.gold, key=lambda s: s[0]):
        by_label.setdefault(label, doc.text[start:end])
    return {field_name: by_label.get(label) for field_name, label in schema.items()}


def build_tasks(docs: list[Document], seed: int) -> list[Task]:
    """Deterministic per `seed`: same corpus + seed always yields the same
    200 tasks, same order, same ids."""
    rng = random.Random(seed)

    tasks: list[Task] = []
    counter = 0
    for task_type in TASK_TYPES:
        count = TASK_TYPE_COUNTS[task_type]
        eligible = (
            [d for d in docs if d.domain in EXTRACT_FIELD_SCHEMAS]
            if task_type == "extract_fields"
            else list(docs)
        )
        pool = list(eligible)
        rng.shuffle(pool)
        for doc in pool[:count]:
            counter += 1
            gold_fields: dict[str, str | None] = {}
            if task_type == "extract_fields":
                gold_fields = _first_value_per_label(doc, EXTRACT_FIELD_SCHEMAS[doc.domain])
            tasks.append(
                Task(
                    id=f"{VERSION}-{counter:05d}",
                    doc_id=doc.id,
                    domain=doc.domain,
                    task_type=task_type,
                    gold_fields=gold_fields,
                )
            )
    return tasks


def write_tasks(tasks: list[Task], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t.to_json()) + "\n")


def load_tasks(path: Path) -> list[Task]:
    tasks = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            tasks.append(
                Task(
                    id=row["id"],
                    doc_id=row["doc_id"],
                    domain=row["domain"],
                    task_type=row["task_type"],
                    gold_fields=row.get("gold_fields") or {},
                )
            )
    return tasks
