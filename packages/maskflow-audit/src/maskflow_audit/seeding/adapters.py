"""The shipped seeding adapters.

Each one is deliberately conservative: it only touches a file it is
confident is test data, it records a backup of everything it rewrites, and
`restore()` puts the tree back byte for byte. An audit that leaves canary
values behind in somebody's repository would be a worse bug than the one it
was looking for.

Field selection reuses the column-name vocabulary the tabular benchmark
established (`bench/tabular/generate.py`'s PII_COLUMNS), normalised the way
`maskflow_core.context._words` normalises a header -- separators to spaces,
camelCase split, casefolded -- so `MobileNo`, `mobile_no` and `mobile no`
all match one entry.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path

from ..canary.manifest import CanaryManifest
from .base import Seeder, SeedResult

#: Field/column name words -> canary entity type. Mined from the tabular
#: corpus's own header variants rather than invented here.
_FIELD_WORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("aadhaar",), "AADHAAR"),
    (("aadhar",), "AADHAAR"),
    (("uid",), "AADHAAR"),
    (("pan",), "PAN"),
    (("gstin",), "GSTIN"),
    (("gst",), "GSTIN"),
    (("ifsc",), "IFSC"),
    (("upi",), "UPI_VPA"),
    (("vpa",), "UPI_VPA"),
    (("mobile",), "INDIAN_MOBILE"),
    (("phone",), "INDIAN_MOBILE"),
    (("msisdn",), "INDIAN_MOBILE"),
    (("contact",), "INDIAN_MOBILE"),
    (("whatsapp",), "INDIAN_MOBILE"),
    (("name",), "PERSON_NAME"),
    (("applicant",), "PERSON_NAME"),
    (("customer",), "PERSON_NAME"),
    (("address",), "INDIAN_ADDRESS"),
    (("pincode",), "PIN_CODE"),
    (("pin", "code"), "PIN_CODE"),
    (("zipcode",), "PIN_CODE"),
    (("postal",), "PIN_CODE"),
    (("account",), "BANK_ACCOUNT_IN"),
    (("acc", "no"), "BANK_ACCOUNT_IN"),
    (("abha",), "ABHA_ADDRESS"),
    (("voter",), "VOTER_ID"),
)

#: Field names that look like PII but are not, so they are never seeded --
#: overwriting an `account_type_code` with a bank account number breaks the
#: application under test and teaches nothing.
_FIELD_DECOYS: frozenset[str] = frozenset(
    {"id", "type", "status", "code", "ref", "version", "build", "model", "count"}
)

_SEPARATORS = str.maketrans({ch: " " for ch in "_-./:#()[]{}\r\t"})

#: Directory names that mark a tree's test data. Seeding outside one of
#: these would be editing the application, not its fixtures.
_FIXTURE_DIRS: frozenset[str] = frozenset(
    {"fixtures", "fixture", "testdata", "test_data", "seeds", "seed", "tests", "test", "data"}
)


def _words(label: str) -> tuple[str, ...]:
    """Case-folded words of a field name. Mirrors core's `_words`."""
    spaced: list[str] = []
    previous = ""
    for char in label:
        if previous.isascii() and previous.islower() and char.isascii() and char.isupper():
            spaced.append(" ")
        spaced.append(char)
        previous = char
    return tuple("".join(spaced).translate(_SEPARATORS).casefold().split())


def entity_for_field(name: str) -> str | None:
    """The canary type a field name asks for, or None."""
    words = _words(name)
    if not words or set(words) <= _FIELD_DECOYS:
        return None
    for keywords, entity_type in _FIELD_WORDS:
        if all(keyword in words for keyword in keywords):
            # A decoy word alongside the match disqualifies it:
            # `account_type_code` is not a bank account.
            if any(word in _FIELD_DECOYS for word in words) and len(keywords) == 1:
                continue
            return entity_type
    return None


def _in_fixture_dir(path: Path, root: Path) -> bool:
    parts = {p.casefold() for p in path.relative_to(root).parts[:-1]}
    return bool(parts & _FIXTURE_DIRS)


