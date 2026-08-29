"""Runs one task under one masking condition:

- unmasked: raw document straight to the task model.
- placeholder: Strategy.REPLACE mask -> task model -> unmask().
- surrogate: Strategy.SURROGATE mask -> task model -> unmask().

`final_response` (post-unmask) is what a real user of mask_and_call() would
actually read -- this is what judge.py grades and scoring.py checks for a
leaked placeholder token, so all three conditions are compared on the same
terms. Every task-model call goes through DiskCache first (see cache.py).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import maskflow_pack_india  # noqa: F401 -- import side effect: registers recognizers + surrogates
import maskflow_pack_intl  # noqa: F401 -- import side effect: registers recognizers + surrogates
from maskflow_core.masking import mask_with_policy, unmask
from maskflow_core.policy import MaskPolicy
from maskflow_core.strategies import Strategy

from .cache import DiskCache

CONDITIONS: tuple[str, ...] = ("unmasked", "placeholder", "surrogate")

_DEFAULT_TASK_MODEL = "claude-sonnet-5"

_POLICIES: dict[str, MaskPolicy | None] = {
    "unmasked": None,
    "placeholder": MaskPolicy(default_strategy=Strategy.REPLACE),
    "surrogate": MaskPolicy(default_strategy=Strategy.SURROGATE),
}

# Same shape masking.py's own _RESERVED_TOKEN_RE matches -- a token that
# survives unmask() into the final response means unmask() had nothing to
# restore it with (a masked-condition bug), not that the model wrote
# literal angle brackets.
_LEAK_RE = re.compile(r"<[A-Z_]+_\d+(?:_[0-9a-f]+)?>")

_SYSTEM_PROMPT = (
    "You complete the requested task based ONLY on the document below. "
    "The document may contain tokens like <PERSON_NAME_1> or <PAN_1> in "
    "place of real values -- treat each such token as an opaque stand-in "
    "for the real value and reproduce it verbatim wherever the task calls "
    "for that value; never invent, alter, or guess what it stands for."
)


@dataclass(frozen=True)
class ConditionResult:
    condition: str
    prompt_sent: str
    raw_response: str
    final_response: str
    had_leak: bool


class TaskModel:
    name = "task_model"

    def __init__(self, cache: DiskCache) -> None:
        self._cache = cache
        self._model = os.environ.get("MASKFLOW_BENCH_QUALITY_TASK_MODEL", _DEFAULT_TASK_MODEL)
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

    def generate(self, instruction: str, document: str) -> str:
        cache_key = f"task_model|{self._model}|{instruction}|{document}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return str(cached["response"])

        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"{instruction}\n\n---\n{document}\n---"}],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        self._cache.set(cache_key, {"response": text})
        return text


def run_condition(
    model: TaskModel, condition: str, instruction: str, source_text: str
) -> ConditionResult:
    policy = _POLICIES[condition]
    if policy is None:
        prompt_sent = source_text
        mapping: Any = {}
    else:
        masked = mask_with_policy(source_text, policy=policy)
        prompt_sent = masked.masked_text
        mapping = masked.mapping

    raw_response = model.generate(instruction, prompt_sent)
    final_response = unmask(raw_response, mapping)
    return ConditionResult(
        condition=condition,
        prompt_sent=prompt_sent,
        raw_response=raw_response,
        final_response=final_response,
        had_leak=bool(_LEAK_RE.search(final_response)),
    )
