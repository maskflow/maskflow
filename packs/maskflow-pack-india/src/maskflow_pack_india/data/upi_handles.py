"""Bundled NPCI-issued UPI PSP handles -- the part of a VPA after '@' (e.g.
"okhdfcbank" in name@okhdfcbank). Curated, NOT exhaustive: NPCI periodically
approves new handles for new/rebranded PSPs. A handle not in this set is
treated as NOT a UPI VPA by validate_upi_vpa() (patterns.py) -- deliberately
conservative, since a handle-shaped string that happens to have a TLD-like
look (e.g. "name@company") should fall through to nothing rather than being
misclassified.

Refresh procedure:
  1. NPCI publishes the list of live PSP handles as part of its UPI
     "member/handle" directory at https://www.npci.org.in -- cross-referenced
     against each PSP's own published VPA format documentation (banks list
     their own handles on their UPI help pages).
  2. Add any newly observed handle (lowercase, no leading '@') to
     UPI_PSP_HANDLES below.
  3. Do not remove a retired handle -- old VPAs using it may still appear in
     historical text even after NPCI stops issuing new ones.
  4. Update the "last refreshed" date in this docstring.

Last refreshed: 2026-08 (manually curated from public PSP/bank documentation,
not a direct NPCI feed import -- treat as a reasonable starting set, not a
guarantee of completeness).
"""

from __future__ import annotations

UPI_PSP_HANDLES: frozenset[str] = frozenset(
    {
        # Google Pay (issued per linked bank)
        "okhdfcbank",
        "oksbi",
        "okaxis",
        "okicici",
        "okbizaxis",
        # PhonePe / Yes Bank
        "ybl",
        "yapl",
        # Paytm
        "paytm",
        # Generic / NPCI-operated
        "upi",
        # IDBI Bank (legacy handle)
        "ibl",
        # Axis Bank (incl. merchant handle used by several PSPs)
        "axl",
        "axisbank",
        # Amazon Pay
        "apl",
        "rapl",  # Amazon Pay via RBL Bank
        # Federal Bank
        "fbl",
        "federal",
        # IDFC FIRST Bank
        "idfcbank",
        # Jupiter (via Axis Bank)
        "jupiteraxis",
        # Kotak Mahindra Bank
        "kotak",
        # Yes Bank
        "yesbank",
        # State Bank of India
        "sbi",
        # ICICI Bank
        "icici",
        # HDFC Bank
        "hdfcbank",
        # IndusInd Bank
        "indus",
        # Canara Bank
        "cnrb",
        # DBS Bank India
        "dbs",
        # Bank of India
        "boi",
        # Central Bank of India
        "cbin",
        "centralbank",
        # Punjab National Bank
        "pnb",
        # Union Bank of India
        "unionbankofindia",
        "unionbank",
        # HSBC
        "hsbc",
        # Indian Bank
        "indianbank",
        # Indian Overseas Bank
        "iob",
        # Karur Vysya Bank
        "kvb",
        # Karnataka Bank
        "karb",
        # Bank of Baroda
        "barodampay",
        "baroda",
        # Freecharge (via Axis Bank)
        "freecharge",
        # MobiKwik
        "mobikwik",
        # Airtel Payments Bank
        "airtel",
        # Jio Payments Bank
        "jio",
        # Slice
        "slice",
        # Aditya Birla Finance
        "abfspay",
        # WhatsApp Pay (issued per linked bank, "wa" prefix)
        "waaxis",
        "wahdfcbank",
        "waicici",
        "wasbi",
    }
)
