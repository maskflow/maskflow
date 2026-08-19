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
class Finding:
    type: PIIType
    # repr=False: raw PII must never surface via default dataclass repr --
    # logger.debug(finding), an unhandled traceback, or a debugger repr() call
    # would otherwise print it verbatim.
    value: str = field(repr=False)
    start: int
    end: int
    confidence: float
    # True only when a structural validator ran and confirmed the match
    # (checksum-valid Luhn card, mod-97 IBAN, ...). Used to give validated
    # spans priority over unvalidated ones during overlap resolution.
    validated: bool = False

    @property
    def span(self) -> tuple[int, int]:
        return (self.start, self.end)
