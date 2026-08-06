"""Labeled PII examples used to measure detection accuracy.

POSITIVE_SAMPLES: each sample's `expected` findings must all be present in
detect()'s output (a recall check -- extra correct detections elsewhere in
the same sentence are fine).

NEGATIVE_SAMPLES: plain sentences (or PII-shaped text that fails structural
validation, e.g. a bad Luhn checksum) that must produce *zero* findings --
a precision check against false positives.
"""
from dataclasses import dataclass

from maskflow_core.entities import PIIType


@dataclass
class Sample:
    text: str
    expected: list[tuple[PIIType, str]]


def _samples(pii_type: PIIType, template: str, values: list[str]) -> list[Sample]:
    return [Sample(template.format(value=v), [(pii_type, v)]) for v in values]


EMAILS = [
    "alice@example.com",
    "bob.smith@company.co.uk",
    "jane_doe123@sub.domain.org",
    "test.user+tag@gmail.com",
    "contact@my-startup.io",
    "first.last@corp-mail.net",
    "support@helpdesk.com",
    "dev.ops@cloud-provider.io",
    "maria.garcia@university.edu",
    "info@nonprofit.org",
]

PHONES = [
    "(415) 555-0132",
    "415-555-0147",
    "415.555.0198",
    "+1 415 555 0173",
    "1-800-555-0199",
    "(212) 867-5309",
    "650-555-0111",
    "212.555.0180",
    "310-555-0166",
    "303-555-0184",
]

SSN_DASHED = [
    "245-11-2222",
    "312-45-6789",
    "560-22-3344",
    "134-56-7890",
    "478-90-1234",
    "601-23-4567",
]

# Bare 9-digit SSNs are ambiguous -- only detected when a keyword like "ssn"
# appears nearby, so these templates embed the number with that context inline.
SSN_PLAIN_SAMPLES = [
    Sample("My SSN is 234567890 for verification.", [(PIIType.SSN, "234567890")]),
    Sample(
        "Please confirm your social security number 345678901 on file.",
        [(PIIType.SSN, "345678901")],
    ),
    Sample("SSN: 456789012 was provided by the applicant.", [(PIIType.SSN, "456789012")]),
    Sample(
        "The applicant's ssn 567890123 matches our records.",
        [(PIIType.SSN, "567890123")],
    ),
]

# Well-known payment-gateway test card numbers (Luhn-valid, not real customer data).
CREDIT_CARDS_VALID = [
    "4111111111111111",
    "5555555555554444",
    "378282246310005",
    "6011000000000004",
    "3566002020360505",
    "30569309025904",
    "5105105105105100",
    "4012888888881881",
]

IPV4_ADDRESSES = [
    "192.168.1.1",
    "10.0.0.254",
    "8.8.8.8",
    "172.16.254.1",
    "203.0.113.42",
    "198.51.100.23",
]

IPV6_ADDRESSES = [
    "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
    "fe80:0000:0000:0000:0202:b3ff:fe1e:8329",
]

AWS_KEYS = [
    "AKIAIOSFODNN7EXAMPLE",
    "AKIAJEXAMPLE12345678",
    "ASIAQWERTYUIOPASDFGH",
    "AKIAZXCVBNMLKJHGFDSA",
    "AKIA1234567890ABCDEF",
]

API_KEYS_PREFIXED = [
    "sk-ant-api03-abcdefghijklmnopqrstuvwxYZ0123456789",
    "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcd",
    "ghp_1234567890abcdefghijklmnopqrstuvwxyz",
    "xoxb-1234567890-abcdefghijklmnopqrstuvwx",
    "AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz0123456",
]

API_KEY_ASSIGNMENT_SAMPLES = [
    Sample(
        "Please rotate secret_token=zX9pQ7mK2vN4wL8rT1yB immediately.",
        [(PIIType.API_KEY, "zX9pQ7mK2vN4wL8rT1yB")],
    ),
    Sample(
        "Set api_key=aB3dE5fG7hJ9kL1mN3pQ in the .env file.",
        [(PIIType.API_KEY, "aB3dE5fG7hJ9kL1mN3pQ")],
    ),
    Sample(
        "password: Tr0ub4dor3xtraLongPass99",
        [(PIIType.API_KEY, "Tr0ub4dor3xtraLongPass99")],
    ),
]

JWTS = [
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    "eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyIjoiYWRtaW4ifQ.4f8h2kd9s0aLpQ7zR3xTvY1bN6mWc5eUj",
    "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJ1c2VyMTIzIn0.abcdefGHIJKL1234567890_-mnopqr",
    "eyJhbGciOiJSUzI1NiJ9.eyJyb2xlIjoiYWRtaW4ifQ.QWxhZGRpbjpvcGVuIHNlc2FtZQ_ZZZ",
]

IBANS = [
    "GB29NWBK60161331926819",
    "DE89370400440532013000",
    "FR1420041010050500013M02606",
    "NL91ABNA0417164300",
    "BE68539007547034",
]

ADDRESSES = [
    "123 Main Street",
    "456 Oak Avenue, Apt 2B",
    "789 Elm Road",
    "1600 Pennsylvania Avenue",
    "42 Baker Street",
    "10 Downing Street",
    "350 Fifth Avenue, Suite 100",
    "77 Massachusetts Avenue",
]

