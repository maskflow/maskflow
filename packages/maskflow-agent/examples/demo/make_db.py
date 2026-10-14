"""Build the demo's KYC database. Every value is SYNTHETIC: names from
MaskFlow's public name list, Aadhaar numbers with a valid Verhoeff check
digit, PAN/mobile/UPI in the right shape -- all random, seeded, and none
belonging to a real person.

    python make_db.py kyc.db
"""

from __future__ import annotations

import random
import sqlite3
import sys

from maskflow_pack_india.checksums import verhoeff_generate

NAMES = ["Ananya Iyer", "Rohan Mehta", "Priya Nair", "Arjun Reddy", "Kavya Sharma", "Vikram Rao"]
PSPS = ["okaxis", "oksbi", "ybl", "paytm"]
LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ"


def row(rng: random.Random, i: int, name: str) -> tuple[object, ...]:
    base = rng.choice("23456789") + "".join(rng.choice("0123456789") for _ in range(10))
    aadhaar = base + verhoeff_generate(base)
    pan = (
        "".join(rng.choice(LETTERS) for _ in range(3)) + "P" + name.split()[-1][0]
        + "".join(rng.choice("0123456789") for _ in range(4)) + rng.choice(LETTERS)
    )  # fmt: skip
    mobile = rng.choice("6789") + "".join(rng.choice("0123456789") for _ in range(9))
    upi = f"{name.split()[0].lower()}{rng.randint(10, 99)}@{rng.choice(PSPS)}"
    status = "stuck" if i == 4 else rng.choice(["verified", "verified", "pending"])
    return (i, name, aadhaar, pan, mobile, upi, status)


def main(path: str) -> None:
    rng = random.Random(4207)
    db = sqlite3.connect(path)
    db.execute("DROP TABLE IF EXISTS kyc")
    db.execute(
        "CREATE TABLE kyc (id INTEGER PRIMARY KEY, name TEXT, aadhaar TEXT, pan TEXT, "
        "mobile TEXT, upi TEXT, status TEXT)"
    )
    db.executemany(
        "INSERT INTO kyc VALUES (?, ?, ?, ?, ?, ?, ?)",
        [row(rng, i, n) for i, n in enumerate(NAMES, 1)],
    )
    db.commit()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "kyc.db")
