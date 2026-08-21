"""Turns schema.py's raw validation issues into a report a human can act
on: every problem at once (schema.py's validators never stop at the first
one), each annotated with where it came from (file:line, env var, or CLI
flag) -- the did-you-mean suggestion itself is already computed inline by
schema.py's validators (they know their own allowed-key sets as they walk,
no generic model introspection needed here).
"""

from __future__ import annotations

from dataclasses import dataclass

from .merge import SOURCE_LABELS, Provenance
from .schema import RawIssue


def _error_prefix(prov: Provenance | None) -> str:
    if prov is None:
        return "?"
    if prov.source in ("user_file", "project_file") and prov.location:
        return prov.location
    if prov.location:
        return f"{SOURCE_LABELS[prov.source]} ({prov.location})"
    return SOURCE_LABELS[prov.source]


def _provenance_for(
    loc: tuple[str, ...], provenance: dict[tuple[str, ...], Provenance]
) -> Provenance | None:
    for end in range(len(loc), 0, -1):
        prov = provenance.get(loc[:end])
        if prov is not None:
            return prov
    return None


@dataclass(frozen=True)
class ConfigError:
    path: str
    message: str
    prefix: str
    suggestion: str | None


def finalize_errors(
    issues: list[RawIssue], provenance: dict[tuple[str, ...], Provenance]
) -> list[ConfigError]:
    report: list[ConfigError] = []
    for issue in issues:
        prov = _provenance_for(issue.path, provenance)
        report.append(
            ConfigError(
                path=".".join(issue.path) or "<root>",
                message=issue.message,
                prefix=_error_prefix(prov),
                suggestion=issue.suggestion,
            )
        )
    return report


def format_error_report(errors: list[ConfigError]) -> str:
    lines = []
    for e in errors:
        line = f"{e.prefix}: {e.path} - {e.message}"
        if e.suggestion:
            line += f" (did you mean '{e.suggestion}'?)"
        lines.append(line)
    return "\n".join(lines)
