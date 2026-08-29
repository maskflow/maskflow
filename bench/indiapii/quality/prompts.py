"""Task-type x domain instruction templates. Kept separate from tasks.py so
a wording tweak doesn't require regenerating quality-v1.0.jsonl -- a task
spec references (task_type, domain), not a frozen instruction string.
"""

from __future__ import annotations

from .tasks import EXTRACT_FIELD_SCHEMAS

_SUMMARIZE: dict[str, str] = {
    "support_ticket": (
        "Write a 2-4 sentence internal handoff summary for the next support "
        "agent: what the customer needs, and what's still pending."
    ),
    "insurance_claim": (
        "Write a 2-4 sentence internal handoff summary for the claims "
        "adjuster: who filed, what's needed to process payout, and any "
        "reference details a colleague would need to locate this case."
    ),
    "medical_note": (
        "Write a 2-4 sentence internal handoff summary for the next "
        "clinician: presenting complaint and current status."
    ),
    "hr_record": (
        "Write a 2-sentence internal note confirming this employee record "
        "is complete and ready for payroll onboarding, or flagging what's "
        "missing."
    ),
    "bank_chat": (
        "Write a 2-4 sentence internal handoff summary of this chat for the "
        "next support agent: what the customer is asking for and what's "
        "still needed to resolve it."
    ),
    "kyc_form": (
        "Write a 2-4 sentence internal handoff summary for the compliance "
        "reviewer: applicant details relevant to review, and whether the "
        "submission looks complete."
    ),
    "loan_application": (
        "Write a 2-4 sentence internal handoff summary for the underwriter: "
        "applicant details relevant to underwriting, and what's needed next."
    ),
}

_DRAFT_REPLY: dict[str, str] = {
    "support_ticket": (
        "You are a support agent. Write a short, professional reply "
        "(3-6 sentences) addressing the customer by name, acknowledging "
        "their specific issue, and stating the next step."
    ),
    "insurance_claim": (
        "You are a claims officer. Write a short, professional reply "
        "(3-6 sentences) acknowledging receipt of this claim, addressing "
        "the policyholder by name, and stating the next step in processing."
    ),
    "bank_chat": (
        "As the bank agent, write the next chat message (under 3 sentences) "
        "confirming the details received and stating the verification "
        "timeline, matching the chat's casual register."
    ),
    "loan_application": (
        "You are a loan officer. Write a short, professional reply "
        "(3-6 sentences) acknowledging this application, addressing the "
        "applicant by name, and stating what happens next."
    ),
    "kyc_form": (
        "You are a compliance reviewer. Write a short, professional reply "
        "(3-6 sentences) to the applicant confirming receipt of their KYC "
        "submission and requesting any missing information."
    ),
    "hr_record": (
        "You are an HR coordinator. Write a short, professional reply "
        "(3-6 sentences) to the employee confirming their record has been "
        "set up, and stating any next step."
    ),
    "medical_note": (
        "You are a clinic administrator. Write a short, professional "
        "message (3-6 sentences) to the patient confirming their discharge "
        "summary is on file, and stating any follow-up instructions."
    ),
}


def summarize_instruction(domain: str) -> str:
    return _SUMMARIZE[domain]


def draft_reply_instruction(domain: str) -> str:
    return _DRAFT_REPLY[domain]


def extract_fields_instruction(domain: str) -> str:
    fields = ", ".join(EXTRACT_FIELD_SCHEMAS[domain].keys())
    return (
        "Extract these fields from the document as strict JSON with exactly "
        f"these keys: {fields}. Use null for any field that is not present "
        "in the document. Return only the JSON object, no other text."
    )


def instruction_for(task_type: str, domain: str) -> str:
    if task_type == "summarize":
        return summarize_instruction(domain)
    if task_type == "draft_reply":
        return draft_reply_instruction(domain)
    if task_type == "extract_fields":
        return extract_fields_instruction(domain)
    raise ValueError(f"unknown task_type: {task_type!r}")
