"""The egress sink registry: what counts as "text left for a provider".

registry.yaml is the data; loader.py turns it into frozen SinkDef objects
and refuses a malformed file. Keeping it as data is what lets a contributor
add a provider without reading discovery/.
"""

from __future__ import annotations

from .loader import (
    CATEGORIES,
    ArgSpec,
    Factory,
    RegistryError,
    SinkDef,
    factory_map,
    load_registry,
    registry_path,
)

__all__ = [
    "CATEGORIES",
    "ArgSpec",
    "Factory",
    "RegistryError",
    "SinkDef",
    "factory_map",
    "load_registry",
    "registry_path",
]
