"""Get canaries into the application's data, however it stores it.

Pluggable because there is no common shape: one project has JSON fixtures,
the next a SQL seed file, the next a factory_boy factory. Each adapter
declares whether it recognises a tree and what it changed, and every
adapter is reversible -- `restore()` puts the tree back, because an audit
that leaves canary data behind in somebody's repository is a bug.
"""

from __future__ import annotations

from .adapters import ADAPTERS, EnvSeeder, JsonCsvSeeder, PytestFixtureSeeder, SqliteSeeder
from .base import Seeder, SeedResult
from .safety import ProductionLooksLikely, assert_not_production

__all__ = [
    "ADAPTERS",
    "EnvSeeder",
    "JsonCsvSeeder",
    "ProductionLooksLikely",
    "PytestFixtureSeeder",
    "SeedResult",
    "Seeder",
    "SqliteSeeder",
    "assert_not_production",
]
