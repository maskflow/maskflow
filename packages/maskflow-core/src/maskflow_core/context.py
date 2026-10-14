"""Keyword-proximity confidence adjustment.

Structural matches (email, credit card w/ Luhn, AWS keys, ...) are already
high-confidence on their own. Ambiguous matches (a bare 9-digit number, a
street-shaped line of text) need a nearby keyword to be trusted -- and a
nearby *negative* keyword ("this is just an example Aadhaar number: ...")
should push them the other way.

Two mechanisms, applied in this order per CLAUDE.md's confidence formula
(`+ context_boost - negative_context`):

* apply_context_boost() -- a nearby positive keyword raises confidence.
* apply_negative_context() -- a nearby negative keyword lowers it (floored
  at 0.0 so Span's [0, 1] invariant holds). Applied regardless of whether a
  checksum validator passed: the formula subtracts negative_context after
  the validator multiplier, and a checksum-valid *synthetic* identifier next
  to the word "example" is exactly the case this exists to suppress.

Both also consult the match's **column header** when the text is a table
(tables.py) and no keyword was found in the window: a header is matched
whole-word (`mobile_no` / `MobileNo` / `Mobile No.` all read as
"mobile no"), against the type's ordinary keywords plus its header-only
ones (HEADER_KEYWORDS / HEADER_NEGATIVE_KEYWORDS -- words like "mob" or
"test" that are too short to trust as free-text substrings but are
unambiguous as a whole column label). At most one boost and one penalty per
match, whichever source finds it first; a header matching a negative word
gives no boost at all (it only penalises). Explanations name the keyword, never
the header text: a misread "header" could be a data row.

Core ships no keywords of its own -- CONTEXT_KEYWORDS,
NEGATIVE_CONTEXT_KEYWORDS, HEADER_KEYWORDS and HEADER_NEGATIVE_KEYWORDS
start empty and are populated by whichever pack registers a type, via
registry.register_pattern() / register_custom_recognizer() /
register_ner_recognizer()'s keyword arguments.
"""

from functools import lru_cache

from .entities import ExplanationStep, PIIType
from .tables import find_tables

WINDOW = 40

CONTEXT_KEYWORDS: dict[PIIType, tuple[str, ...]] = {}
NEGATIVE_CONTEXT_KEYWORDS: dict[PIIType, tuple[str, ...]] = {}
HEADER_KEYWORDS: dict[PIIType, tuple[str, ...]] = {}
HEADER_NEGATIVE_KEYWORDS: dict[PIIType, tuple[str, ...]] = {}

BOOST = 0.4
PENALTY = 0.3
MAX_CONFIDENCE = 0.99


def _nearby(text: str, start: int, end: int) -> str:
    """The lowercased text within WINDOW chars on either side of [start, end),
    joined by a space so a keyword can't straddle the gap. Shared by both the
    positive and negative proximity checks."""
    window_start = max(0, start - WINDOW)
    window_end = min(len(text), end + WINDOW)
    return text[window_start:start].lower() + " " + text[end:window_end].lower()


_HEADER_SEPARATORS = str.maketrans({ch: " " for ch in "_-./:#()[]{}\r\t"})


@lru_cache(maxsize=4096)
def _words(label: str) -> tuple[str, ...]:
    """Case-folded words of a header cell or keyword: separators become
    spaces and an ASCII camelCase boundary splits ("MobileNo" -> mobile no).
    Only explicit separators split -- not str.isalnum -- because Devanagari
    vowel signs are combining marks and would otherwise break words apart."""
    spaced = []
    prev = ""
    for ch in label:
        if prev.isascii() and prev.islower() and ch.isascii() and ch.isupper():
            spaced.append(" ")
        spaced.append(ch)
        prev = ch
    return tuple("".join(spaced).translate(_HEADER_SEPARATORS).casefold().split())


def _header_keyword(
    text: str, start: int, end: int, keyword_sets: tuple[tuple[str, ...], ...]
) -> str | None:
    """The first keyword whose words appear contiguously in the column
    header above [start, end), or None (not a table cell / no match)."""
    if not any(keyword_sets):
        return None
    header = find_tables(text).header_for(start, end)
    if not header:
        return None
    return _match_header(header, keyword_sets)


