from dataclasses import dataclass
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
    value: str
    start: int
    end: int
    confidence: float

    @property
    def span(self) -> tuple[int, int]:
        return (self.start, self.end)
