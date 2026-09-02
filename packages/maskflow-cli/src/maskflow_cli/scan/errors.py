"""Scan-layer exceptions. Standalone (no imports from the rest of `scan`)
so any module can raise them without risking an import cycle.

Every message is shown to the user verbatim, so phrase them as fix-it
guidance and never interpolate record content into them (CLAUDE.md rule 1).
"""

from __future__ import annotations


class SourceError(Exception):
    """Base for every source-layer failure."""


class SourceConfigError(SourceError):
    """Missing or malformed source configuration."""


class SourceAuthError(SourceError):
    """Credentials absent, rejected, or lacking permission."""