PERSON_NAME_SAMPLES = [
    Sample("John Smith called yesterday afternoon.", [(PIIType.PERSON_NAME, "John Smith")]),
    Sample("My name is Sarah Johnson.", [(PIIType.PERSON_NAME, "Sarah Johnson")]),
    Sample(
        "Please contact Michael Chen regarding the invoice.",
        [(PIIType.PERSON_NAME, "Michael Chen")],
    ),
    Sample("Emily Davis will attend the conference.", [(PIIType.PERSON_NAME, "Emily Davis")]),
    Sample("The report was signed by Robert Wilson.", [(PIIType.PERSON_NAME, "Robert Wilson")]),
    Sample(
        "Laura Martinez submitted her application today.",
        [(PIIType.PERSON_NAME, "Laura Martinez")],
    ),
    Sample("David Thompson is the project lead.", [(PIIType.PERSON_NAME, "David Thompson")]),
    Sample("Please forward this to Jennifer Lee.", [(PIIType.PERSON_NAME, "Jennifer Lee")]),
]

DATE_OF_BIRTH_SAMPLES = [
    Sample("Her date of birth is March 3, 1990.", [(PIIType.DATE_OF_BIRTH, "March 3, 1990")]),
    Sample("Date of birth: July 4, 1990.", [(PIIType.DATE_OF_BIRTH, "July 4, 1990")]),
    Sample("He was born on June 12, 1979.", [(PIIType.DATE_OF_BIRTH, "June 12, 1979")]),
    Sample("DOB: December 25, 1985.", [(PIIType.DATE_OF_BIRTH, "December 25, 1985")]),
    Sample(
        "The patient's date of birth is January 9, 2001.",
        [(PIIType.DATE_OF_BIRTH, "January 9, 2001")],
    ),
    Sample("Birthdate: February 14, 1995.", [(PIIType.DATE_OF_BIRTH, "February 14, 1995")]),
]

MULTI_ENTITY_SAMPLES = [
    Sample(
        "Hi, this is Jane Doe. My email is jane.doe@example.com and my phone is "
        "415-555-0198. My SSN is 245-11-2222 for the background check.",
        [
            (PIIType.PERSON_NAME, "Jane Doe"),
            (PIIType.EMAIL, "jane.doe@example.com"),
            (PIIType.PHONE, "415-555-0198"),
            (PIIType.SSN, "245-11-2222"),
        ],
    ),
    Sample(
        "Contact: Mark Rivera, mark.rivera@company.com, (312) 555-0142. "
        "He lives at 789 Elm Road.",
        [
            (PIIType.PERSON_NAME, "Mark Rivera"),
            (PIIType.EMAIL, "mark.rivera@company.com"),
            (PIIType.PHONE, "(312) 555-0142"),
            (PIIType.ADDRESS, "789 Elm Road"),
        ],
    ),
    Sample(
        "AWS incident: key AKIAIOSFODNN7EXAMPLE was exposed in a commit by Alice "
        "Nguyen. Her email alice.nguyen@dev.io was notified.",
        [
            (PIIType.AWS_KEY, "AKIAIOSFODNN7EXAMPLE"),
            (PIIType.PERSON_NAME, "Alice Nguyen"),
            (PIIType.EMAIL, "alice.nguyen@dev.io"),
        ],
    ),
    Sample(
        "Customer card 4111111111111111 was charged; confirmation sent to "
        "billing@shop.com and 650-555-0177.",
        [
            (PIIType.CREDIT_CARD, "4111111111111111"),
            (PIIType.EMAIL, "billing@shop.com"),
            (PIIType.PHONE, "650-555-0177"),
        ],
    ),
    Sample(
        "Server 10.0.0.254 issued token "
        "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcd for user Chris Park "
        "at chris.park@ops.com.",
        [
            (PIIType.IP_ADDRESS, "10.0.0.254"),
            (PIIType.API_KEY, "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcd"),
            (PIIType.PERSON_NAME, "Chris Park"),
            (PIIType.EMAIL, "chris.park@ops.com"),
        ],
    ),
]

NEGATIVE_SAMPLES = [
    "Order number 123456789 was shipped today.",
    "Reference code: 4111111111111112 does not match our records.",
    "Invoice total due: 378282246310006 dollars.",
    "Please review the quarterly report before Friday.",
    "The stock price rose by 4.5 percent today.",
    "Meeting is scheduled for next Tuesday at the main office.",
    "Our server uptime this month was 99.98 percent.",
    "The temperature reached 72 degrees this afternoon.",
]

POSITIVE_SAMPLES: list[Sample] = (
    _samples(PIIType.EMAIL, "You can reach me at {value} anytime.", EMAILS)
    + _samples(PIIType.PHONE, "Call me at {value} when you're free.", PHONES)
    + _samples(PIIType.SSN, "Employee SSN on file: {value}.", SSN_DASHED)
    + SSN_PLAIN_SAMPLES
    + _samples(PIIType.CREDIT_CARD, "Charge the card ending in this number: {value}.", CREDIT_CARDS_VALID)
    + _samples(PIIType.IP_ADDRESS, "The request originated from {value}.", IPV4_ADDRESSES)
    + _samples(PIIType.IP_ADDRESS, "The request originated from {value}.", IPV6_ADDRESSES)
    + _samples(PIIType.AWS_KEY, "Found exposed key {value} in the logs.", AWS_KEYS)
    + _samples(PIIType.API_KEY, "The integration uses {value} as its token.", API_KEYS_PREFIXED)
    + API_KEY_ASSIGNMENT_SAMPLES
    + _samples(PIIType.JWT, "Authorization header: Bearer {value}", JWTS)
    + _samples(PIIType.IBAN, "Please wire the funds to {value}.", IBANS)
    + _samples(PIIType.ADDRESS, "I live at {value}.", ADDRESSES)
    + PERSON_NAME_SAMPLES
    + DATE_OF_BIRTH_SAMPLES
    + MULTI_ENTITY_SAMPLES
)
