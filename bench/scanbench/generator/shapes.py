"""Five log-record shape builders. Each returns (text, entities) where a
recorded span's {start, end} exactly matches text[start:end] -- values are
appended verbatim through DocBuilder.entity(), noise only ever goes through
.raw()/.prose() around them (mirrors bench/intlpii/generator/templates.py).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from bench.indiapii.generator import identifiers as ind
from bench.intlpii.generator import identifiers as intl

from . import hard_negatives as hn

SHAPES: tuple[str, ...] = (
    "access_log",
    "app_json",
    "stack_trace",
    "llm_traffic",
    "worker_log",
)

_LEVELS = ("INFO", "WARN", "ERROR", "DEBUG")
_LOGGERS = ("kyc.service", "payment.api", "auth.gateway", "payout.worker", "http.access")
_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH")
_ROUTES = ("/api/v2/lookup", "/v1/customers", "/internal/kyc", "/accounts/detail", "/billing/rec")
_MSG_VERBS = ("verified", "processed", "updated record for", "onboarded", "reconciled")
_EXCEPTIONS = (
    "com.acme.PaymentException",
    "java.lang.IllegalStateException",
    "com.acme.SettlementError",
    "org.postgresql.util.PSQLException",
    "com.acme.KycRejectedException",
)
_TRACE_MSGS = (
    "failed charge for",
    "settlement rejected for",
    "declined transaction for",
    "retry exhausted for",
)
_GST_PHRASES = ("gstin=", "tax_id=", "gst_no:", "reg=")


@dataclass
class DocBuilder:
    rng: random.Random
    text: str = ""
    entities: list[dict] = field(default_factory=list)

    def raw(self, chunk: str) -> DocBuilder:
        self.text += chunk
        return self

    def entity(self, value: str, label: str, value_class: str = "positive") -> DocBuilder:
        start = len(self.text)
        self.text += value
        self.entities.append(
            {"start": start, "end": len(self.text), "label": label, "value_class": value_class}
        )
        return self

    def pii(self, value: str, label: str) -> DocBuilder:
        return self.entity(value, label, "positive")

    def decoy(self, value: str, label: str) -> DocBuilder:
        return self.entity(value, label, "hard_negative")

    def build(self) -> tuple[str, list[dict]]:
        return self.text, self.entities


def _maybe(rng: random.Random, p: float) -> bool:
    return rng.random() < p


def _ts(rng: random.Random, *, millis: bool = False) -> str:
    y, mo, d = 2026, rng.randint(1, 12), rng.randint(1, 28)
    h, mi, s = rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59)
    base = f"{y}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}"
    return f"{base},{rng.randint(0, 999):03d}" if millis else base


# ---------------------------------------------------------------------------
# 1. access_log -- nginx / ALB combined format, PII in the query string.
# ---------------------------------------------------------------------------


def build_access_log(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    b.pii(intl.generate_ip_address(rng), "IP_ADDRESS")
    b.raw(" - - [")
    d = rng.randint(1, 28)
    b.raw(f"{d:02d}/Sep/2026:{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00 +0000] ")
    params = []
    if _maybe(rng, 0.8):
        params.append(("email", intl.generate_email(rng), "EMAIL"))
    if _maybe(rng, 0.5):
        params.append(
            ("mobile", ind.generate_indian_mobile(rng, with_prefix=False), "INDIAN_MOBILE")
        )
    if _maybe(rng, 0.4):
        params.append(("uid", ind.generate_aadhaar(rng), "AADHAAR"))
    b.raw(f'"{rng.choice(_METHODS)} {rng.choice(_ROUTES)}?')
    for i, (k, value, label) in enumerate(params):
        if i:
            b.raw("&")
        b.raw(f"{k}=")
        b.pii(value, label)
    if not params:
        b.raw("q=health")
    b.raw(' HTTP/1.1" 200 ')
    b.raw(f"{rng.randint(120, 9000)} ")
    b.raw('"-" "')
    b.decoy(hn.generate_user_agent(rng), hn.USER_AGENT)
    b.raw('"')
    if _maybe(rng, 0.35):
        b.raw(' "Bearer ')
        b.pii(intl.generate_jwt(rng), "JWT")
        b.raw('"')
    b.raw(" xff=")
    b.decoy(hn.generate_internal_ip(rng), hn.INTERNAL_IP)
    b.raw(" rid=")
    b.decoy(hn.generate_request_id(rng), hn.REQUEST_ID)
    return b


# ---------------------------------------------------------------------------
# 2. app_json -- structured log line, PII in `msg`, creds sometimes leaked.
# ---------------------------------------------------------------------------


def build_app_json(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    b.raw('{"ts":"')
    b.raw(_ts(rng).replace(" ", "T") + "Z")
    b.raw(f'","level":"{rng.choice(_LEVELS)}","logger":"')
    b.decoy(hn.generate_dotted_classpath(rng), hn.DOTTED_CLASSPATH)
    b.raw('","trace_id":"')
    b.decoy(hn.generate_trace_id(rng), hn.TRACE_ID)
    b.raw(f'","msg":"{rng.choice(_MSG_VERBS)} ')
    b.pii(ind.generate_person_name(rng), "PERSON_NAME")
    b.raw(" pan ")
    b.pii(ind.generate_pan(rng), "PAN")
    if _maybe(rng, 0.6):
        b.raw(" mobile ")
        b.pii(ind.generate_indian_mobile(rng), "INDIAN_MOBILE")
    if _maybe(rng, 0.45):
        b.raw(" via key ")
        b.pii(intl.generate_api_key(rng), "API_KEY")
    if _maybe(rng, 0.3):
        b.raw(" aws=")
        b.pii(intl.generate_aws_key(rng), "AWS_KEY")
    b.raw('","request_id":"')
    b.decoy(hn.generate_request_id(rng), hn.REQUEST_ID)
    b.raw('"}')
    return b


# ---------------------------------------------------------------------------
# 3. stack_trace -- multi-line exception, PII in the message lines.
# ---------------------------------------------------------------------------


def build_stack_trace(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    b.raw(f"{_ts(rng, millis=True)} ERROR [http-nio-8080-exec-{rng.randint(1, 40)}] ")
    b.decoy(hn.generate_dotted_classpath(rng), hn.DOTTED_CLASSPATH)
    b.raw(f" - {rng.choice(_TRACE_MSGS)} ")
    b.pii(ind.generate_person_name(rng), "PERSON_NAME")
    b.raw(f"\n{rng.choice(_EXCEPTIONS)}: card ")
    b.pii(intl.generate_credit_card(rng), "CREDIT_CARD")
    b.raw(" declined, settlement IFSC ")
    b.pii(ind.generate_ifsc(rng), "IFSC")
    if _maybe(rng, 0.5):
        b.raw(", notify ")
        b.pii(intl.generate_email(rng), "EMAIL")
    for _ in range(rng.choice((2, 3))):
        b.raw("\n\tat ")
        b.decoy(hn.generate_dotted_classpath(rng), hn.DOTTED_CLASSPATH)
        b.raw(f".{hn.method_name(rng)}(")
        b.decoy(hn.generate_file_frame(rng), hn.FILE_FRAME)
        b.raw(")")
    return b


# ---------------------------------------------------------------------------
# 4. llm_traffic -- an OpenAI/Anthropic request dump, PII in messages[].
# ---------------------------------------------------------------------------


def build_llm_traffic(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    b.raw('{"request_id":"')
    b.decoy(hn.generate_request_id(rng), hn.REQUEST_ID)
    b.raw(f'","model":"{rng.choice(("gpt-4o", "claude-sonnet-4", "gemini-1.5-pro"))}",')
    b.raw('"messages":[{"role":"user","content":"Draft a note to ')
    b.pii(ind.generate_person_name(rng), "PERSON_NAME")
    b.raw(" at ")
    b.pii(intl.generate_email(rng), "EMAIL")
    b.raw(f" {rng.choice(_GST_PHRASES)}")
    b.pii(ind.generate_gstin(rng), "GSTIN")
    if _maybe(rng, 0.5):
        b.raw(" and Aadhaar ")
        b.pii(ind.generate_aadhaar(rng), "AADHAAR")
    if _maybe(rng, 0.4):
        b.raw(" UPI ")
        b.pii(ind.generate_upi_vpa(rng), "UPI_VPA")
    b.raw('"}],"usage":{"prompt_tokens":')
    b.raw(f'{rng.randint(80, 900)},"total_tokens":{rng.randint(200, 1600)}}}')
    return b


# ---------------------------------------------------------------------------
# 5. worker_log -- celery/sidekiq style task line.
# ---------------------------------------------------------------------------


def build_worker_log(rng: random.Random) -> DocBuilder:
    b = DocBuilder(rng)
    b.raw(f"[{_ts(rng)}] [{rng.choice(_LOGGERS)}] Task process_payout[")
    b.decoy(hn.generate_uuid4(rng), hn.UUID4)
    b.raw("] succeeded: sent to UPI ")
    b.pii(ind.generate_upi_vpa(rng), "UPI_VPA")
    b.raw(" for ")
    b.pii(ind.generate_person_name(rng), "PERSON_NAME")
    if _maybe(rng, 0.6):
        b.raw(" (mobile ")
        b.pii(ind.generate_indian_mobile(rng, with_prefix=False), "INDIAN_MOBILE")
        b.raw(")")
    b.raw(" ref=")
    b.decoy(hn.generate_opaque_keyish(rng), hn.OPAQUE_KEYISH)
    if _maybe(rng, 0.3):
        b.raw(" ts=")
        b.decoy(hn.generate_epoch_ms(rng), hn.EPOCH_MS)
    return b


_BUILDERS = {
    "access_log": build_access_log,
    "app_json": build_app_json,
    "stack_trace": build_stack_trace,
    "llm_traffic": build_llm_traffic,
    "worker_log": build_worker_log,
}


def generate_document(shape: str, doc_id: str, rng: random.Random) -> dict:
    text, entities = _BUILDERS[shape](rng).build()
    return {"id": doc_id, "text": text, "entities": entities, "domain": shape, "lang": "en"}
