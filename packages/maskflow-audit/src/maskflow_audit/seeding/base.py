"""The seeding adapter contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..canary.manifest import CanaryManifest


@dataclass(frozen=True)
class SeedResult:
    """What one adapter did. Identifiers and counts only -- no values."""

    adapter: str
    applied: bool
    targets: tuple[str, ...] = ()  # files / tables touched, repo-relative
    values_written: int = 0
    note: str = ""
    #: Original contents of every file this adapter rewrote, so the tree can
    #: be restored. Held in memory on purpose: writing a backup file into
    #: somebody's repository is its own kind of mess.
    backups: dict[str, str] = field(default_factory=dict, repr=False)


@runtime_checkable
class Seeder(Protocol):
    """An adapter that can put canaries where the application reads them."""

    name: str

    def detect(self, root: Path) -> bool:
        """Does this tree have anything this adapter can seed?"""
        ...

    def seed(self, root: Path, manifest: CanaryManifest) -> SeedResult:
        """Write canaries. Must record backups for anything it rewrites."""
        ...

    def restore(self, root: Path, result: SeedResult) -> None:
        """Undo `seed`, so the tree is left exactly as it was found."""
        ...
