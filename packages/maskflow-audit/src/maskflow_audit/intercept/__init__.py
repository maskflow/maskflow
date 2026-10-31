"""Capture outbound requests in-process, with the call stack at send time.

transport.py patches the HTTP client libraries; capture.py is the record
each patch produces. A recording proxy would also work and needs no
patching, but it cannot see the Python stack -- and the stack is the
evidence that turns "this flow looks unmasked" into "this line sent it".
"""

from __future__ import annotations

from .capture import Capture, CaptureStore, StackFrame
from .transport import PROVIDER_HOSTS, intercept, is_provider_host

__all__ = [
    "PROVIDER_HOSTS",
    "Capture",
    "CaptureStore",
    "StackFrame",
    "intercept",
    "is_provider_host",
]
