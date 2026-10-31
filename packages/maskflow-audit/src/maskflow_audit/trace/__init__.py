"""Backward tracing: a sink's payload argument -> where that text came from.

M1 ships the intra-procedural pass in backward.py. Inter-procedural
following (one or two levels) and DB-schema awareness land with M2, when
the canary harness can check the answer rather than assert it.
"""

from __future__ import annotations

from .backward import trace_payload

__all__ = ["trace_payload"]
