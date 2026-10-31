"""Find canary values inside a captured request payload.

A naive substring search finds the easy half. Real applications reformat on
the way out: an Aadhaar read as 12 digits is sent as `1234 5678 9012`, a
name is upper-cased, a payload is base64'd into a multipart body, and a
value gets split across two JSON fields and only reassembled by the
provider's own template. Each of those is still a leak, and a detector that
misses them produces a clean report for a leaking app -- the single worst
outcome this tool can produce.

So every canary is searched for in:

  * its raw form;
  * case-folded, and with spaces / dashes / dots stripped from BOTH the
    needle and the haystack, so any grouping finds any other;
  * all four unicode normal forms;
  * base64 (standard and url-safe), for values embedded in an encoded body;
  * and, for digit-only values, as an ordered digit run with arbitrary
    separators -- which is what catches `"uid_part_1" .. "uid_part_4"`
    reassembled into one prompt.

The split-across-JSON-fields case deserves a note. We do **not** try to
reassemble arbitrary field combinations -- that is exponential and would
manufacture false positives. We look for the digits of the canary appearing
in order in the payload, which is exactly what happens once the application
itself has done the reassembly on the way to the provider. If the payload
genuinely carries four separate fragments and never joins them, no escape
is reported, which is the honest answer: nothing leaked that the provider
could read as an identifier.
"""

from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass, field

#: Characters an application might insert into an identifier for display.
_SEPARATORS = " -. ‑\t_/"

#: Shortest value worth searching for. Below this a match is as likely to
#: be coincidence as a leak -- a 4-digit PIN code appears in any timestamp
#: -- and a false confirmed-leak is worse than a missed one here, because
#: "confirmed" is the word the whole product rests on.
MIN_SEARCHABLE = 6

#: Shortest DIGIT-ONLY value eligible for the digit-run form, which is far
#: more permissive than the others: it strips every non-digit from the whole
#: payload, so a short value can match by coincidence. Twelve specific
#: digits in a 10k-digit payload collide with probability ~1e-8; six digits
#: collide at ~1%, which would be a fabricated "confirmed leak". Aadhaar
#: (12), mobile (10) and bank accounts (9-18) qualify; a 6-digit PIN code
#: deliberately does not, and is caught by the other forms or not at all.
MIN_DIGIT_RUN = 10

#: Cap on how much of one payload is searched. An audit should not stall on
#: a 200 MB multipart upload; the limit is far above any realistic prompt.
MAX_PAYLOAD_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class Escape:
    """One canary observed in one outbound payload.

    `value` is repr-excluded, like `Canary.value`.
    """

    entity_type: str
    value: str = field(repr=False)
    form: str  # how it was found: raw | normalised | base64 | digit-run
    identity: int = 0


def _strip_separators(text: str) -> str:
    return text.translate({ord(ch): None for ch in _SEPARATORS})


def normalisations(value: str) -> set[str]:
    """Every form of `value` worth searching for, needle side."""
    forms = {value, value.casefold(), _strip_separators(value)}
    forms.add(_strip_separators(value).casefold())
    for form in tuple(forms):
        for scheme in ("NFC", "NFKC", "NFD", "NFKD"):
            forms.add(unicodedata.normalize(scheme, form))
    return {f for f in forms if f}


def _is_short_numeric(value: str) -> bool:
    """A digit-only value too short to be unambiguous on its own.

    A 6-digit PIN code is a substring of any longer digit run -- it occurs
    inside `1700500001999` by coincidence -- so these are matched only at a
    digit boundary. Without this, every digit-heavy payload manufactures a
    confirmed leak, and "confirmed" is the word this whole product rests on.
    """
    stripped = _strip_separators(value)
    return stripped.isdigit() and len(stripped) < MIN_DIGIT_RUN


def _bounded_in(needle: str, haystack: str) -> bool:
    """`needle` in `haystack`, but not glued to another digit."""
    for match in re.finditer(re.escape(needle), haystack):
        before = haystack[match.start() - 1] if match.start() else ""
        after = haystack[match.end()] if match.end() < len(haystack) else ""
        if not before.isdigit() and not after.isdigit():
            return True
    return False


def _haystacks(payload: str) -> dict[str, str]:
    """The payload in each form a needle might match against."""
    folded = payload.casefold()
    return {
        "raw": payload,
        "normalised": _strip_separators(folded),
        "nfkc": unicodedata.normalize("NFKC", folded),
    }


def _decoded_haystacks(payload: str) -> list[str]:
    """Base64 blobs inside the payload, decoded.

    Only runs of plausible base64 are tried, and a decode failure is
    ignored -- the goal is to catch a value hidden in an encoded body, not
    to parse the body.
    """
    out: list[str] = []
    for match in re.finditer(r"[A-Za-z0-9+/_-]{16,}={0,2}", payload):
        blob = match.group(0)
        for decoder in (base64.b64decode, base64.urlsafe_b64decode):
            try:
                padded = blob + "=" * (-len(blob) % 4)
                decoded = decoder(padded.encode("ascii"))
            except Exception:  # noqa: BLE001 -- any decode failure is a non-match
                continue
            try:
                out.append(decoded.decode("utf-8", errors="ignore"))
            except Exception:  # noqa: BLE001
                continue
    return out


def _digit_run_matches(digits: str, payload_digits: str) -> bool:
    """Do `digits` appear as a contiguous run in the payload's digits?

    `payload_digits` is the payload with every non-digit removed, so a
    value reassembled from fragments -- or merely reformatted -- is found.
    Gated on MIN_DIGIT_RUN rather than MIN_SEARCHABLE; see that constant.
    """
    return len(digits) >= MIN_DIGIT_RUN and digits in payload_digits


def find_escapes(
    payload: str,
    canaries: dict[str, tuple[str, int]],
) -> tuple[Escape, ...]:
    """Which canaries appear in this payload.

    `canaries` maps value -> (entity_type, identity). Returns one Escape
    per distinct value, recording the weakest form that matched (raw beats
    normalised beats base64 beats digit-run) so a report can say how
    direct the leak was.
    """
    if not payload or not canaries:
        return ()
    if len(payload) > MAX_PAYLOAD_BYTES:
        payload = payload[:MAX_PAYLOAD_BYTES]

    haystacks = _haystacks(payload)
    decoded = _decoded_haystacks(payload)
    payload_digits = re.sub(r"\D", "", payload)

    found: list[Escape] = []
    for value, (entity_type, identity) in canaries.items():
        if len(value) < MIN_SEARCHABLE:
            continue

        short_numeric = _is_short_numeric(value)

        def contains(needle: str, haystack: str, *, bounded: bool = short_numeric) -> bool:
            return _bounded_in(needle, haystack) if bounded else needle in haystack

        form = None
        if contains(value, haystacks["raw"]):
            form = "raw"
        else:
            needles = normalisations(value)
            if any(contains(n, hay) for n in needles for hay in haystacks.values()):
                form = "normalised"
            elif any(contains(n, blob) for n in needles for blob in decoded):
                form = "base64"
            else:
                digits = re.sub(r"\D", "", value)
                if len(digits) == len(_strip_separators(value)) and _digit_run_matches(
                    digits, payload_digits
                ):
                    # A digit-only identifier, found as an ordered run --
                    # this is the split-and-reassembled case.
                    form = "digit-run"

        if form is not None:
            found.append(Escape(entity_type=entity_type, value=value, form=form, identity=identity))

    return tuple(sorted(found, key=lambda e: (e.entity_type, e.identity)))
