"""Synthetic international-PII document generator for bench/intlpii
(intl-pii-v1.0).

Every value this package produces is either checksum-VALID but never issued
to a real holder (CREDIT_CARD via Luhn, IBAN via mod-97, SSN via a real but
unassigned area range), or structurally valid to its published format with
no real-world backing (EMAIL, PHONE in the NANP 555-01xx fiction range,
AWS_KEY, API_KEY, JWT, IP_ADDRESS, ADDRESS, PERSON_NAME, DATE_OF_BIRTH).
None of these belong to a real person, account, or credential -- see
bench/intlpii/data/intl-pii-v1.0.README.md for the full disclaimer.

Realism noise (typos, casing wobble -- see realism.py) is applied ONLY to
surrounding template prose and field labels, never to a checksum-bearing
value's own characters: corrupting those would silently break the validity
guarantee this corpus exists to make true. generate.py's self-check
re-validates every generated value against maskflow-pack-intl's OWN
validate_*()/luhn_is_valid()/iban_is_valid() functions rather than
asserting it.

Mirrors bench/indiapii/generator/ in structure and discipline; the intl
pack (maskflow_pack_intl) is the moat's counterpart here -- generic PII we
do not compete on, but still publish a measured number for.
"""
