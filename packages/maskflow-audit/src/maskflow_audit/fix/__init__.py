"""The agentic fix loop, and the handoff that needs no model.

handoff.py writes a precise per-leak task list for the user's own coding
agent -- no key, no network, no model. loop.py is the orchestrator that
drives a model itself; gates.py is what makes either safe to trust.
"""

from __future__ import annotations

from .gates import GateOutcome, GateReport, run_gates
from .handoff import build_handoff, write_handoff
from .loop import FixAttempt, FixReport, FixResult, ModelFn, run_fix_loop

__all__ = [
    "FixAttempt",
    "FixReport",
    "FixResult",
    "GateOutcome",
    "GateReport",
    "ModelFn",
    "run_fix_loop",
    "build_handoff",
    "run_gates",
    "write_handoff",
]
