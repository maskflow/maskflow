from dataclasses import dataclass, field
from typing import ClassVar


class PIIType(str):
    """Open registry of PII type identifiers, each just a validated UPPER_SNAKE
    string. Core registers none of its own -- every type (PIIType.EMAIL,
    PIIType.AADHAAR, ...) is registered by whichever pack owns that recognizer,
    via PIIType.register("AADHAAR"), typically through registry.register_pattern()
    or registry.register_ner_recognizer() rather than calling this directly.
    """

    _registered: ClassVar[dict[str, "PIIType"]] = {}

    def __new__(cls, name: str) -> "PIIType":
        if name not in cls._registered:
            raise ValueError(f"Unregistered PII type: {name!r}. Use PIIType.register() first.")
        return cls._registered[name]

    @property
    def value(self) -> str:
        return str(self)

    @classmethod
    def register(cls, name: str) -> "PIIType":
        if name in cls._registered:
            return cls._registered[name]
        if not name.isidentifier() or name != name.upper():
            raise ValueError(f"PII type name must be an UPPER_SNAKE identifier: {name!r}")
        instance = str.__new__(cls, name)
        cls._registered[name] = instance
        setattr(cls, name, instance)
        return instance

    @classmethod
    def values(cls) -> tuple["PIIType", ...]:
        return tuple(cls._registered.values())


@dataclass(frozen=True)
class ExplanationStep:
    """One step in a Span's decision trail -- structured (not a free-text
    string) so it can be rendered as text, serialized as JSON, or asserted
    on in tests by field rather than substring match. `detail` is a short,
    human-readable note (a static context keyword, an offset, a threshold
    value) -- never the matched PII text itself (CLAUDE.md rule 1)."""

    rule: str
    outcome: str
    delta: float = 0.0
    detail: str = ""


@dataclass(frozen=True)
class Span:
    """One candidate (or resolved) PII detection. Every recognizer -- regex or
    NER -- emits these; SpanSet.resolve() (see spanset.py) is the single place
    that turns a pile of overlapping candidate Spans into the final
    non-overlapping list used for masking.
    """

    start: int
    end: int
    entity_type: PIIType
    score: float
    # Which recognizer produced this span, e.g. "pattern:AADHAAR", "ner:PERSON",
    # or "merged(...)" for a span produced by the MERGE overlap policy. Purely
    # diagnostic -- never parsed, only useful in explanation trails/debugging.
    recognizer: str
    # repr=False: raw PII must never surface via default dataclass repr --
    # logger.debug(span), an unhandled traceback, or a debugger repr() call
    # would otherwise print it verbatim.
    text: str = field(repr=False)
    # True only when a structural validator ran and confirmed the match
    # (checksum-valid Luhn card, mod-97 IBAN, ...). Used to give validated
    # spans priority over unvalidated ones during overlap resolution.
    validated: bool = False
    # Structured trail of decisions that touched this span (pattern hit,
    # checksum result, context boost, beat/lost to an overlapping span,
    # merged with a neighbor, threshold cut, ...). Mutable list on a frozen
    # dataclass is intentional -- frozen only blocks attribute *assignment*,
    # and appending to this list in place is how resolution code annotates a
    # span without needing dataclasses.replace() everywhere.
    explanation: list[ExplanationStep] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.start < self.end:
            raise ValueError(f"Span start must be < end (got start={self.start}, end={self.end})")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"Span score must be within [0, 1] (got {self.score})")

    @property
    def span(self) -> tuple[int, int]:
        return (self.start, self.end)
