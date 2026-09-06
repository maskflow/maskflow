"""Abstract anonymizer contracts, signature-compatible with
``langchain_experimental.data_anonymizer.base``.

Re-implemented here (rather than imported) so ``maskflow-langchain`` does
not pull in ``langchain-experimental`` and its Presidio/spaCy stack, while
code that type-checks against ``AnonymizerBase`` / ``ReversibleAnonymizerBase``
still works after the import swap.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from .matching import (
    DEFAULT_DEANONYMIZER_MATCHING_STRATEGY,
    MappingDataType,
)


class AnonymizerBase(ABC):
    """Base class for anonymizers. ``anonymize`` is the public entry point;
    subclasses implement ``_anonymize``."""

    def anonymize(
        self,
        text: str,
        language: str | None = None,
        allow_list: list[str] | None = None,
    ) -> str:
        return self._anonymize(text, language, allow_list)

    @abstractmethod
    def _anonymize(
        self, text: str, language: str | None, allow_list: list[str] | None = None
    ) -> str: ...


class ReversibleAnonymizerBase(AnonymizerBase):
    """Base class for anonymizers that can restore the original text."""

    def deanonymize(
        self,
        text_to_deanonymize: str,
        deanonymizer_matching_strategy: Callable[
            [str, MappingDataType], str
        ] = DEFAULT_DEANONYMIZER_MATCHING_STRATEGY,
    ) -> str:
        return self._deanonymize(text_to_deanonymize, deanonymizer_matching_strategy)

    @abstractmethod
    def _deanonymize(
        self,
        text_to_deanonymize: str,
        deanonymizer_matching_strategy: Callable[[str, MappingDataType], str],
    ) -> str: ...

    @abstractmethod
    def reset_deanonymizer_mapping(self) -> None: ...
