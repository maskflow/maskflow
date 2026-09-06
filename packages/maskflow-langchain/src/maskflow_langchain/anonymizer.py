"""``MaskflowAnonymizer`` / ``MaskflowReversibleAnonymizer`` -- drop-in
replacements for ``langchain_experimental.data_anonymizer``'s
``PresidioAnonymizer`` / ``PresidioReversibleAnonymizer``.

Migrating a chain is meant to be one import line::

    # from langchain_experimental.data_anonymizer import PresidioReversibleAnonymizer
    from maskflow_langchain import MaskflowReversibleAnonymizer as PresidioReversibleAnonymizer

The methods a chain touches keep the same names and shapes: ``.anonymize``,
``.deanonymize``, ``.reset_deanonymizer_mapping``, ``.deanonymizer_mapping``,
``.anonymizer_mapping``, ``.save_deanonymizer_mapping``,
``.load_deanonymizer_mapping``. Detection is MaskFlow's engine, so the
Indian identifiers (Aadhaar, PAN, GSTIN, UPI, IFSC, ABHA, Indian names /
addresses) are covered alongside the generic PII.

Two places diverge from Presidio, both documented on the methods:
``add_recognizer`` (MaskFlow custom patterns are registered differently) and
``add_operators`` (MaskFlow strategy names, not Presidio ``OperatorConfig``).
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

import maskflow
from maskflow import RootConfig, Session
from maskflow_core import PIIType
from maskflow_core.config import EntityConfig, ExclusionsConfig, MaskflowSection
from maskflow_core.strategies import Strategy

from ._mapping import (
    flat_token_pairs,
    invert,
    merge_into,
    session_deanonymizer_mapping,
)
from .base import AnonymizerBase, ReversibleAnonymizerBase
from .matching import MappingDataType
from .runnables import MaskflowDeanonymizer

_STRATEGY_NAMES = {s.value: s for s in Strategy}


def _build_config(
    *,
    analyzed_fields: list[str] | None,
    operators: dict[str, str] | None,
    add_default_faker_operators: bool,
    allow_list: list[str] | None,
    base: RootConfig | None,
) -> RootConfig:
    entities: dict[str, EntityConfig] = dict(base.entities) if base else {}

    if analyzed_fields is not None:
        keep = set(analyzed_fields)
        for known in PIIType.values():
            if known.value not in keep:
                entities[known.value] = EntityConfig(enabled=False)

    for entity_type, strategy_name in (operators or {}).items():
        strategy = _STRATEGY_NAMES.get(strategy_name.lower())
        if strategy is None:
            raise ValueError(
                f"operators[{entity_type!r}] = {strategy_name!r}: expected one of "
                f"{sorted(_STRATEGY_NAMES)}"
            )
        prev = entities.get(entity_type, EntityConfig())
        entities[entity_type] = EntityConfig(
            enabled=prev.enabled, threshold=prev.threshold, strategy=strategy
        )

    section = base.maskflow if base else MaskflowSection()
    if add_default_faker_operators:
        section = MaskflowSection(packs=section.packs, default_strategy=Strategy.SURROGATE)

    exclusion_values = list(base.exclusions.values) if base else []
    if allow_list:
        exclusion_values = [*exclusion_values, *allow_list]

    return RootConfig(
        maskflow=section,
        entities=entities,
        custom=dict(base.custom) if base else {},
        exclusions=ExclusionsConfig(
            values=exclusion_values,
            patterns=list(base.exclusions.patterns) if base else [],
        ),
    )


def _warn_unsupported(languages_config: Any, language: str | None) -> None:
    if languages_config is not None:
        warnings.warn(
            "maskflow-langchain ignores `languages_config` (Presidio/spaCy specific). "
            "MaskFlow runs its own EN + India NER pipeline.",
            stacklevel=3,
        )
    if language is not None and language != "en":
        warnings.warn(
            f"maskflow-langchain ignores language={language!r}; detection is EN + India.",
            stacklevel=3,
        )


class MaskflowAnonymizer(AnonymizerBase):
    """Non-reversible anonymizer: each ``anonymize`` call is independent, no
    mapping is kept. Mirrors ``PresidioAnonymizer``. Use
    ``MaskflowReversibleAnonymizer`` when the response has to be restored."""

    def __init__(
        self,
        analyzed_fields: list[str] | None = None,
        operators: dict[str, str] | None = None,
        languages_config: Any = None,
        add_default_faker_operators: bool = True,
        faker_seed: int | None = None,
        *,
        min_confidence: float | None = None,
        patterns_only: bool = False,
        config: RootConfig | None = None,
    ) -> None:
        _warn_unsupported(languages_config, None)
        if faker_seed is not None:
            warnings.warn(
                "maskflow-langchain accepts `faker_seed` for signature parity but does "
                "not seed surrogate generation.",
                stacklevel=2,
            )
        self._analyzed_fields = analyzed_fields
        self._operators = operators
        self._add_faker = add_default_faker_operators
        self._min_confidence = min_confidence
        self._patterns_only = patterns_only
        self._base_config = config

    def _anonymize(
        self, text: str, language: str | None, allow_list: list[str] | None = None
    ) -> str:
        _warn_unsupported(None, language)
        cfg = _build_config(
            analyzed_fields=self._analyzed_fields,
            operators=self._operators,
            add_default_faker_operators=self._add_faker,
            allow_list=allow_list,
            base=self._base_config,
        )
        kwargs: dict[str, Any] = {"config": cfg, "patterns_only": self._patterns_only}
        if self._min_confidence is not None:
            kwargs["min_confidence"] = self._min_confidence
        with maskflow.session(ttl_seconds=None, **kwargs) as session:
            return session.mask(text)


class MaskflowReversibleAnonymizer(ReversibleAnonymizerBase):
    """Reversible anonymizer backed by a long-lived ``maskflow.Session``, so a
    value keeps the same placeholder across every ``anonymize`` call for the
    life of this object. Mirrors ``PresidioReversibleAnonymizer``."""

    def __init__(
        self,
        analyzed_fields: list[str] | None = None,
        operators: dict[str, str] | None = None,
        languages_config: Any = None,
        add_default_faker_operators: bool = False,
        faker_seed: int | None = None,
        *,
        min_confidence: float | None = None,
        patterns_only: bool = False,
        config: RootConfig | None = None,
        allow_list: list[str] | None = None,
    ) -> None:
        _warn_unsupported(languages_config, None)
        if faker_seed is not None:
            warnings.warn(
                "maskflow-langchain accepts `faker_seed` for signature parity but does "
                "not seed surrogate generation.",
                stacklevel=2,
            )
        self._analyzed_fields = list(analyzed_fields) if analyzed_fields is not None else None
        self._operators = dict(operators) if operators else None
        self._add_faker = add_default_faker_operators
        self._min_confidence = min_confidence
        self._patterns_only = patterns_only
        self._base_config = config
        self._allow_list = list(allow_list) if allow_list else None
        self._loaded: MappingDataType = {}
        self._session: Session = self._new_session()

    # -- session -----------------------------------------------------------
    def _new_session(self) -> Session:
        cfg = _build_config(
            analyzed_fields=self._analyzed_fields,
            operators=self._operators,
            add_default_faker_operators=self._add_faker,
            allow_list=self._allow_list,
            base=self._base_config,
        )
        kwargs: dict[str, Any] = {
            "ttl_seconds": None,
            "config": cfg,
            "patterns_only": self._patterns_only,
        }
        if self._min_confidence is not None:
            kwargs["min_confidence"] = self._min_confidence
        return maskflow.Session(**kwargs)

    # -- anonymize / deanonymize ----------------------------------------------
    def _anonymize(
        self, text: str, language: str | None, allow_list: list[str] | None = None
    ) -> str:
        _warn_unsupported(None, language)
        if allow_list is not None and allow_list != (self._allow_list or []):
            raise ValueError(
                "MaskflowReversibleAnonymizer takes `allow_list` in the constructor "
                "(the session is built once); a per-call allow_list would need a new "
                "session and would drop existing placeholder identity."
            )
        return self._session.mask(text)

    def _deanonymize(
        self,
        text_to_deanonymize: str,
        deanonymizer_matching_strategy: Callable[[str, MappingDataType], str],
    ) -> str:
        mapping = self.deanonymizer_mapping
        if not mapping:
            warnings.warn(
                "No deanonymizer mapping yet -- call anonymize() (or "
                "load_deanonymizer_mapping()) before deanonymize(). Returning text "
                "unchanged.",
                stacklevel=2,
            )
            return text_to_deanonymize
        return deanonymizer_matching_strategy(text_to_deanonymize, mapping)

    def reset_deanonymizer_mapping(self) -> None:
        self._session.close()
        self._session = self._new_session()
        self._loaded = {}

    # -- mapping views ------------------------------------------------------
    @property
    def deanonymizer_mapping(self) -> MappingDataType:
        """``{ENTITY: {<placeholder>: original}}`` -- session-derived, merged
        with anything from ``load_deanonymizer_mapping``."""
        merged: MappingDataType = {
            entity_type: dict(inner) for entity_type, inner in self._loaded.items()
        }
        merge_into(merged, session_deanonymizer_mapping(self._session))
        return merged

    @property
    def anonymizer_mapping(self) -> MappingDataType:
        """``{ENTITY: {original: <placeholder>}}`` -- the inverse view."""
        return invert(self.deanonymizer_mapping)

    def token_pairs(self) -> dict[str, str]:
        """``{<placeholder>: original}`` flat -- for a streaming unmask (see
        ``MaskflowDeanonymizer``)."""
        return flat_token_pairs(self.deanonymizer_mapping)

    @property
    def deanonymizer(self) -> MaskflowDeanonymizer:
        """A streaming-aware ``Runnable[str, str]`` to put at the tail of an
        LCEL chain in place of ``RunnableLambda(self.deanonymize)`` -- it
        restores originals chunk by chunk under ``chain.stream()``."""
        return MaskflowDeanonymizer(self)

    # -- persistence (JSON always; YAML with the [yaml] extra) --------------
    def save_deanonymizer_mapping(self, file_path: str | Path) -> None:
        path = Path(file_path)
        data = self.deanonymizer_mapping
        if path.suffix == ".json":
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        elif path.suffix in (".yaml", ".yml"):
            import yaml

            path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
        else:
            raise ValueError(f"{path.suffix!r}: expected .json, .yaml, or .yml")

    def load_deanonymizer_mapping(self, file_path: str | Path) -> None:
        """Merge a saved mapping in for deanonymize(). Note: this restores
        deanonymize state only, not the session's counters -- new anonymize()
        calls continue numbering from the session, same as
        ``PresidioReversibleAnonymizer``."""
        path = Path(file_path)
        if path.suffix == ".json":
            loaded = json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix in (".yaml", ".yml"):
            import yaml

            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        else:
            raise ValueError(f"{path.suffix!r}: expected .json, .yaml, or .yml")
        merge_into(self._loaded, loaded)

    # -- extension points (diverge from Presidio) --------------------------
    def add_recognizer(
        self,
        *,
        entity_type: str,
        regex: str,
        base_confidence: float = 0.6,
        context_keywords: tuple[str, ...] | None = None,
    ) -> None:
        """Register a custom regex recognizer. Unlike
        ``PresidioReversibleAnonymizer.add_recognizer(recognizer_obj)``, this
        takes a pattern directly -- MaskFlow recognizers are process-global
        (``maskflow_core.register_pattern`` / entry-point plugins), so this
        registers one and adds ``entity_type`` to the analyzed set. Rebuilds
        the session, which resets placeholder identity."""
        import re

        from maskflow_core import register_pattern

        register_pattern(
            entity_type, re.compile(regex), base_confidence, context_keywords=context_keywords
        )
        if self._analyzed_fields is not None and entity_type not in self._analyzed_fields:
            self._analyzed_fields.append(entity_type)
        self.reset_deanonymizer_mapping()

    def add_operators(self, operators: dict[str, str]) -> None:
        """Set the substitution strategy per entity type. Values are MaskFlow
        strategy names (``replace`` / ``redact`` / ``mask`` / ``hash`` /
        ``surrogate``), not Presidio ``OperatorConfig`` objects. Rebuilds the
        session, which resets placeholder identity."""
        self._operators = {**(self._operators or {}), **operators}
        self.reset_deanonymizer_mapping()
