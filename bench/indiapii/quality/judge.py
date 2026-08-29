"""LLM judge: scores one task's final (post-unmask) response against its
source document and instruction on three 1-5 dimensions -- task_completion,
fluency, factual_consistency -- via tool-use structured output, the same
reliability argument bench/indiapii/harness/adapters/llm_adapter.py makes
for forcing a tool call over free-text JSON parsing. Judged on the FINAL
response so all three masking conditions (pipeline.py) are graded in
exactly the same terms: what a real user would actually read.
"""

from __future__ import annotations

import os
from typing import Any

from .cache import DiskCache

_DEFAULT_JUDGE_MODEL = "claude-opus-5"

_TOOL_NAME = "report_judgment"

_TOOL: dict[str, Any] = {
    "name": _TOOL_NAME,
    "description": "Report the rubric scores for one response.",
    "input_schema": {
        "type": "object",
        "properties": {
            "task_completion": {"type": "integer", "minimum": 1, "maximum": 5},
            "fluency": {"type": "integer", "minimum": 1, "maximum": 5},
            "factual_consistency": {"type": "integer", "minimum": 1, "maximum": 5},
            "rationale": {"type": "string", "description": "One or two sentences."},
        },
        "required": ["task_completion", "fluency", "factual_consistency", "rationale"],
    },
}

_SYSTEM_PROMPT = """You are grading one response to a document-processing task.
Score it on three dimensions, 1-5 each:

- task_completion: did it do what was asked, fully?
  1=ignored/off-topic/refused, 2=missed major requested elements,
  3=core ask done with minor gaps, 4=all requested elements present,
  5=fully complete and correctly scoped, nothing extraneous or missing.
- fluency: is it well-formed, natural prose for this task?
  1=incoherent/unusable, 2=readable but awkward/repetitive/wrong tone,
  3=acceptable minor awkwardness, 4=natural and right register,
  5=polished, indistinguishable from a competent human draft.
- factual_consistency: does every name/number/date/amount/ID/decision in
  the response match the source document, with nothing fabricated or
  dropped? 1=fabricates or contradicts multiple facts, 2=one or more
  material factual errors, 3=minor slip that doesn't change meaning,
  4=fully consistent with the source, no fabrication, 5=fully consistent
  AND every PII detail relevant to the task is correctly restored -- no
  leaked placeholder token (e.g. a literal "<PAN_1>" left in the text),
  no hallucinated identifier.

Call report_judgment with your scores and a one-or-two-sentence rationale."""


class Judge:
    name = "judge"

    def __init__(self, cache: DiskCache) -> None:
        self._cache = cache
        self._model = os.environ.get("MASKFLOW_BENCH_QUALITY_JUDGE_MODEL", _DEFAULT_JUDGE_MODEL)
        self._client: Any = None

    def available(self) -> tuple[bool, str]:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return False, "ANTHROPIC_API_KEY not set"
        if self._client is None:
            try:
                import anthropic

                self._client = anthropic.Anthropic()
            except Exception as exc:  # noqa: BLE001
                return False, f"anthropic client init failed: {exc}"
        return True, ""

    def score(self, instruction: str, source_document: str, response: str) -> dict[str, Any]:
        cache_key = f"judge|{self._model}|{instruction}|{source_document}|{response}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return dict(cached)

        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)

        message = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Task instruction:\n{instruction}\n\n"
                        f"Source document:\n{source_document}\n\n"
                        f"Response to grade:\n{response}"
                    ),
                }
            ],
        )
        result: dict[str, Any] = {}
        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and block.name == _TOOL_NAME:
                result = dict(block.input)
                break
        self._cache.set(cache_key, result)
        return result
