"""Refresh helpers for maskflow-pack-india's bundled reference datasets.

Run via `uv run python scripts/refresh_india_reference_data.py <command>`
(from the repo root). Full sourcing/licensing notes and the manual UPI
procedure live in docs/data-refresh.md -- this script only automates the
fetch-and-diff step. It never writes the bundled data files itself: each
command prints a diff for a human to review and fold in by hand, matching
the "curated, not auto-merged" refresh procedure already documented in every
data file's own docstring (packs/maskflow-pack-india/src/maskflow_pack_india/
data/*.py). Retired/renamed entries already bundled are never auto-removed --
historical documents may still reference them.

Commands:
  ifsc              Diff IFSC_BANK_CODES against razorpay/ifsc's public-domain
                     bank-code data (MIT-licensed code, public-domain dataset,
                     cross-checked against RBI publications).
  cities --input F  Diff INDIAN_CITIES against a downloaded Census 2011
                     population-by-town CSV (see docs/data-refresh.md for
                     where to get one; must have name_of_city and
                     population_total columns).
  upi               Print the (still-manual) UPI PSP-handle refresh
                     procedure -- no machine-readable authoritative NPCI feed
                     exists as of 2026-08.
"""

from __future__ import annotations

import argparse
import csv
import json
import urllib.request
from pathlib import Path

from maskflow_pack_india.data.ifsc_bank_codes import IFSC_BANK_CODES
from maskflow_pack_india.data.indian_places import INDIAN_CITIES

RAZORPAY_BANKS_URL = "https://raw.githubusercontent.com/razorpay/ifsc/master/src/banks.json"

# razorpay/ifsc's `type` field is far more granular than this pack wants:
# O-UCB/DCCB/S-UCB are urban & district co-operative banks, and its "SCB"
# means *State* Co-operative Bank (not Scheduled Commercial Bank) -- all
# deliberately out of scope, same as ifsc_bank_codes.py's own docstring
# ("major scheduled commercial banks, small finance banks, and payments
# banks"). PSB_ALLOWLIST covers legitimate merged/retired PSU codes seen in
# the wild; GPOX ("General Post Office") is excluded as not a consumer-facing
# bank a real IFSC in PII text would reference.
IN_SCOPE_TYPES = {"Foreign", "Private", "SFB", "PB", "LAB"}
PSB_ALLOWLIST = {"BKDN", "RBIN", "UTBI"}


def ifsc_diff(current: frozenset[str], fetched: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Pure diff (no I/O): (in-scope codes missing from `current`, codes in
    `current` not present in this fetch -- surfaced for review, never
    auto-removed)."""
    candidate = {
        code
        for code, meta in fetched.items()
        if meta.get("type") in IN_SCOPE_TYPES or code in PSB_ALLOWLIST
    }
    added = sorted(candidate - current)
    unseen = sorted(current - set(fetched))
    return added, unseen


def cities_diff(current: frozenset[str], rows: list[dict[str, str]]) -> list[str]:
    """Pure diff (no I/O): city names in `rows` with population >= 100,000
    that aren't already in `current`."""
    census_cities = {
        row["name_of_city"].strip()
        for row in rows
        if row.get("population_total", "").strip().isdigit()
        and int(row["population_total"]) >= 100_000
    }
    return sorted(census_cities - current)


def fetch_ifsc_candidates() -> dict[str, dict]:
    with urllib.request.urlopen(RAZORPAY_BANKS_URL, timeout=30) as resp:  # noqa: S310
        return json.load(resp)


def parse_cities_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cmd_ifsc(_args: argparse.Namespace) -> None:
    fetched = fetch_ifsc_candidates()
    added, unseen = ifsc_diff(IFSC_BANK_CODES, fetched)
    print(f"{len(added)} candidate additions (review before adding to ifsc_bank_codes.py):")
    for code in added:
        print(f"  + {code}  ({fetched[code].get('type')})")
    if unseen:
        print(f"\n{len(unseen)} bundled codes not present in this fetch (NOT auto-removed):")
        for code in sorted(unseen):
            print(f"  ? {code}")


def cmd_cities(args: argparse.Namespace) -> None:
    rows = parse_cities_csv(Path(args.input))
    added = cities_diff(frozenset(INDIAN_CITIES), rows)
    print(f"{len(added)} candidate city additions (population >= 100,000):")
    for name in added:
        print(f"  + {name}")


def cmd_upi(_args: argparse.Namespace) -> None:
    print(
        "No machine-readable authoritative NPCI PSP-handle feed exists "
        "(checked again 2026-08-27; NPCI publishes member banks, not a live "
        "handle list). Refresh manually: cross-check each PSP's own UPI "
        "help/documentation page against UPI_PSP_HANDLES in "
        "packs/maskflow-pack-india/src/maskflow_pack_india/data/upi_handles.py "
        "-- see docs/data-refresh.md for the PSP list to check and how "
        "often to repeat this."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh helpers for maskflow-pack-india's reference datasets."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ifsc = sub.add_parser("ifsc", help="Diff IFSC_BANK_CODES against razorpay/ifsc.")
    p_ifsc.set_defaults(func=cmd_ifsc)

    p_cities = sub.add_parser("cities", help="Diff INDIAN_CITIES against a Census 2011 CSV.")
    p_cities.add_argument(
        "--input", required=True, help="Path to a name_of_city/population_total CSV."
    )
    p_cities.set_defaults(func=cmd_cities)

    p_upi = sub.add_parser("upi", help="Print the manual UPI PSP-handle refresh procedure.")
    p_upi.set_defaults(func=cmd_upi)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
