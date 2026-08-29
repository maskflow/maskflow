"""Synthetic India-PII document generator for bench/indiapii (indiapii-v1.0).

Every identifier value this package produces is either checksum-VALID but
UNASSIGNED (AADHAAR, GSTIN), or structurally valid to its published format
with no real-world registry backing it (PAN, IFSC, UPI VPA, ...). None of
these belong to a real person, business, or account -- see
bench/indiapii/data/indiapii-v1.0.README.md for the full disclaimer.

Realism noise (OCR confusions, typos, Hinglish code-mixing, WhatsApp
abbreviations -- see realism.py) is applied ONLY to surrounding template
prose and field labels, never to a checksum-bearing identifier's own
characters: corrupting those digits would silently break the
"checksum-VALID" guarantee this corpus exists to make true. See
generate.py's module docstring for the self-check that verifies this
guarantee end-to-end rather than asserting it.
"""
