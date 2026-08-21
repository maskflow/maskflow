"""Process-level cache for the ambient (filesystem-discovered) .maskflowrc
config. A long-running server must not re-stat the filesystem on every
mask()/session() call -- resolve_config() runs at most once per process,
lazily, on first use, unless reload_config() is called explicitly.

A broken on-disk .maskflowrc raises ConfigResolutionError out of
get_ambient_config() on first use -- fails loud, consistent with "a typo
silently disabling detection is a security bug" (CLAUDE.md). No config
file anywhere is not an error: resolve_config() succeeds with an
all-defaults RootConfig, which is what makes mask()/mask_and_call()/
session() byte-identical to their pre-config behavior by default.
"""

from __future__ import annotations

import threading

from maskflow_core.config import ResolvedConfig, resolve_config

_lock = threading.Lock()
_cached: ResolvedConfig | None = None


def get_ambient_config() -> ResolvedConfig:
    global _cached
    if _cached is None:
        with _lock:
            if _cached is None:
                _cached = resolve_config()
    return _cached


def reload_config() -> ResolvedConfig:
    """Force a fresh filesystem discovery, replacing the cached ambient
    config. Every open Session keeps whatever config it already compiled
    at construction -- only future mask()/mask_and_call() calls (and new
    Session/session() calls) see the reloaded config."""
    global _cached
    with _lock:
        _cached = resolve_config()
    return _cached
