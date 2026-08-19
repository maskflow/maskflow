from dataclasses import dataclass, field
from enum import Enum


class PIIType(str, Enum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    SSN = "SSN"
    CREDIT_CARD = "CREDIT_CARD"
    IP_ADDRESS = "IP_ADDRESS"
    AWS_KEY = "AWS_KEY"
    API_KEY = "API_KEY"
    JWT = "JWT"
    IBAN = "IBAN"
    ADDRESS = "ADDRESS"
    PERSON_NAME = "PERSON_NAME"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"


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
