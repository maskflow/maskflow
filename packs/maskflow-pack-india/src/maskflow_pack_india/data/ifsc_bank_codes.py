"""Bundled RBI-assigned 4-letter bank codes -- the first 4 characters of an
IFSC (e.g. "HDFC" in HDFC0001234). Curated, NOT exhaustive: it covers major
scheduled commercial banks, small finance banks, and payments banks
operating in India as of this file's last refresh. An IFSC whose bank code
isn't in this set is treated as structurally invalid by validate_ifsc()
(patterns.py) -- a false negative on an obscure/regional bank is preferred
over inventing a checksum-like check IFSC doesn't actually have (there is no
public per-character checksum on an IFSC; the bank-code lookup IS the
structural check).

Refresh procedure: see docs/data-refresh.md, or run
`uv run python scripts/refresh_india_reference_data.py ifsc` (from the repo
root), which diffs this set against razorpay/ifsc's public-domain,
RBI-cross-checked bank-code data and prints candidates for review -- it never
writes this file itself. Bank mergers retire old codes but never reuse them
for a different bank, so retired codes are kept in this set indefinitely.

Last refreshed: 2026-08-27 via the script above. Added 38 codes the prior
manual curation missed (21 foreign banks, 5 private banks, 6 small finance
banks, 2 local area banks, India Post Payments Bank, and 3 legitimate
merged/retired PSU codes -- Dena Bank, Reserve Bank of India, United Bank of
India). DCBB, EQBL, IPOS, and UJVN (already bundled) don't appear in this
source at all -- kept as-is rather than guessed-and-removed, but worth a
closer look next refresh (DCBL/USFB/IPPB, added below, look like they may be
the same banks under current codes).
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
        "BKDN",  # Dena Bank (merged into Bank of Baroda)
        "UTBI",  # United Bank of India (merged into PNB)
        "RBIN",  # Reserve Bank of India
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
        "CIUB",  # City Union Bank
        "DCBL",  # DCB Bank (see refresh note above re: DCBB)
        "DLXB",  # Dhanlaxmi Bank
        "IBKL",  # IDBI Bank
        "NTBL",  # Nainital Bank
        # Foreign banks operating in India
        "CITI",  # Citibank
        "HSBC",  # HSBC
        "SCBL",  # Standard Chartered Bank
        "DEUT",  # Deutsche Bank
        "BOFA",  # Bank of America
        "ABBL",  # AB Bank
        "BARC",  # Barclays Bank
        "BBKM",  # Bank of Bahrein and Kuwait
        "BCEY",  # Bank of Ceylon
        "BNPA",  # BNP Paribas
        "BOTM",  # MUFG Bank
        "CHAS",  # JP Morgan Chase Bank N.A.
        "CRLY",  # Credit Agricole Corporate and Investment Bank
        "EBIL",  # Emirates NBD Bank
        "KBHB",  # KEB Hana Bank
        "LAVB",  # Laxmi Vilas Bank (merged into DBS Bank India, see DBSS above)
        "MHCB",  # Mizuho Bank
        "NOSC",  # Bank of Nova Scotia
        "OIBA",  # HSBC Bank Oman S.A.O.G
        "QNBX",  # Qatar National Bank
        "RABO",  # Rabobank International
        "SBLD",  # Sonali Bank
        "SHBK",  # Shinhan Bank
        "SMBC",  # Sumitomo Mitsui Banking Corporation
        "SOGE",  # Societe Generale
        "STCB",  # SBM Bank
        # Small finance banks
        "AUBL",  # AU Small Finance Bank
        "EQBL",  # Equitas Small Finance Bank
        "UJVN",  # Ujjivan Small Finance Bank
        "USFB",  # Ujjivan Small Finance Bank (current code, see refresh note above)
        "ESFB",  # Equitas Small Finance Bank (relabeled 2026-08-27, was mislabeled ESAF)
        "ESAF",  # ESAF Small Finance Bank
        "SURY",  # Suryoday Small Finance Bank
        "UTKS",  # Utkarsh Small Finance Bank
        "JSFB",  # Jana Small Finance Bank
        "CLBL",  # Capital Small Finance Bank
        "FINF",  # Fincare Small Finance Bank
        "NESF",  # North East Small Finance Bank
        "SHIX",  # Shivalik Small Finance Bank
        # Local area banks
        "COLX",  # Coastal Local Area Bank
        "KBSX",  # Krishna Bhima Samruddhi Local Area Bank
        # Payments banks
        "PYTM",  # Paytm Payments Bank
        "AIRP",  # Airtel Payments Bank
        "FINO",  # Fino Payments Bank
        "NSPB",  # NSDL Payments Bank
        "IPOS",  # India Post Payments Bank
        "IPPB",  # India Post Payments Bank (current code, see refresh note above)
        "JIOP",  # Jio Payments Bank
    }
)
