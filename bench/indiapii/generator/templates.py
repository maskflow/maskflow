"""Seven domain document templates (support ticket, KYC form, insurance
claim, medical note, HR record, bank chat, loan application). Each builds a
document via DocBuilder, which appends literal prose through realism.apply_
noise() and identifier values verbatim -- so a recorded entity span's
{start, end} always exactly matches text[start:end], regardless of what
noise was applied to the surrounding prose (see realism.py's docstring).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import hard_negatives as hn
from . import identifiers as ident
from . import realism

DOMAINS: tuple[str, ...] = (
    "support_ticket",
    "kyc_form",
    "insurance_claim",
    "medical_note",
    "hr_record",
    "bank_chat",
    "loan_application",
)


@dataclass
class DocBuilder:
    rng: random.Random
    text: str = ""
    entities: list[dict] = field(default_factory=list)

    def raw(self, chunk: str) -> DocBuilder:
        self.text += chunk
        return self

    def prose(self, chunk: str, **noise_kwargs: bool) -> DocBuilder:
        self.text += realism.apply_noise(chunk, self.rng, **noise_kwargs)
        return self

    def entity(self, value: str, label: str, value_class: str = "positive") -> DocBuilder:
        start = len(self.text)
        self.text += value
        self.entities.append(
            {"start": start, "end": len(self.text), "label": label, "value_class": value_class}
        )
        return self

    def field(
        self,
        label_text: str,
        value: str,
        entity_label: str,
        value_class: str = "positive",
        **noise_kwargs: bool,
    ) -> DocBuilder:
        self.prose(f"{label_text}: ", **noise_kwargs)
        self.entity(value, entity_label, value_class)
        self.raw("\n")
        return self

    def build(self) -> tuple[str, list[dict]]:
        return self.text, self.entities


def _maybe(rng: random.Random, p: float) -> bool:
    return rng.random() < p


# ---------------------------------------------------------------------------
# 1. support_ticket
# ---------------------------------------------------------------------------


def build_support_ticket(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    name = ident.generate_person_name(rng)
    b.prose("Subject: Unable to complete UPI payment\n\n", whatsapp=True)
    b.prose("Hi Support Team,\nMy name is ", whatsapp=True, typo=True)
    b.entity(name, "PERSON_NAME")
    b.prose(
        " and I am facing an issue sending money using my UPI ID ",
        whatsapp=True,
        typo=True,
        hinglish_splice=True,
    )
    b.entity(ident.generate_upi_vpa(rng), "UPI_VPA")
    b.raw(".\n")
    b.field(
        "Registered mobile", ident.generate_indian_mobile(rng), "INDIAN_MOBILE", whatsapp=True
    )
    b.field(
        "Order reference", hn.generate_order_id_shaped(rng), hn.ORDER_ID_SHAPED, "hard_negative"
    )
    if _maybe(rng, 0.3):
        b.field("Delivery address", ident.generate_indian_address(rng), "INDIAN_ADDRESS")
    b.prose(
        "Please resolve this on priority, it is very urgent.\n\nRegards,\n",
        whatsapp=True,
        hinglish_splice=True,
    )
    b.entity(name, "PERSON_NAME")
    return b


# ---------------------------------------------------------------------------
# 2. kyc_form
# ---------------------------------------------------------------------------


def build_kyc_form(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    name = ident.generate_person_name(rng)
    b.raw("KYC APPLICATION FORM\n\n")
    b.field("Applicant Name", name, "PERSON_NAME")
    b.field("Aadhaar Number", ident.generate_aadhaar(rng), "AADHAAR")
    b.field("PAN", ident.generate_pan(rng), "PAN")
    if _maybe(rng, 0.4):
        b.field("Voter ID (EPIC)", ident.generate_voter_id(rng), "VOTER_ID")
    if _maybe(rng, 0.3):
        b.field("Passport Number", ident.generate_indian_passport(rng), "INDIAN_PASSPORT")
    if _maybe(rng, 0.2):
        b.field(
            "Previously submitted Aadhaar (under correction)",
            hn.generate_non_verhoeff_aadhaar(rng),
            hn.NON_VERHOEFF_AADHAAR_SHAPED,
            "hard_negative",
        )
    b.field("Residential Address", ident.generate_indian_address(rng), "INDIAN_ADDRESS")
    b.field("PIN Code", ident.generate_pin_code(rng), "PIN_CODE")
    b.field("Mobile Number", ident.generate_indian_mobile(rng), "INDIAN_MOBILE")
    return b


# ---------------------------------------------------------------------------
# 3. insurance_claim
# ---------------------------------------------------------------------------


def build_insurance_claim(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    name = ident.generate_person_name(rng)
    b.raw("MOTOR INSURANCE CLAIM FORM\n\n")
    b.field("Policyholder Name", name, "PERSON_NAME")
    b.field("Vehicle Registration No", ident.generate_vehicle_reg(rng), "VEHICLE_REG")
    b.field("Driving Licence No", ident.generate_driving_licence(rng), "DRIVING_LICENCE")
    b.field("Bank Account Number", ident.generate_bank_account(rng), "BANK_ACCOUNT_IN")
    b.field("IFSC Code", ident.generate_ifsc(rng), "IFSC")
    b.field("Contact Number", ident.generate_indian_mobile(rng), "INDIAN_MOBILE")
    b.field(
        "Incident Date/Time",
        hn.generate_timestamp_shaped(rng),
        hn.TIMESTAMP_SHAPED,
        "hard_negative",
    )
    if _maybe(rng, 0.5):
        b.field(
            "Claim Reference", hn.generate_order_id_shaped(rng), hn.ORDER_ID_SHAPED, "hard_negative"
        )
    if _maybe(rng, 0.35):
        b.field(
            "Garage Invoice No",
            hn.generate_pan_shaped_invoice_no(rng),
            hn.PAN_SHAPED_INVOICE_NO,
            "hard_negative",
        )
    return b


# ---------------------------------------------------------------------------
# 4. medical_note
# ---------------------------------------------------------------------------


def build_medical_note(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    name = ident.generate_person_name(rng)
    b.raw("DISCHARGE SUMMARY\n\n")
    b.field("Patient Name", name, "PERSON_NAME")
    b.field("ABHA Number", ident.generate_abha_number(rng), "ABHA_NUMBER")
    if _maybe(rng, 0.5):
        b.field("ABHA Address", ident.generate_abha_address(rng), "ABHA_ADDRESS")
    b.field("Address", ident.generate_indian_address(rng), "INDIAN_ADDRESS")
    b.field("PIN", ident.generate_pin_code(rng), "PIN_CODE")
    b.prose("\nPatient was admitted on ", typo=True)
    b.entity(hn.generate_timestamp_shaped(rng), hn.TIMESTAMP_SHAPED, "hard_negative")
    b.prose(" with complaints of fever and was discharged in stable condition.\n", typo=True)
    if _maybe(rng, 0.3):
        b.field("Contact Number", ident.generate_indian_mobile(rng), "INDIAN_MOBILE")
    return b


# ---------------------------------------------------------------------------
# 5. hr_record
# ---------------------------------------------------------------------------


def build_hr_record(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    name = ident.generate_person_name(rng)
    b.raw("EMPLOYEE MASTER RECORD\n\n")
    b.field("Employee Name", name, "PERSON_NAME")
    b.field("PAN", ident.generate_pan(rng), "PAN")
    b.field("Aadhaar Number", ident.generate_aadhaar(rng), "AADHAAR")
    b.field("Bank Account Number", ident.generate_bank_account(rng), "BANK_ACCOUNT_IN")
    b.field("IFSC", ident.generate_ifsc(rng), "IFSC")
    b.field("Mobile", ident.generate_indian_mobile(rng), "INDIAN_MOBILE")
    b.field("Address", ident.generate_indian_address(rng), "INDIAN_ADDRESS")
    if _maybe(rng, 0.25):
        b.field(
            "Employee ID", hn.generate_order_id_shaped(rng), hn.ORDER_ID_SHAPED, "hard_negative"
        )
    return b


# ---------------------------------------------------------------------------
# 6. bank_chat -- WhatsApp-style, heaviest Hinglish/code-mixing knob.
# ---------------------------------------------------------------------------


def build_bank_chat(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    customer = ident.generate_person_name(rng).split()[0]
    b.prose(f"[10:{rng.randint(10, 59):02d}] {customer}: Sir maine payment bheja hai apke UPI ")
    b.entity(ident.generate_upi_vpa(rng), "UPI_VPA")
    b.prose(" pe, please check karo\n", whatsapp=True, hinglish_splice=True)
    b.prose(
        f"[10:{rng.randint(10, 59):02d}] Agent: Kripya apna account number aur IFSC bhejiye\n",
        devanagari_splice=True,
    )
    b.prose(
        f"[10:{rng.randint(10, 59):02d}] Agent: Verification ke liye, hamare records mein aapka "
        "Aadhaar ",
    )
    b.entity(ident.generate_aadhaar_masked(rng), "AADHAAR_MASKED")
    b.prose(" dikh raha hai, confirm karein\n", hinglish_splice=True)
    b.prose(f"[10:{rng.randint(10, 59):02d}] {customer}: Account: ")
    b.entity(ident.generate_bank_account(rng), "BANK_ACCOUNT_IN")
    b.prose(", IFSC: ")
    b.entity(ident.generate_ifsc(rng), "IFSC")
    b.raw("\n")
    b.prose(
        f"[10:{rng.randint(10, 59):02d}] {customer}: mera mobile number ",
        whatsapp=True,
        hinglish_splice=True,
    )
    b.entity(ident.generate_indian_mobile(rng, with_prefix=_maybe(rng, 0.5)), "INDIAN_MOBILE")
    b.raw(" hai, thanks\n")
    if _maybe(rng, 0.3):
        b.prose(
            f"[10:{rng.randint(10, 59):02d}] {customer}: maine payment id ke liye email diya tha ",
            whatsapp=True,
        )
        b.entity(hn.generate_vpa_shaped_email(rng), hn.VPA_SHAPED_EMAIL, "hard_negative")
        b.raw(" us par bhi confirm kar dena\n")
    return b


# ---------------------------------------------------------------------------
# 7. loan_application
# ---------------------------------------------------------------------------


def build_loan_application(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    name = ident.generate_person_name(rng)
    b.raw("PERSONAL LOAN APPLICATION\n\n")
    b.field("Applicant Name", name, "PERSON_NAME")
    b.field("PAN", ident.generate_pan(rng), "PAN")
    b.field("Aadhaar Number", ident.generate_aadhaar(rng), "AADHAAR")
    if _maybe(rng, 0.4):
        b.field("GSTIN (if self-employed)", ident.generate_gstin(rng), "GSTIN")
    b.field("Bank Account Number", ident.generate_bank_account(rng), "BANK_ACCOUNT_IN")
    b.field("IFSC Code", ident.generate_ifsc(rng), "IFSC")
    b.field("Mobile Number", ident.generate_indian_mobile(rng), "INDIAN_MOBILE")
    b.field("Residential Address", ident.generate_indian_address(rng), "INDIAN_ADDRESS")
    b.field("PIN Code", ident.generate_pin_code(rng), "PIN_CODE")
    if _maybe(rng, 0.2):
        b.field(
            "Application Reference",
            hn.generate_order_id_shaped(rng),
            hn.ORDER_ID_SHAPED,
            "hard_negative",
        )
    return b


_BUILDERS = {
    "support_ticket": build_support_ticket,
    "kyc_form": build_kyc_form,
    "insurance_claim": build_insurance_claim,
    "medical_note": build_medical_note,
    "hr_record": build_hr_record,
    "bank_chat": build_bank_chat,
    "loan_application": build_loan_application,
}

_HINGLISH_DOMAINS = frozenset({"bank_chat", "support_ticket"})


def generate_document(domain: str, doc_id: str, rng: random.Random) -> dict:
    builder = _BUILDERS[domain](rng)
    text, entities = builder.build()
    lang = "hi-en" if domain in _HINGLISH_DOMAINS else "en"
    return {"id": doc_id, "text": text, "entities": entities, "domain": domain, "lang": lang}