class EnvSeeder:
    """Expose canaries as environment variables.

    The universal fallback, and the one a user's own `audit.flows` script
    is expected to read. It writes nothing to disk, so it is always safe
    and always applicable.
    """

    name = "env"

    def detect(self, root: Path) -> bool:
        return True

    def seed(self, root: Path, manifest: CanaryManifest) -> SeedResult:
        written = 0
        for entity_type, value in manifest.for_identity(0).items():
            os.environ[f"MASKFLOW_AUDIT_CANARY_{entity_type}"] = value
            written += 1
        os.environ["MASKFLOW_AUDIT_SEED"] = str(manifest.seed)
        return SeedResult(
            adapter=self.name,
            applied=True,
            targets=("environment",),
            values_written=written,
            note="canaries exported as MASKFLOW_AUDIT_CANARY_<TYPE>",
        )

    def restore(self, root: Path, result: SeedResult) -> None:
        for entity_type in list(os.environ):
            if entity_type.startswith("MASKFLOW_AUDIT_CANARY_"):
                os.environ.pop(entity_type, None)
        os.environ.pop("MASKFLOW_AUDIT_SEED", None)


class JsonCsvSeeder:
    """Rewrite PII-named fields in JSON / CSV test data."""

    name = "json-csv"

    def _candidates(self, root: Path) -> list[Path]:
        out: list[Path] = []
        for pattern in ("*.json", "*.csv"):
            for path in sorted(root.rglob(pattern)):
                if ".venv" in path.parts or "node_modules" in path.parts:
                    continue
                if _in_fixture_dir(path, root):
                    out.append(path)
        return out

    def detect(self, root: Path) -> bool:
        return bool(self._candidates(root))

    def _seed_json(self, data: object, values: dict[str, str], counter: list[int]) -> object:
        if isinstance(data, dict):
            out: dict[str, object] = {}
            for key, value in data.items():
                entity = entity_for_field(str(key)) if isinstance(value, (str, int)) else None
                if entity is not None and entity in values:
                    out[key] = values[entity]
                    counter[0] += 1
                else:
                    out[key] = self._seed_json(value, values, counter)
            return out
        if isinstance(data, list):
            return [self._seed_json(item, values, counter) for item in data]
        return data

    def seed(self, root: Path, manifest: CanaryManifest) -> SeedResult:
        values = manifest.for_identity(0)
        backups: dict[str, str] = {}
        targets: list[str] = []
        counter = [0]

        for path in self._candidates(root):
            try:
                original = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            if path.suffix == ".json":
                try:
                    parsed = json.loads(original)
                except json.JSONDecodeError:
                    continue
                before = counter[0]
                seeded = self._seed_json(parsed, values, counter)
                if counter[0] == before:
                    continue
                new_text = json.dumps(seeded, indent=2) + "\n"
            else:
                reader = csv.reader(io.StringIO(original))
                rows = list(reader)
                if len(rows) < 2:
                    continue
                header = rows[0]
                mapping = {i: entity_for_field(h) for i, h in enumerate(header)}
                if not any(v for v in mapping.values()):
                    continue
                for row in rows[1:]:
                    for index, entity in mapping.items():
                        if entity and entity in values and index < len(row):
                            row[index] = values[entity]
                            counter[0] += 1
                buffer = io.StringIO()
                csv.writer(buffer, lineterminator="\n").writerows(rows)
                new_text = buffer.getvalue()

            relative = path.relative_to(root).as_posix()
            backups[relative] = original
            path.write_text(new_text, encoding="utf-8")
            targets.append(relative)

        return SeedResult(
            adapter=self.name,
            applied=bool(targets),
            targets=tuple(targets),
            values_written=counter[0],
            note="PII-named fields in JSON/CSV fixtures replaced with canaries",
            backups=backups,
        )

    def restore(self, root: Path, result: SeedResult) -> None:
        for relative, original in result.backups.items():
            (root / relative).write_text(original, encoding="utf-8")


