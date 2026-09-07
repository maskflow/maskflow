"""Resolve ``engine_version`` and ``pack_version`` for an evidence event.

Both come from installed distribution metadata -- never hard-coded -- so an
event always records the versions that actually did the masking.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, distributions
from importlib.metadata import version as _dist_version

# Packs advertise their recognizers under this entry-point group (see
# maskflow_core/recognizer.py). We read the group to discover which packs
# are installed without importing any of them.
_RECOGNIZER_GROUP = "maskflow.recognizers"

# The pack whose version fills the single `pack_version` field when it is
# installed. MaskFlow exists for Indian PII; that pack is the one an
# attestation is about.
_PRIMARY_PACK = "maskflow-pack-india"

_FALLBACK = "unknown"


def engine_version() -> str:
    try:
        return _dist_version("maskflow-core")
    except PackageNotFoundError:
        return _FALLBACK


def pack_versions() -> dict[str, str]:
    """Every installed distribution that registers MaskFlow recognizers,
    mapped to its version. Distribution names are slugs already."""
    found: dict[str, str] = {}
    for dist in distributions():
        entry_points = dist.entry_points
        if any(ep.group == _RECOGNIZER_GROUP for ep in entry_points):
            name = dist.metadata["Name"]
            if name:
                found[name] = dist.version
    return dict(sorted(found.items()))


def pack_version() -> str:
    """The value for an event's ``pack_version`` field: the India pack's
    version if installed, else the first recognizer-providing pack by name,
    else ``"none"``."""
    packs = pack_versions()
    if _PRIMARY_PACK in packs:
        return packs[_PRIMARY_PACK]
    if packs:
        return next(iter(packs.values()))
    return "none"
