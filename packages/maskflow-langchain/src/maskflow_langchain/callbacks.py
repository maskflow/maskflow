"""``MaskflowLeakGuardCallback`` -- a LangChain callback that watches PII
crossing the LLM boundary.

LangChain callbacks are observers: they cannot rewrite a prompt or a
response, so this does not mask. Its two jobs:

* **Audit** -- tally which PII entity types appear in prompts and
  completions, by type only, never the values (MaskFlow rule #1). Read
  ``.summary()`` for a compliance/observability signal.
* **Leak guard** (opt in) -- with ``raise_on_prompt_pii=True`` it raises in
  ``on_llm_start`` / ``on_chat_model_start`` before the model is called, so
  a prompt that still contains PII (an anonymizer that was forgotten or
  mis-wired) fails closed instead of leaking.

Wire it as a normal callback::

    guard = MaskflowLeakGuardCallback(raise_on_prompt_pii=True)
    chain.invoke(x, config={"callbacks": [guard]})
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler, BaseCallbackHandler
from maskflow_core import detect, detect_patterns_only
from maskflow_core.detection import DEFAULT_MIN_CONFIDENCE


class MaskflowPIILeakError(RuntimeError):
    """Raised by the leak guard when a prompt reaching the LLM still contains
    PII. Carries entity types and counts only, never values."""

    def __init__(self, counts: dict[str, int]) -> None:
        self.counts = dict(counts)
        summary = ", ".join(f"{n}x {t}" for t, n in sorted(counts.items()))
        super().__init__(f"Prompt reaching the LLM still contains PII: {summary}")


def _count_types(texts: list[str], min_confidence: float, patterns_only: bool) -> dict[str, int]:
    detector = detect_patterns_only if patterns_only else detect
    counts: dict[str, int] = {}
    for text in texts:
        # coerce: langchain-core's ChatGeneration.text is a str *subclass*
        # (TextAccessor) that spaCy's tokenizer rejects.
        text = str(text)
        if not text:
            continue
        for span in detector(text, min_confidence=min_confidence):
            key = span.entity_type.value
            counts[key] = counts.get(key, 0) + 1
    return counts


class _GuardMixin:
    def __init__(
        self,
        *,
        raise_on_prompt_pii: bool = False,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        patterns_only: bool = False,
    ) -> None:
        self.raise_on_prompt_pii = raise_on_prompt_pii
        self._min_confidence = min_confidence
        self._patterns_only = patterns_only
        self.prompt_detections: dict[str, int] = {}
        self.completion_detections: dict[str, int] = {}
        # run_inline so a raise in on_*_start actually aborts before the call
        self.run_inline = True
        self.raise_error = raise_on_prompt_pii

    def _add(self, target: dict[str, int], counts: dict[str, int]) -> None:
        for key, n in counts.items():
            target[key] = target.get(key, 0) + n

    def _on_prompts(self, prompts: list[str]) -> None:
        counts = _count_types(prompts, self._min_confidence, self._patterns_only)
        self._add(self.prompt_detections, counts)
        if self.raise_on_prompt_pii and counts:
            raise MaskflowPIILeakError(counts)

    def _on_completion(self, texts: list[str]) -> None:
        self._add(
            self.completion_detections,
            _count_types(texts, self._min_confidence, self._patterns_only),
        )

    def summary(self) -> dict[str, dict[str, int]]:
        """``{"prompt": {...}, "completion": {...}}`` -- cumulative entity-type
        counts since this handler was created. No values, ever."""
        return {
            "prompt": dict(self.prompt_detections),
            "completion": dict(self.completion_detections),
        }

    @staticmethod
    def _messages_to_texts(messages: list[list[Any]]) -> list[str]:
        out: list[str] = []
        for batch in messages:
            for message in batch:
                content = getattr(message, "content", None)
                if isinstance(content, str):
                    out.append(content)
                elif isinstance(content, list):
                    out.extend(
                        part["text"]
                        for part in content
                        if isinstance(part, dict) and isinstance(part.get("text"), str)
                    )
        return out

    @staticmethod
    def _llmresult_to_texts(response: Any) -> list[str]:
        out: list[str] = []
        for generations in getattr(response, "generations", []) or []:
            for gen in generations:
                text = getattr(gen, "text", None)
                if isinstance(text, str) and text:
                    out.append(text)
        return out


class MaskflowLeakGuardCallback(_GuardMixin, BaseCallbackHandler):
    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._on_prompts(prompts)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._on_prompts(self._messages_to_texts(messages))

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._on_completion(self._llmresult_to_texts(response))


class AsyncMaskflowLeakGuardCallback(_GuardMixin, AsyncCallbackHandler):
    async def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._on_prompts(prompts)

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._on_prompts(self._messages_to_texts(messages))

    async def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._on_completion(self._llmresult_to_texts(response))
