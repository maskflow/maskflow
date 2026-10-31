"""Canaries: synthetic identities that prove a path leaks.

generate.py builds them on the shipped pack's own surrogate generators;
manifest.py records them and re-validates every one against the pack's
validators before any of them is allowed near a test run.
"""

from __future__ import annotations

from .generate import CANARY_TYPES, generate_identity
from .manifest import Canary, CanaryManifest, SelfCheckFailure, build_manifest

__all__ = [
    "CANARY_TYPES",
    "Canary",
    "CanaryManifest",
    "SelfCheckFailure",
    "build_manifest",
    "generate_identity",
]
