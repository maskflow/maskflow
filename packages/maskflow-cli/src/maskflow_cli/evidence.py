"""`maskflow explain --evidence`: emit one metadata-only evidence event per
detected (or near-miss) entity type for this run.

Thin glue over ``maskflow_evidence``, which is an **optional** dependency
(``pip install maskflow-cli[evidence]``) -- imported lazily so a bare CLI
install without it still runs every other command.
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from pathlib import Path

from maskflow_core.config.schema import RootConfig
from maskflow_core.entities import Span

_MISSING = (
    "the --evidence / --evidence-file flags need the evidence extra -- "
    "install it with:  pip install 'maskflow-cli[evidence]'"
)


class EvidenceExtraMissing(RuntimeError):
    """Raised when --evidence is requested but maskflow-evidence isn't installed."""

    def __init__(self) -> None:
        super().__init__(_MISSING)


def emit_explain_evidence(
    accepted: Sequence[Span],
    rejected: Sequence[Span],
    root_config: RootConfig,
    *,
    enabled: bool,
    evidence_file: Path | None,
) -> int:
    """Emit events for one `explain` run. Returns the count emitted.

    ``enabled`` is the resolved on/off (``--evidence`` / ``[evidence]
    enabled``); ``evidence_file`` forces a file sink at that path. Returns 0
    without importing anything when evidence is off.
    """
    want = evidence_file is not None or enabled
    if not want and not root_config.evidence.enabled:
        return 0

    try:
        from dataclasses import replace

        from maskflow_evidence import (
            EventContext,
            EvidenceConfig,
            build_emitter,
            events_from_spans,
        )
    except ModuleNotFoundError as exc:
        if evidence_file is not None or enabled:
            raise EvidenceExtraMissing() from exc
        return 0  # [evidence] enabled in config but the extra isn't installed

    config = EvidenceConfig.from_rootconfig(root_config)
    if evidence_file is not None:
        config = replace(config, enabled=True, sink="file", path=str(evidence_file))
    elif enabled:
        config = replace(config, enabled=True)
    if not config.enabled:
        return 0

    ctx = EventContext(
        session_id="cli_" + secrets.token_hex(8),
        service=config.service,
        environment=config.environment,
    )
    emitter = build_emitter(config)
    try:
        events = events_from_spans(accepted, ctx, dropped=rejected)
        for event in events:
            emitter.emit(event)
        return len(events)
    finally:
        emitter.close()
