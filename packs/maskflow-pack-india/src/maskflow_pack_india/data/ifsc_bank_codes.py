"""Bundled RBI-assigned 4-letter bank codes -- the first 4 characters of an
IFSC (e.g. "HDFC" in HDFC0001234). Curated, NOT exhaustive: it covers major
scheduled commercial banks, small finance banks, and payments banks
operating in India as of this file's last refresh. An IFSC whose bank code
isn't in this set is treated as structurally invalid by validate_ifsc()
(patterns.py) -- a false negative on an obscure/regional bank is preferred
over inventing a checksum-like check IFSC doesn't actually have (there is no
public per-character checksum on an IFSC; the bank-code lookup IS the
structural check).

Refresh procedure:
  1. RBI publishes the authoritative IFSC master list (bank-wise, all
     branches) at https://www.rbi.org.in -- search "IFSC master list" for
     the current CSV/XLSX download.
  2. Extract the unique set of 4-character bank-code prefixes (characters
     0-3 of each IFSC in the list; character 4 is always '0').
  3. Diff against IFSC_BANK_CODES below, add any new entries (bank mergers
     retire old codes but never reuse them for a different bank -- safe to
     leave retired codes in this set indefinitely).
  4. Update the "last refreshed" date in this docstring.

Last refreshed: 2026-08 (manually curated from public bank-merger and PSP
records, not a direct RBI CSV import -- treat as a reasonable starting set,
not a guarantee of completeness).
"""

from __future__ import annotations

IFSC_BANK_CODES: frozenset[str] = frozenset(
    {
        # Public sector banks
        "SBIN",  # State Bank of India
        "PUNB",  # Punjab National Bank
        "BKID",  # Bank of India
        "CNRB",  # Canara Bank
        "UBIN",  # Union Bank of India
        "IOBA",  # Indian Overseas Bank
        "IDIB",  # Indian Bank
        "CBIN",  # Central Bank of India
        "MAHB",  # Bank of Maharashtra
        "UCBA",  # UCO Bank
        "PSIB",  # Punjab & Sind Bank
        "BARB",  # Bank of Baroda
        # Merged/retired public sector codes (still valid on old branches --
        # never reused for a different bank, see refresh procedure above)
        "ORBC",  # Oriental Bank of Commerce (merged into PNB)
        "ANDB",  # Andhra Bank (merged into Union Bank)
        "CORP",  # Corporation Bank (merged into Union Bank)
        "ALLA",  # Allahabad Bank (merged into Indian Bank)
        "SYNB",  # Syndicate Bank (merged into Canara Bank)
        "VIJB",  # Vijaya Bank (merged into Bank of Baroda)
        # Major private sector banks
        "HDFC",  # HDFC Bank
        "ICIC",  # ICICI Bank
        "UTIB",  # Axis Bank
        "KKBK",  # Kotak Mahindra Bank
        "YESB",  # Yes Bank
        "INDB",  # IndusInd Bank
        "IDFB",  # IDFC FIRST Bank
        "RATN",  # RBL Bank
        "FDRL",  # Federal Bank
        "SIBL",  # South Indian Bank
        "KVBL",  # Karur Vysya Bank
        "TMBL",  # Tamilnad Mercantile Bank
        "DCBB",  # DCB Bank
        "CSBK",  # CSB Bank
        "KARB",  # Karnataka Bank
        "DBSS",  # DBS Bank India (incl. merged Lakshmi Vilas Bank branches)
        "BDBL",  # Bandhan Bank
        "JAKA",  # Jammu & Kashmir Bank
        "NKGS",  # NKGSB Co-operative Bank
        "SVCB",  # Shamrao Vithal Co-operative Bank
        # Foreign banks operating in India
        "CITI",  # Citibank
        "HSBC",  # HSBC
        "SCBL",  # Standard Chartered Bank
        "DEUT",  # Deutsche Bank
        "BOFA",  # Bank of America
        # Small finance banks
        "AUBL",  # AU Small Finance Bank
        "EQBL",  # Equitas Small Finance Bank
        "UJVN",  # Ujjivan Small Finance Bank
        "ESFB",  # ESAF Small Finance Bank
        "SURY",  # Suryoday Small Finance Bank
        "UTKS",  # Utkarsh Small Finance Bank
        "JSFB",  # Jana Small Finance Bank
        # Payments banks
        "PYTM",  # Paytm Payments Bank
        "AIRP",  # Airtel Payments Bank
        "FINO",  # Fino Payments Bank
        "NSPB",  # NSDL Payments Bank
        "IPOS",  # India Post Payments Bank
        "JIOP",  # Jio Payments Bank
    }
)
