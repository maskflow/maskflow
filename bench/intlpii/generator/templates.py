"""Five domain document templates (signup form, support ticket, CRM note,
security incident report, invoice email). Each builds a document via
DocBuilder, which appends literal prose through realism.apply_noise() and
PII values verbatim -- so a recorded entity span's {start, end} always
exactly matches text[start:end], regardless of noise applied to the
surrounding prose (mirrors bench/indiapii/generator/templates.py).

Prose is drawn from small per-sentence phrasing pools rather than a single
fixed string: a benchmark corpus with 1800 identically-worded documents
makes a small NER model misfire on the *same* sentence-initial token
hundreds of times, which measures the corpus's monotony, not the
detector. Varying the wording keeps the false-positive surface realistic.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import hard_negatives as hn
from . import identifiers as ident
from . import realism

DOMAINS: tuple[str, ...] = (
    "signup_form",
    "support_ticket",
    "crm_note",
    "incident_report",
    "invoice_email",
)


@dataclass
class DocBuilder:
    rng: random.Random
    text: str = ""
    entities: list[dict] = field(default_factory=list)

    def raw(self, chunk: str) -> DocBuilder:
        self.text += chunk
        return self

    def prose(self, chunk: str, **noise: bool) -> DocBuilder:
        self.text += realism.apply_noise(chunk, self.rng, **noise)
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
        **noise: bool,
    ) -> DocBuilder:
        self.prose(f"{label_text}: ", **noise)
        self.entity(value, entity_label, value_class)
        self.raw("\n")
        return self

    def build(self) -> tuple[str, list[dict]]:
        return self.text, self.entities


def _maybe(rng: random.Random, p: float) -> bool:
    return rng.random() < p


def _pick(rng: random.Random, *options: str) -> str:
    return rng.choice(options)


# ---------------------------------------------------------------------------
# 1. signup_form -- form-field layout, field labels supply context keywords.
# ---------------------------------------------------------------------------


def build_signup_form(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    b.raw(
        _pick(rng, "NEW ACCOUNT REGISTRATION\n\n", "Account sign-up\n\n", "Registration form\n\n")
    )
    b.field(
        _pick(rng, "Full Name", "Name", "Account holder"),
        ident.generate_person_name(rng),
        "PERSON_NAME",
        casing=True,
    )
    b.field(
        _pick(rng, "Email Address", "Email", "Contact email"),
        ident.generate_email(rng),
        "EMAIL",
        casing=True,
    )
    b.field(
        _pick(rng, "Phone", "Phone number", "Mobile"),
        ident.generate_phone(rng),
        "PHONE",
        casing=True,
    )
    b.field(
        _pick(rng, "Date of Birth", "DOB", "Birth date"),
        ident.generate_date_of_birth(rng),
        "DATE_OF_BIRTH",
        casing=True,
    )
    b.field(
        _pick(rng, "Mailing Address", "Home address", "Address"),
        ident.generate_address(rng),
        "ADDRESS",
        casing=True,
    )
    if _maybe(rng, 0.55):
        b.field(
            _pick(rng, "SSN", "Social Security Number", "SSN (for tax reporting)"),
            ident.generate_ssn(rng),
            "SSN",
        )
    if _maybe(rng, 0.2):
        b.field(
            _pick(rng, "Referral code", "Promo / order code", "Invite code"),
            hn.generate_order_id_shaped(rng),
            hn.ORDER_ID_SHAPED,
            "hard_negative",
        )
    return b


# ---------------------------------------------------------------------------
# 2. support_ticket -- free prose, inline context.
# ---------------------------------------------------------------------------

_TICKET_SUBJECTS = (
    "Cannot log in to my account",
    "Locked out after password reset",
    "Two-factor code never arrives",
    "Account access issue",
)
_TICKET_OPENERS = (
    "Hello support team,",
    "Hi there,",
    "Afternoon,",
    "To whom it may concern,",
)
_TICKET_CLOSERS = ("Best regards,", "Thanks in advance,", "Appreciate the help,", "Kind regards,")


def build_support_ticket(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    name = ident.generate_person_name(rng)
    b.prose(f"Subject: {_pick(rng, *_TICKET_SUBJECTS)}\n\n{_pick(rng, *_TICKET_OPENERS)}\n\n")
    b.prose(_pick(rng, "My name is ", "This is ", "You have my details on file as "), typo=True)
    b.entity(name, "PERSON_NAME")
    b.prose(
        _pick(
            rng,
            " and I have been locked out since this morning. The best email to reach me is ",
            " and I still can't get in. My email on the account is ",
            ", and I would like this escalated. Contact me at ",
        ),
        typo=True,
    )
    b.entity(ident.generate_email(rng), "EMAIL")
    b.prose(_pick(rng, ", or by phone on ", ". You can also call ", "; my number is "), typo=True)
    b.entity(ident.generate_phone(rng), "PHONE")
    b.raw(".\n")
    if _maybe(rng, 0.5):
        b.prose(
            _pick(
                rng,
                "The order this relates to is ",
                "For reference, order ",
                "It concerns purchase ",
            )
        )
        b.entity(hn.generate_order_id_shaped(rng), hn.ORDER_ID_SHAPED, "hard_negative")
        b.raw(".\n")
    if _maybe(rng, 0.4):
        b.prose(
            _pick(
                rng,
                "To verify me, the card I last used was ",
                "The full card number on the account is ",
                "You can confirm my identity with card ",
            )
        )
        b.entity(ident.generate_credit_card(rng), "CREDIT_CARD")
        b.raw(".\n")
    b.prose(f"\n{_pick(rng, *_TICKET_CLOSERS)}\n", typo=True)
    b.entity(name, "PERSON_NAME")
    return b


# ---------------------------------------------------------------------------
# 3. crm_note -- internal sales/account note.
# ---------------------------------------------------------------------------

_CRM_HEADERS = ("ACCOUNT NOTE\n\n", "Call log\n\n", "Renewal note\n\n", "Customer touchpoint\n\n")


def build_crm_note(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    b.raw(_pick(rng, *_CRM_HEADERS))
    b.prose(_pick(rng, "Spoke with ", "Had a call with ", "Followed up with ", "Met "))
    b.entity(ident.generate_person_name(rng), "PERSON_NAME")
    b.prose(
        _pick(
            rng,
            " about the renewal. Their preferred email is ",
            " regarding the upgrade. Reach them at ",
            " to review pricing. Primary contact email: ",
        )
    )
    b.entity(ident.generate_email(rng), "EMAIL")
    b.prose(_pick(rng, ", direct line ", ". Phone on file: ", "; mobile "))
    b.entity(ident.generate_phone(rng), "PHONE")
    b.raw(".\n")
    b.prose(
        _pick(
            rng,
            "Their office is located at ",
            "Site visit address is ",
            "The registered business address is ",
        )
    )
    b.entity(ident.generate_address(rng), "ADDRESS")
    b.raw(".\n")
    if _maybe(rng, 0.35):
        b.prose(
            _pick(
                rng,
                "Billing IBAN on file is ",
                "Refunds go to IBAN ",
                "The account for direct debit is ",
            )
        )
        b.entity(ident.generate_iban(rng), "IBAN")
        b.raw(".\n")
    if _maybe(rng, 0.3):
        b.prose(
            _pick(
                rng,
                "Disregard the merged case ",
                "The old ticket reference ",
                "Superseded by case ",
            )
        )
        b.entity(hn.generate_order_id_shaped(rng), hn.ORDER_ID_SHAPED, "hard_negative")
        b.raw(".\n")
    return b


# ---------------------------------------------------------------------------
# 4. incident_report -- security incident, credential-heavy.
# ---------------------------------------------------------------------------

_INCIDENT_HEADERS = (
    "SECURITY INCIDENT REPORT\n\n",
    "Incident writeup\n\n",
    "Postmortem: credential exposure\n\n",
)


def build_incident_report(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    b.raw(_pick(rng, *_INCIDENT_HEADERS))
    b.prose(
        _pick(
            rng,
            "Suspicious activity originated from source IP ",
            "The first anomalous request came from ",
            "Traffic was traced back to address ",
        )
    )
    b.entity(ident.generate_ip_address(rng), "IP_ADDRESS")
    b.raw(".\n")
    b.prose(
        _pick(
            rng,
            "An exposed AWS access key ",
            "Investigators found the access key ",
            "The leaked credential was an AWS key, ",
        )
    )
    b.entity(ident.generate_aws_key(rng), "AWS_KEY")
    b.prose(
        _pick(
            rng,
            " together with an application api key ",
            " alongside the service token ",
            " and a hard-coded api key ",
        )
    )
    b.entity(ident.generate_api_key(rng), "API_KEY")
    b.prose(
        _pick(
            rng,
            " were committed to a public repository.\n",
            " had been pushed to an open branch.\n",
            " were visible in the build logs.\n",
        )
    )
    if _maybe(rng, 0.7):
        b.prose(
            _pick(
                rng,
                "The captured session token was ",
                "Attackers also replayed the JWT ",
                "One request carried the bearer token ",
            )
        )
        b.entity(ident.generate_jwt(rng), "JWT")
        b.raw(".\n")
    b.prose(
        _pick(
            rng,
            "Affected user: ",
            "The impacted account belongs to ",
            "Owner of the compromised session: ",
        )
    )
    b.entity(ident.generate_person_name(rng), "PERSON_NAME")
    b.prose(_pick(rng, " (", ", email ", ", reachable at "))
    b.entity(ident.generate_email(rng), "EMAIL")
    b.raw(_pick(rng, ").\n", ".\n", "\n"))
    if _maybe(rng, 0.4):
        b.prose(
            _pick(
                rng,
                "Correlated request trace id ",
                "See internal ticket ",
                "Cross-referenced with log id ",
            )
        )
        b.entity(
            hn.generate_tracking_number_shaped(rng), hn.TRACKING_NUMBER_SHAPED, "hard_negative"
        )
        b.raw(".\n")
    return b


# ---------------------------------------------------------------------------
# 5. invoice_email -- billing / payment confirmation.
# ---------------------------------------------------------------------------

_INVOICE_GREETINGS = ("Hi ", "Hello ", "Dear ", "Hey ")
_INVOICE_OPENERS = (
    "Thank you for your payment. ",
    "Your recent order has been processed. ",
    "This confirms your purchase. ",
    "We have received your payment. ",
)


def build_invoice_email(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    name = ident.generate_person_name(rng)
    b.prose("From: ")
    b.entity(ident.generate_email(rng), "EMAIL")
    b.prose("\nTo: ")
    b.entity(ident.generate_email(rng), "EMAIL")
    b.prose(
        f"\nSubject: {_pick(rng, 'Your invoice', 'Payment received', 'Order confirmation')}\n\n"
    )
    b.prose(_pick(rng, *_INVOICE_GREETINGS))
    b.entity(name, "PERSON_NAME")
    b.prose(",\n\n" + _pick(rng, *_INVOICE_OPENERS))
    b.prose(
        _pick(
            rng, "The card charged was ", "We billed card number ", "Payment was taken from card "
        )
    )
    b.entity(ident.generate_credit_card(rng), "CREDIT_CARD")
    b.raw(".\n")
    b.prose(
        _pick(
            rng,
            "Any refund will be returned to IBAN ",
            "Refunds are issued to account ",
            "Your registered IBAN for credits is ",
        )
    )
    b.entity(ident.generate_iban(rng), "IBAN")
    b.raw(".\n")
    b.prose(_pick(rng, "Ship to: ", "Delivery address: ", "Shipping to "))
    b.entity(ident.generate_address(rng), "ADDRESS")
    b.raw("\n")
    b.field(
        _pick(rng, "Invoice number", "Reference", "Order ref"),
        hn.generate_order_id_shaped(rng),
        hn.ORDER_ID_SHAPED,
        "hard_negative",
    )
    if _maybe(rng, 0.3):
        b.field(
            _pick(rng, "Authorization code", "Transaction id", "Auth ref"),
            hn.generate_tracking_number_shaped(rng),
            hn.TRACKING_NUMBER_SHAPED,
            "hard_negative",
        )
    return b


_BUILDERS = {
    "signup_form": build_signup_form,
    "support_ticket": build_support_ticket,
    "crm_note": build_crm_note,
    "incident_report": build_incident_report,
    "invoice_email": build_invoice_email,
}


def generate_document(domain: str, doc_id: str, rng: random.Random) -> dict:
    text, entities = _BUILDERS[domain](rng).build()
    return {"id": doc_id, "text": text, "entities": entities, "domain": domain, "lang": "en"}
