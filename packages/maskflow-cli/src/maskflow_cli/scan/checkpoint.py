"""Resumable checkpoint file: atomic JSON holding the source cursor plus the
full (PII-free) aggregator state, so a killed multi-gigabyte scan resumes
where it stopped instead of restarting."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

CHECKPOINT_VERSION = 1


class CheckpointMismatch(Exception):
    """The on-disk checkpoint was built for a different input or detection
    config; resuming it would produce a corrupt report."""


@dataclass(frozen=True)
class Checkpoint:
    scan_id: str
    spec_fingerprint: str
    detection_fingerprint: str
    cursor: str | None
    aggregator_state: dict

    def to_json(self) -> dict:
        return {
            "version": CHECKPOINT_VERSION,
            "scan_id": self.scan_id,
            "spec_fingerprint": self.spec_fingerprint,
            "detection_fingerprint": self.detection_fingerprint,
            "cursor": self.cursor,
            "aggregator_state": self.aggregator_state,
        }


def write_checkpoint(path: Path, checkpoint: Checkpoint) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(checkpoint.to_json(), fh)
        os.replace(tmp, path)  # atomic on POSIX and Windows
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_checkpoint(
    path: Path, *, spec_fingerprint: str, detection_fingerprint: str
) -> Checkpoint | None:
    """Return the checkpoint if it exists and matches the current run;
    None if it does not exist; raise CheckpointMismatch if it exists but
    was built for a different input/config."""
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != CHECKPOINT_VERSION:
        raise CheckpointMismatch(
            f"{path} is from an older maskflow scan (v{data.get('version')}); re-run with --restart"
        )
    if data["spec_fingerprint"] != spec_fingerprint:
        raise CheckpointMismatch(
            f"{path} was built for a different source/selector. "
            "Re-run with --restart to start fresh, or --checkpoint PATH for a new file."
        )
    if data["detection_fingerprint"] != detection_fingerprint:
        raise CheckpointMismatch(
            f"{path} was built with different detection settings (--deep or .maskflowrc "
            "changed). Re-run with --restart, or --checkpoint PATH."
        )
    return Checkpoint(
        scan_id=data["scan_id"],
        spec_fingerprint=data["spec_fingerprint"],
        detection_fingerprint=data["detection_fingerprint"],
        cursor=data["cursor"],
        aggregator_state=data["aggregator_state"],
    )