class SqliteSeeder:
    """Insert canary rows into local SQLite databases.

    Only files already present in the tree, and only tables with a
    PII-named column. Each inserted row is remembered by rowid so
    `restore()` deletes exactly what was added.
    """

    name = "sqlite"

    def _databases(self, root: Path) -> list[Path]:
        out: list[Path] = []
        for pattern in ("*.db", "*.sqlite", "*.sqlite3"):
            for path in sorted(root.rglob(pattern)):
                if ".venv" not in path.parts and "node_modules" not in path.parts:
                    out.append(path)
        return out

    def detect(self, root: Path) -> bool:
        return bool(self._databases(root))

    def seed(self, root: Path, manifest: CanaryManifest) -> SeedResult:
        values = manifest.for_identity(0)
        targets: list[str] = []
        written = 0
        inserted: dict[str, str] = {}

        for database in self._databases(root):
            try:
                connection = sqlite3.connect(database)
            except sqlite3.Error:
                continue
            try:
                tables = [
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%'"
                    )
                ]
                for table in tables:
                    info = connection.execute(f'PRAGMA table_info("{table}")')
                    columns = [row[1] for row in info]
                    mapping = {c: entity_for_field(c) for c in columns}
                    seedable = {c: e for c, e in mapping.items() if e and e in values}
                    if not seedable:
                        continue
                    names = ", ".join(f'"{c}"' for c in seedable)
                    placeholders = ", ".join("?" for _ in seedable)
                    cursor = connection.execute(
                        f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})',
                        [values[e] for e in seedable.values()],
                    )
                    written += len(seedable)
                    key = f"{database.relative_to(root).as_posix()}::{table}"
                    inserted[key] = str(cursor.lastrowid)
                    targets.append(key)
                connection.commit()
            except sqlite3.Error:
                # A locked or malformed database is skipped, never fatal:
                # an audit of a real tree will meet both.
                continue
            finally:
                connection.close()

        return SeedResult(
            adapter=self.name,
            applied=bool(targets),
            targets=tuple(targets),
            values_written=written,
            note="canary rows inserted into tables with PII-named columns",
            backups=inserted,
        )

    def restore(self, root: Path, result: SeedResult) -> None:
        for key, rowid in result.backups.items():
            relative, table = key.split("::", 1)
            try:
                connection = sqlite3.connect(root / relative)
                connection.execute(f'DELETE FROM "{table}" WHERE rowid = ?', (int(rowid),))
                connection.commit()
                connection.close()
            except (sqlite3.Error, ValueError):
                continue


class PytestFixtureSeeder:
    """Expose canaries to a pytest suite as a fixture.

    Writes a `conftest.py` into the tree's test directory providing
    `maskflow_canaries`, so a project can opt a specific test into using
    canary data without the audit having to guess its factories.
    """

    name = "pytest-fixture"
    _FILENAME = "conftest_maskflow_audit.py"

    def _test_dirs(self, root: Path) -> list[Path]:
        return [path for name in ("tests", "test") for path in [root / name] if path.is_dir()]

    def detect(self, root: Path) -> bool:
        return bool(self._test_dirs(root))

    def seed(self, root: Path, manifest: CanaryManifest) -> SeedResult:
        values = manifest.for_identity(0)
        targets: list[str] = []
        backups: dict[str, str] = {}
        body = (
            '"""Written by `maskflow audit --prove`. Deleted when it finishes.\n\n'
            "Every value here is SYNTHETIC, generated per run from seed "
            f"{manifest.seed}.\n"
            '"""\n\n'
            "import pytest\n\n"
            f"CANARIES = {values!r}\n\n\n"
            "@pytest.fixture\n"
            "def maskflow_canaries():\n"
            "    return dict(CANARIES)\n"
        )
        for directory in self._test_dirs(root):
            path = directory / self._FILENAME
            relative = path.relative_to(root).as_posix()
            if path.exists():
                backups[relative] = path.read_text(encoding="utf-8")
            path.write_text(body, encoding="utf-8")
            targets.append(relative)

        return SeedResult(
            adapter=self.name,
            applied=bool(targets),
            targets=tuple(targets),
            values_written=len(values) * len(targets),
            note=f"{self._FILENAME} provides a `maskflow_canaries` fixture",
            backups=backups,
        )

    def restore(self, root: Path, result: SeedResult) -> None:
        for relative in result.targets:
            path = root / relative
            if relative in result.backups:
                path.write_text(result.backups[relative], encoding="utf-8")
            elif path.exists():
                path.unlink()


#: Order matters: env first (always applies, writes nothing), then the
#: adapters that touch the tree.
ADAPTERS: tuple[Callable[[], Seeder], ...] = (
    EnvSeeder,
    JsonCsvSeeder,
    SqliteSeeder,
    PytestFixtureSeeder,
)