@lru_cache(maxsize=4096)
def _match_header(header: str, keyword_sets: tuple[tuple[str, ...], ...]) -> str | None:
    """Memoised: a document has a handful of distinct headers but one
    lookup per match, and keyword lists run to dozens of entries."""
    header_words = _words(header)
    for keywords in keyword_sets:
        for keyword in keywords:
            kw = _words(keyword)
            if not kw or len(kw) > len(header_words):
                continue
            for i in range(len(header_words) - len(kw) + 1):
                if header_words[i : i + len(kw)] == kw:
                    return keyword
    return None


def apply_context_boost(
    text: str, start: int, end: int, pii_type: PIIType, base_confidence: float
) -> tuple[float, ExplanationStep]:
    keywords = CONTEXT_KEYWORDS.get(pii_type, ())
    header_only = HEADER_KEYWORDS.get(pii_type, ())
    if not keywords and not header_only:
        return base_confidence, ExplanationStep(rule="context", outcome="not_configured")

    nearby = _nearby(text, start, end)
    boosted = min(MAX_CONFIDENCE, base_confidence + BOOST)

    for keyword in keywords:
        if keyword in nearby:
            step = ExplanationStep(
                rule="context",
                outcome="boosted",
                delta=round(boosted - base_confidence, 2),
                detail=f'keyword "{keyword}" found within {WINDOW} chars',
            )
            return boosted, step

    header_keyword = _header_keyword(text, start, end, (keywords, header_only))
    # A header that also carries one of the type's negative words
    # (`mobile_app_build`, `account_id`, `product_name`) isn't about this
    # entity, so it gives no header boost. apply_negative_context() then applies the usual
    # penalty, so such a column always scores at or below an unlabelled one.
    if header_keyword is not None and not _header_keyword(
        text,
        start,
        end,
        (NEGATIVE_CONTEXT_KEYWORDS.get(pii_type, ()), HEADER_NEGATIVE_KEYWORDS.get(pii_type, ())),
    ):
        step = ExplanationStep(
            rule="context",
            outcome="boosted",
            delta=round(boosted - base_confidence, 2),
            detail=f'keyword "{header_keyword}" found in column header',
        )
        return boosted, step

    step = ExplanationStep(
        rule="context", outcome="no_match", detail=f"no context keyword found within {WINDOW} chars"
    )
    return base_confidence, step


def apply_negative_context(
    text: str, start: int, end: int, pii_type: PIIType, base_confidence: float
) -> tuple[float, ExplanationStep]:
    """Lower `base_confidence` by PENALTY (floored at 0.0) when a registered
    negative keyword for `pii_type` sits within WINDOW chars of the match --
    the suppression half of the confidence formula. Runs after
    apply_context_boost(), so "example aadhaar number 1234 ..." is boosted
    then suppressed, and both steps appear in the explanation trail."""
    keywords = NEGATIVE_CONTEXT_KEYWORDS.get(pii_type, ())
    header_only = HEADER_NEGATIVE_KEYWORDS.get(pii_type, ())
    if not keywords and not header_only:
        return base_confidence, ExplanationStep(rule="negative_context", outcome="not_configured")

    nearby = _nearby(text, start, end)
    reduced = max(0.0, base_confidence - PENALTY)

    for keyword in keywords:
        if keyword in nearby:
            step = ExplanationStep(
                rule="negative_context",
                outcome="suppressed",
                delta=round(reduced - base_confidence, 2),
                detail=f'keyword "{keyword}" found within {WINDOW} chars',
            )
            return reduced, step

    header_keyword = _header_keyword(text, start, end, (keywords, header_only))
    if header_keyword is not None:
        step = ExplanationStep(
            rule="negative_context",
            outcome="suppressed",
            delta=round(reduced - base_confidence, 2),
            detail=f'keyword "{header_keyword}" found in column header',
        )
        return reduced, step

    step = ExplanationStep(
        rule="negative_context",
        outcome="no_match",
        detail=f"no negative context keyword found within {WINDOW} chars",
    )
    return base_confidence, step
