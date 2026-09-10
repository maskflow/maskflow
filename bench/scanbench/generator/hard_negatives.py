"""Confusable-but-not-PII strings that pervade real logs. Each returns a
plain string; shapes.py records it under a shape-descriptive label (never a
real PIIType), so any real label a detector fires on one of these spans is
scored as a false positive.

None of these is engineered against a single validator -- they are just the
texture of log lines: opaque ids, hashes, timestamps, paths, framework
noise. A detector that stays quiet on them is what "precision on log input"
measures.
"""

from __future__ import annotations

import random
import string
import uuid

TRACE_ID = "TRACE_ID"
REQUEST_ID = "REQUEST_ID"
UUID4 = "UUID4"
GIT_SHA = "GIT_SHA"
EPOCH_MS = "EPOCH_MS"
INTERNAL_IP = "INTERNAL_IP"
FILE_FRAME = "FILE_FRAME"
DOTTED_CLASSPATH = "DOTTED_CLASSPATH"
USER_AGENT = "USER_AGENT"
OPAQUE_KEYISH = "OPAQUE_KEYISH"
HEX_BLOB = "HEX_BLOB"

ALL_LABELS = (
    TRACE_ID,
    REQUEST_ID,
    UUID4,
    GIT_SHA,
    EPOCH_MS,
    INTERNAL_IP,
    FILE_FRAME,
    DOTTED_CLASSPATH,
    USER_AGENT,
    OPAQUE_KEYISH,
    HEX_BLOB,
)

_HEX = "0123456789abcdef"
_JAVA_CLASSES = (
    "com.acme.payment.PaymentService",
    "com.acme.kyc.VerificationController",
    "io.acme.worker.PayoutHandler",
    "org.springframework.web.servlet.DispatcherServlet",
    "com.acme.billing.InvoiceRepository",
    "net.stripe.gateway.ChargeClient",
    "com.acme.auth.TokenValidator",
    "io.grpc.internal.ClientCallImpl",
    "com.zaxxer.hikari.pool.HikariPool",
    "com.acme.notify.EmailDispatcher",
)
_METHODS = ("charge", "handle", "process", "invoke", "execute", "call", "doFilter", "run")
_SRC_FILES = (
    "PaymentService.java",
    "VerificationController.java",
    "PayoutHandler.kt",
    "worker.py",
    "handlers.go",
    "routes.rb",
    "InvoiceRepository.java",
    "ChargeClient.scala",
    "TokenValidator.java",
    "server.ts",
)
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/129.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.6",
    "curl/8.7.1",
    "python-requests/2.32.3",
    "Go-http-client/2.0",
    "PostmanRuntime/7.39.0",
    "okhttp/4.12.0",
    "axios/1.7.2",
)


def _hex(rng: random.Random, n: int) -> str:
    return "".join(rng.choice(_HEX) for _ in range(n))


def generate_trace_id(rng: random.Random) -> str:
    return _hex(rng, 32)


def generate_request_id(rng: random.Random) -> str:
    prefix = rng.choice(("req_", "chatcmpl-", "run-", "evt_"))
    aln = string.ascii_lowercase + string.digits
    return prefix + "".join(rng.choice(aln) for _ in range(rng.choice((10, 12, 16, 24))))


def generate_uuid4(rng: random.Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def generate_git_sha(rng: random.Random) -> str:
    return _hex(rng, 40)


def generate_epoch_ms(rng: random.Random) -> str:
    return str(rng.randint(1_700_000_000_000, 1_800_000_000_000))


def generate_internal_ip(rng: random.Random) -> str:
    kind = rng.choice(("10", "172", "192"))
    if kind == "10":
        return f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
    if kind == "172":
        return f"172.{rng.randint(16, 31)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
    return f"192.168.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


def generate_file_frame(rng: random.Random) -> str:
    return f"{rng.choice(_SRC_FILES)}:{rng.randint(12, 900)}"


def method_name(rng: random.Random) -> str:
    return rng.choice(_METHODS)


def generate_dotted_classpath(rng: random.Random) -> str:
    return rng.choice(_JAVA_CLASSES)


def generate_user_agent(rng: random.Random) -> str:
    return rng.choice(_UA)


def generate_opaque_keyish(rng: random.Random) -> str:
    """A token that reads like a secret but matches no API_KEY / AWS_KEY /
    JWT shape: Stripe-style `sk_test_` (underscore, too short), a hyphen-id,
    or a bare base64-ish run with no `eyJ` head."""
    style = rng.choice(("stripe_test", "hyphen_id", "b64"))
    aln = string.ascii_letters + string.digits
    if style == "stripe_test":
        return "sk_test_" + "".join(rng.choice(aln) for _ in range(rng.choice((8, 12, 16))))
    if style == "hyphen_id":
        return "-".join("".join(rng.choice(aln) for _ in range(4)) for _ in range(4))
    return "".join(rng.choice(aln + "+/") for _ in range(rng.choice((18, 22, 30))))


def generate_hex_blob(rng: random.Random) -> str:
    if rng.random() < 0.5:
        return "0x" + _hex(rng, rng.choice((8, 12, 16)))
    return _hex(rng, rng.choice((12, 16, 24)))


GENERATORS = {
    TRACE_ID: generate_trace_id,
    REQUEST_ID: generate_request_id,
    UUID4: generate_uuid4,
    GIT_SHA: generate_git_sha,
    EPOCH_MS: generate_epoch_ms,
    INTERNAL_IP: generate_internal_ip,
    FILE_FRAME: generate_file_frame,
    DOTTED_CLASSPATH: generate_dotted_classpath,
    USER_AGENT: generate_user_agent,
    OPAQUE_KEYISH: generate_opaque_keyish,
    HEX_BLOB: generate_hex_blob,
}
