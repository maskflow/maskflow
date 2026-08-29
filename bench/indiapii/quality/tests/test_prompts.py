from __future__ import annotations

import pytest

from bench.indiapii.quality import prompts
from bench.indiapii.quality.tasks import EXTRACT_FIELD_SCHEMAS

# Every domain the corpus actually generates (see
# bench/indiapii/generator/templates.py's DOMAINS) -- summarize/draft_reply
# must cover all of them since build_tasks() doesn't restrict those two
# task types to a domain subset.
_ALL_DOMAINS = (
    "support_ticket",
    "kyc_form",
    "insurance_claim",
    "medical_note",
    "hr_record",
    "bank_chat",
    "loan_application",
)


@pytest.mark.parametrize("domain", _ALL_DOMAINS)
def test_summarize_covers_every_domain(domain: str) -> None:
    assert prompts.summarize_instruction(domain)


@pytest.mark.parametrize("domain", _ALL_DOMAINS)
def test_draft_reply_covers_every_domain(domain: str) -> None:
    assert prompts.draft_reply_instruction(domain)


@pytest.mark.parametrize("domain", EXTRACT_FIELD_SCHEMAS.keys())
def test_extract_fields_instruction_lists_every_schema_field(domain: str) -> None:
    instruction = prompts.extract_fields_instruction(domain)
    for field_name in EXTRACT_FIELD_SCHEMAS[domain]:
        assert field_name in instruction


def test_instruction_for_dispatches_by_task_type() -> None:
    assert prompts.instruction_for("summarize", "kyc_form") == prompts.summarize_instruction(
        "kyc_form"
    )
    assert prompts.instruction_for(
        "draft_reply", "support_ticket"
    ) == prompts.draft_reply_instruction("support_ticket")
    assert prompts.instruction_for(
        "extract_fields", "loan_application"
    ) == prompts.extract_fields_instruction("loan_application")


def test_instruction_for_rejects_unknown_task_type() -> None:
    with pytest.raises(ValueError):
        prompts.instruction_for("not_a_real_task_type", "kyc_form")
