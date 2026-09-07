"""`maskflow explain --evidence`: emit one metadata-only evidence event per
detected (or near-miss) entity type for this run.

Thin glue over ``maskflow_evidence``; kept out of ``explain.py`` so that
module stays import-light and console-free.
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from maskflow_core.config.schema import RootConfig
from maskflow_core.entities import Span
from maskflow_evidence import (
    EventContext,
    EvidenceConfig,
    build_emitter,
    events_from_spans,
)


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
    enabled``); ``evidence_file`` forces a file sink at that path.
    """
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
