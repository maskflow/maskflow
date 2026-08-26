"""Aho-Corasick gazetteer matching for PERSON_NAME (Indian) and
INDIAN_ADDRESS L1 (the work order's "L1 Gazetteer" layer). Wrapped by a
maskflow_core.recognizer.GazetteerRecognizer in __init__.py -- see that
module's docstring for how a custom match function's raw hits (start, end,
matched_text, base_confidence) feed into the same validator/context-boost/
Span pipeline every other recognizer uses.

Both automatons are built lazily and cached (@lru_cache(maxsize=1)), the
same way maskflow_core.ner._get_nlp() lazily loads spaCy -- importing this
module, or `maskflow_pack_india` as a whole, never pays the ~115k-entry
automaton-build cost; only the first detect() call does.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

import ahocorasick

from .data.indian_names import EXCLUDED_NAMES, TIER_RARE, load_indian_names
from .data.indian_places import INDIAN_PLACE_NAMES
from .patterns import INDIAN_PIN_CODE_SHAPE_RE

# L2 "STRONG mutual PIN_CODE reinforcement": a place hit with a PIN-shaped
# 6-digit run within this many chars is far more likely to be part of a
# real address than a bare place mention -- pushes INDIAN_ADDRESS_L1_BASE
# (0.3) up to comfortably clear DEFAULT_MIN_CONFIDENCE without needing a
# separate keyword nearby. Mirrors context.WINDOW's spirit but implemented
# locally (patterns.py has no notion of "nearby another pattern's match").
_PIN_REINFORCEMENT_WINDOW = 20
INDIAN_ADDRESS_L1_BASE = 0.3
INDIAN_ADDRESS_PIN_REINFORCED = 0.65

# ---------------------------------------------------------------------------
# Confidence -- frequency-aware per CLAUDE.md's work order: a COMMON name
# (also a common English/Hinglish word, or simply too generic to be
# distinctive on its own -- "Kumar", "Devi") needs a nearby context cue to
# clear DEFAULT_MIN_CONFIDENCE (0.5); a RARE, more distinctive name can fire
# standalone. Same shape as PIN_CODE/AADHAAR_MASKED's context-gated design
# in patterns.py.
# ---------------------------------------------------------------------------
TIER_COMMON_BASE = 0.35
TIER_RARE_BASE = 0.6

# Two gazetteer hits immediately adjacent (single space -- a given name
# directly followed by a surname, e.g. "Rohit Sharma") are far stronger
# joint evidence than either alone, so contiguous same-kind-family hits are
# coalesced into one span with a bonus rather than left as two separate
# PERSON_NAME candidates that the STRICT overlap policy would otherwise both
# accept as adjacent-but-unmerged spans.
MULTI_TOKEN_BONUS = 0.25
MAX_MATCH_CONFIDENCE = 0.95

_RawHit = tuple[int, int, str]  # (start, end, tier)


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _boundary_ok(text: str, start: int, end: int) -> bool:
    if start > 0 and _is_word_char(text[start - 1]):
        return False
    if end < len(text) and _is_word_char(text[end]):
        return False
    return True


def _is_capitalized(text: str, start: int) -> bool:
    # L1 precision gate: a lowercase "priya" mid-sentence doesn't fire --
    # L2 (structural evidence) / L3 (NLP agreement) can relax this once
    # there's other evidence to lean on.
    return text[start : start + 1].isupper()


# ---------------------------------------------------------------------------
# Programmatic spelling variants -- a small, documented, DETERMINISTIC rule
# table (not sourced) that expands each canonical gazetteer entry into its
# common romanization alternates, e.g. Krishna -> Krishnaa, Lakshmi -> Laxmi.
# Each rule fires at most once per name (first match only), independently of
# the others -- not combined/chained, to keep the expansion set small,
# predictable, and reviewable rather than combinatorial.
# ---------------------------------------------------------------------------
_SUFFIX_VARIANT_RULES: tuple[tuple[str, str], ...] = (
    ("na", "naa"),  # Krishna -> Krishnaa
    ("ma", "maa"),  # Uma -> Umaa
    ("ta", "taa"),  # Sita -> Sitaa
)
_SUBSTRING_VARIANT_RULES: tuple[tuple[str, str], ...] = (
    ("ksh", "x"),  # Lakshmi -> Laxmi
    ("ee", "i"),  # Sanjeev -> Sanjiv
    # No blanket "v"->"w" rule: tried it, dropped it -- it turns short noisy
    # pool fragments (see indian_names.py's provenance caveat) into common
    # English words, e.g. "vi"/"vish" -> "wi"/"wish", which is worse than
    # the coverage it was meant to add.
)


def generate_spelling_variants(name: str) -> set[str]:
    variants: set[str] = set()
    lowered = name.lower()

    for suffix, replacement in _SUFFIX_VARIANT_RULES:
        if lowered.endswith(suffix):
            variants.add(lowered[: -len(suffix)] + replacement)

    for old, new in _SUBSTRING_VARIANT_RULES:
        idx = lowered.find(old)
        if idx != -1:
            variants.add(lowered[:idx] + new + lowered[idx + len(old) :])

    variants.discard(lowered)
    return variants


def _expand_with_variants(entries: dict[str, str]) -> Iterator[tuple[str, str]]:
    for name, tier in entries.items():
        lowered = name.lower()
        yield lowered, tier
        for variant in generate_spelling_variants(lowered):
            # A generated variant never overrides a real dataset entry's own
            # (possibly different) tier -- only fills gaps. Also never
            # re-introduces a name EXCLUDED_NAMES deliberately dropped (e.g.
            # "shree" -[ee->i]-> "shri", which would otherwise put this
            # pack's own honorific vocabulary right back in the automaton).
            if variant not in entries and variant not in EXCLUDED_NAMES:
                yield variant, tier


@lru_cache(maxsize=1)
def _person_name_automaton() -> ahocorasick.Automaton:
    automaton = ahocorasick.Automaton()
    for name, tier in _expand_with_variants(load_indian_names()):
        # pyahocorasick's iter() only ever hands back the stored VALUE, not
        # the key that was add_word()'d -- store the key alongside the tier
        # so match_person_names can recover the match's length/start from it.
        if name not in automaton:
            automaton.add_word(name, (name, tier))
    automaton.make_automaton()
    return automaton


@lru_cache(maxsize=1)
def _place_automaton() -> ahocorasick.Automaton:
    automaton = ahocorasick.Automaton()
    for place in INDIAN_PLACE_NAMES:
        automaton.add_word(place.lower(), place.lower())
    automaton.make_automaton()
    return automaton


def match_person_names(text: str) -> Iterator[tuple[int, int, str, float]]:
    """PIIType.PERSON_NAME candidates: contiguous runs of capitalized,
    word-boundary-safe gazetteer hits, coalesced into one span per run.
    """
    automaton = _person_name_automaton()
    lowered = text.lower()

    raw: list[_RawHit] = []
    for end_index, (matched_word, tier) in automaton.iter(lowered):
        start = end_index - len(matched_word) + 1
        end = end_index + 1
        if not _boundary_ok(text, start, end):
            continue
        if not _is_capitalized(text, start):
            continue
        raw.append((start, end, tier))

    raw.sort()
    yield from _coalesce_hits(text, raw)


def _coalesce_hits(text: str, raw: list[_RawHit]) -> Iterator[tuple[int, int, str, float]]:
    i = 0
    n = len(raw)
    while i < n:
        start, end, tier = raw[i]
        tiers = [tier]
        j = i + 1
        # Coalesce only a genuinely adjacent next hit: exactly one char
        # between them, and that char is a plain space (e.g. a given name
        # directly followed by a surname).
        while j < n and raw[j][0] == end + 1 and text[end] == " ":
            end = raw[j][1]
            tiers.append(raw[j][2])
            j += 1

        base = TIER_RARE_BASE if TIER_RARE in tiers else TIER_COMMON_BASE
        if len(tiers) > 1:
            base = min(MAX_MATCH_CONFIDENCE, base + MULTI_TOKEN_BONUS)

        yield start, end, text[start:end], base
        i = j


def match_indian_places(text: str) -> Iterator[tuple[int, int, str, float]]:
    """PIIType.INDIAN_ADDRESS candidates from the state/UT + top-500-city
    gazetteer alone -- deliberately low base confidence (mirrors PIN_CODE's
    0.3): a bare place mention isn't an address by itself. L2's structural
    markers (unit numbers, landmark-relative phrases, locality words) and
    PIN_CODE proximity are what carry this type to usable recall.
    """
    automaton = _place_automaton()
    lowered = text.lower()

    for end_index, place in automaton.iter(lowered):
        start = end_index - len(place) + 1
        end = end_index + 1
        if not _boundary_ok(text, start, end):
            continue
        if not _is_capitalized(text, start):
            continue

        window_start = max(0, start - _PIN_REINFORCEMENT_WINDOW)
        window_end = min(len(text), end + _PIN_REINFORCEMENT_WINDOW)
        nearby = text[window_start:start] + text[end:window_end]
        base = (
            INDIAN_ADDRESS_PIN_REINFORCED
            if INDIAN_PIN_CODE_SHAPE_RE.search(nearby)
            else INDIAN_ADDRESS_L1_BASE
        )
        yield start, end, text[start:end], base
