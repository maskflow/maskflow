"""Data gathering for `maskflow doctor` -- pure checks, no Rich/Typer here,
so the logic is testable without rendering. See doctor_render.py for the
table output and commands/doctor_cmd.py for the Typer command + exit code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import metadata
from typing import Literal

from maskflow_core.config.resolve import ConfigResolutionError, ResolvedConfig, resolve_config
from maskflow_core.entities import PIIType
from maskflow_core.ner import MODEL_NAME
from maskflow_core.registry import NER_RECOGNIZERS, PATTERNS

Status = Literal["ok", "warn", "error"]


@dataclass(frozen=True)
class ComponentCheck:
    name: str
    version: str | None
    status: Status
    detail: str = ""


@dataclass(frozen=True)
class EntityCheck:
    name: str
    detector: str
    enabled: bool
    reason: str = ""


@dataclass(frozen=True)
class DoctorReport:
    components: list[ComponentCheck] = field(default_factory=list)
    entities: list[EntityCheck] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for c in self.components if c.status == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.components if c.status == "warn")

    @property
    def healthy(self) -> bool:
        return self.error_count == 0


def _version(dist_name: str) -> str | None:
    try:
        return metadata.version(dist_name)
    except metadata.PackageNotFoundError:
        return None


def _check_packages() -> list[ComponentCheck]:
    checks: list[ComponentCheck] = []

    for dist_name in ("maskflow-core", "maskflow-cli"):
        version = _version(dist_name)
        if version is None:
            checks.append(ComponentCheck(dist_name, None, "error", "not installed"))
        else:
            checks.append(ComponentCheck(dist_name, version, "ok"))

    installed_packs = sorted(
        {
            name
            for dist in metadata.distributions()
            if (name := dist.metadata.get("Name")) and name.startswith("maskflow-pack-")
        }
    )
    for pack in installed_packs:
        checks.append(ComponentCheck(pack, _version(pack), "ok"))

    return checks


def _check_spacy() -> tuple[ComponentCheck, ComponentCheck]:
    model_name = f"spaCy model ({MODEL_NAME})"
    try:
        import spacy
    except ImportError:
        return (
            ComponentCheck(
                "spaCy", None, "error", "not installed (pip install maskflow-core[nlp])"
            ),
            ComponentCheck(model_name, None, "error", "unavailable -- spaCy not installed"),
        )

    spacy_check = ComponentCheck("spaCy", spacy.__version__, "ok")
    try:
        spacy.load(MODEL_NAME)
    except OSError:
        model_check = ComponentCheck(
            model_name, None, "error", f"MISSING (python -m spacy download {MODEL_NAME})"
        )
    else:
        model_check = ComponentCheck(model_name, _version(MODEL_NAME), "ok")
    return spacy_check, model_check


def _check_config() -> tuple[ComponentCheck, ResolvedConfig | None]:
    try:
        resolved = resolve_config()
    except ConfigResolutionError as exc:
        detail = f"{len(exc.errors)} error(s) -- run `maskflow config validate`"
        return ComponentCheck(".maskflowrc", None, "error", detail), None

    if resolved.project_file is not None:
        detail = f"valid (project file: {resolved.project_file})"
    elif resolved.user_file is not None:
        detail = f"valid (user file: {resolved.user_file})"
    else:
        detail = "valid (no config file found -- using defaults)"

    status: Status = "ok"
    if resolved.warnings:
        status = "warn"
        detail += f" -- {len(resolved.warnings)} warning(s), see `maskflow config validate`"

    return ComponentCheck(".maskflowrc", None, status, detail), resolved


def _check_redis() -> ComponentCheck:
    # RedisMappingStore (maskflow_core.mapping_store) is an interface-only
    # stub -- every method raises NotImplementedError regardless of whether
    # a `redis` client or server is reachable, so there is nothing to probe
    # yet. Always the same informational warning until that ships for real.
    return ComponentCheck(
        "Redis", None, "warn", "RedisMappingStore not implemented yet -- using in-memory store"
    )


def _entity_checks(resolved: ResolvedConfig | None, spacy_ready: bool) -> list[EntityCheck]:
    ner_label_by_type: dict[PIIType, str] = {
        mapping.pii_type: label for label, mapping in NER_RECOGNIZERS.items()
    }
    all_types = set(PATTERNS) | set(ner_label_by_type)

    checks: list[EntityCheck] = []
    for pii_type in sorted(all_types):
        detector = (
            f"ner:{ner_label_by_type[pii_type]}" if pii_type in ner_label_by_type else "pattern"
        )

        entity_config = (
            resolved.config.entities.get(str(pii_type)) if resolved is not None else None
        )
        if entity_config is not None and not entity_config.enabled:
            reason = ".maskflowrc: entities.<X>.enabled = false"
            checks.append(EntityCheck(str(pii_type), detector, False, reason))
            continue

        if pii_type in ner_label_by_type and not spacy_ready:
            checks.append(EntityCheck(str(pii_type), detector, False, "spaCy model unavailable"))
            continue

        checks.append(EntityCheck(str(pii_type), detector, True))

    return checks


def run_checks() -> DoctorReport:
    components: list[ComponentCheck] = []
    components.extend(_check_packages())

    spacy_check, model_check = _check_spacy()
    components.append(spacy_check)
    components.append(model_check)

    config_check, resolved = _check_config()
    components.append(config_check)

    components.append(_check_redis())

    entities = _entity_checks(resolved, spacy_ready=model_check.status == "ok")

    return DoctorReport(components=components, entities=entities)
