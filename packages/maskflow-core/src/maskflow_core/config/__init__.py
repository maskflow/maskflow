"""`.maskflowrc` configuration: schema, discovery, precedence/merge,
validation, and compiling a resolved config into engine primitives. A
self-contained sub-namespace -- not flattened into top-level
`maskflow_core` -- so the primary detect/mask API surface stays
uncluttered. Import as `from maskflow_core.config import ...`.
"""

from .engine import CompiledConfig, compile_config
from .errors import ConfigError, format_error_report
from .merge import Provenance
from .resolve import ConfigResolutionError, ConfigWarning, ResolvedConfig, resolve_config
from .schema import (
    CustomEntityConfig,
    EntityConfig,
    ExclusionsConfig,
    MaskflowSection,
    RootConfig,
    validate_root_config,
)

__all__ = [
    "RootConfig",
    "MaskflowSection",
    "EntityConfig",
    "CustomEntityConfig",
    "ExclusionsConfig",
    "validate_root_config",
    "resolve_config",
    "ResolvedConfig",
    "ConfigResolutionError",
    "ConfigWarning",
    "Provenance",
    "ConfigError",
    "format_error_report",
    "CompiledConfig",
    "compile_config",
]
