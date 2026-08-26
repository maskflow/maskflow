"""Bundled 2-letter Indian state/UT vehicle-registration (RTO) codes -- the
first two characters of a DRIVING_LICENCE number or VEHICLE_REG plate (e.g.
"MH" in MH12AB1234). Curated, NOT exhaustive in the sense of covering every
historical/retired variant, but covers every state and union territory
current as of this file's last refresh. A value whose first two characters
aren't in this set is treated as structurally invalid by validate_driving_licence()
/ validate_vehicle_reg() (patterns.py) -- same "the code lookup IS the
structural check" design as IFSC's bank-code list (data/ifsc_bank_codes.py).

Refresh procedure: see docs/data-refresh.md.
  1. MoRTH (Ministry of Road Transport & Highways) publishes the current
     state/UT RTO code list via the Vahan/Sarathi portals
     (https://vahan.parivahan.gov.in, https://sarathi.parivahan.gov.in).
  2. Diff against INDIAN_STATE_RTO_CODES below, add any new UT/state code.
  3. Do not remove a retired code (e.g. a state renamed/split) -- historical
     documents referencing it may still appear in text.
  4. Update the "last refreshed" date in this docstring.

Last refreshed: 2026-08 (manually curated from public MoRTH/Vahan
documentation, not a direct portal export -- treat as a reasonable starting
set, not a guarantee of completeness).
"""

from __future__ import annotations

INDIAN_STATE_RTO_CODES: frozenset[str] = frozenset(
    {
        "AN",  # Andaman & Nicobar Islands
        "AP",  # Andhra Pradesh
        "AR",  # Arunachal Pradesh
        "AS",  # Assam
        "BR",  # Bihar
        "CH",  # Chandigarh
        "CG",  # Chhattisgarh
        "DD",  # Daman & Diu / Dadra & Nagar Haveli (legacy combined UT)
        "DL",  # Delhi
        "DN",  # Dadra & Nagar Haveli
        "GA",  # Goa
        "GJ",  # Gujarat
        "HP",  # Himachal Pradesh
        "HR",  # Haryana
        "JH",  # Jharkhand
        "JK",  # Jammu & Kashmir
        "KA",  # Karnataka
        "KL",  # Kerala
        "LA",  # Ladakh
        "LD",  # Lakshadweep
        "MH",  # Maharashtra
        "ML",  # Meghalaya
        "MN",  # Manipur
        "MP",  # Madhya Pradesh
        "MZ",  # Mizoram
        "NL",  # Nagaland
        "OD",  # Odisha (current code)
        "OR",  # Odisha (legacy code, still in circulation)
        "PB",  # Punjab
        "PY",  # Puducherry
        "RJ",  # Rajasthan
        "SK",  # Sikkim
        "TN",  # Tamil Nadu
        "TR",  # Tripura
        "TS",  # Telangana
        "UK",  # Uttarakhand (current code)
        "UA",  # Uttarakhand (legacy code, still in circulation)
        "UP",  # Uttar Pradesh
        "WB",  # West Bengal
    }
)
