"""Refuse to seed anything that looks like production.

The audit writes identifier-shaped data into a database and runs the
project's test suite against it. Doing that to production would be a data
incident caused by the tool that exists to prevent data incidents, so the
check is a hard gate rather than a warning, and the override is explicit.

The heuristics are deliberately broad and err toward refusing: a false
refusal costs one flag, a false pass costs a production database.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

#: Environment variables that commonly name the deployment environment.
_ENV_VARS = ("ENV", "ENVIRONMENT", "APP_ENV", "DJANGO_ENV", "NODE_ENV", "STAGE", "DEPLOY_ENV")

#: Values of those that mean "do not touch this".
_PROD_VALUES = frozenset({"prod", "production", "live", "staging", "stage", "preprod"})

#: Substrings in a database URL that suggest a real deployment.
_PROD_URL_MARKERS = (
    "prod",
    "live",
    "rds.amazonaws.com",
    "neon.tech",
    "supabase.co",
    "azure.com",
    "cloudsql",
    ".rds.",
    "planetscale",
    "cockroachlabs.cloud",
    "mongodb.net",
)

#: A URL containing one of these is a local database and is fine.
_LOCAL_MARKERS = ("localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal", "/tmp/")

#: Environment variables likely to hold a database URL.
_DB_URL_VARS = (
    "DATABASE_URL",
    "DB_URL",
    "POSTGRES_URL",
    "POSTGRES_DSN",
    "MYSQL_URL",
    "MONGODB_URI",
    "REDIS_URL",
)

_PROD_WORD = re.compile(r"\b(prod|production|live)\b", re.IGNORECASE)


class ProductionLooksLikely(Exception):
    """The environment looks like production; seeding refused.

    Carries the reasons -- variable names and matched markers, never the
    full connection string, which holds credentials.
    """

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        joined = "\n".join(f"  - {r}" for r in reasons)
        super().__init__(
            "refusing to seed canaries: this looks like a real deployment, not a "
            f"test environment:\n{joined}\n"
            "Canaries are identifier-shaped data written into your database. If this "
            "really is a throwaway environment, re-run with --allow-env."
        )


def _url_reasons() -> list[str]:
    reasons: list[str] = []
    for var in _DB_URL_VARS:
        value = os.environ.get(var)
        if not value:
            continue
        lowered = value.lower()
        if any(marker in lowered for marker in _LOCAL_MARKERS):
            continue
        hits = [m for m in _PROD_URL_MARKERS if m in lowered]
        if hits:
            # Name the variable and the marker, never the value: a DSN
            # carries a password.
            reasons.append(f"{var} contains {hits[0]!r} and is not a local address")
        elif "://" in lowered:
            reasons.append(f"{var} points at a non-local host")
    return reasons


def assert_not_production(root: Path, *, allow_env: bool = False) -> list[str]:
    """Raise unless this looks like a safe place to write canaries.

    Returns the list of warnings when `allow_env` overrode a refusal, so
    the caller can print them -- an override should still be loud.
    """
    reasons: list[str] = []

    for var in _ENV_VARS:
        value = (os.environ.get(var) or "").strip().lower()
        if value in _PROD_VALUES:
            reasons.append(f"{var}={value}")

    reasons += _url_reasons()

    # A .env committed next to the code, naming production.
    for candidate in (".env", ".env.production", ".env.prod"):
        path = root / candidate
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if _PROD_WORD.search(text):
                reasons.append(f"{candidate} mentions production")

    if reasons and not allow_env:
        raise ProductionLooksLikely(reasons)
    return reasons
