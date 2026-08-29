"""Adapter 6: ask an Anthropic model to extract PII spans as structured
output, via tool-use (not free-text JSON parsing -- forcing a tool call
with an enum-constrained `label` field is far more reliable than asking
the model to emit raw JSON and hoping it's well-formed).

Env-keyed and skippable without a key, per the work order: `available()`
is False with a plain reason when ANTHROPIC_API_KEY isn't set, and the SDK
is never imported unless a key is present (no network calls, no cost, no
crash for anyone running the harness without one). Model is configurable
via MASKFLOW_BENCH_LLM_MODEL -- defaults to a Haiku-tier model since this
adapter's job is to be *a* baseline, not the best possible LLM result, and
scanning a multi-thousand-document corpus with a larger model is a real
cost a benchmark run shouldn't default into silently.

The model is told the corpus's own canonical label vocabulary (see
labels.py) and asked to report literal matched substrings, not raw
character offsets -- LLMs are unreliable at counting characters, so
offsets are recovered afterward via offsets.locate_span() the same way
mask_privacy_adapter.py's Tier-2 NLP findings are. A substring that can't
be located verbatim in the text is dropped and counted as "unlocatable"
rather than guessed at.
"""

from __future__ import annotations

import os
from typing import Any

from ..labels import LABEL_DESCRIPTIONS
from ..offsets import locate_span

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

_TOOL_NAME = "report_pii_findings"


def _build_tool(canonical_labels: tuple[str, ...]) -> dict[str, Any]:
    return {
        "name": _TOOL_NAME,
        "description": "Report every PII span found in the document.",
        "input_schema": {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "value": {
                                "type": "string",
                                "description": "Exact matched substring, copied verbatim.",
                            },
                            "label": {"type": "string", "enum": list(canonical_labels)},
                        },
                        "required": ["value", "label"],
                    },
                }
            },
            "required": ["findings"],
        },
    }


def _build_system_prompt(canonical_labels: tuple[str, ...]) -> str:
    lines = [
        "You are a PII detection system for Indian-context documents.",
        "Find every span in the document matching one of these entity types:",
        "",
    ]
    for label in canonical_labels:
        desc = LABEL_DESCRIPTIONS.get(label, "")
        lines.append(f"- {label}: {desc}" if desc else f"- {label}")
    lines += [
        "",
        "Call report_pii_findings with every match. For `value`, copy the",
        "matched text exactly as it appears in the document -- do not",
        "normalize whitespace, punctuation, or casing. Report each match",
        "once. If nothing matches, call the tool with an empty findings list.",
    ]
    return "\n".join(lines)


class LlmAdapter:
    name = "llm_detector"

    def __init__(self, canonical_labels: tuple[str, ...]) -> None:
        self._canonical_labels = canonical_labels
        self._client: Any = None
        self._model = os.environ.get("MASKFLOW_BENCH_LLM_MODEL", _DEFAULT_MODEL)
        self._unlocatable = 0

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

    def detect(self, text: str) -> list[tuple[int, int, str]]:
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=_build_system_prompt(self._canonical_labels),
            tools=[_build_tool(self._canonical_labels)],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
            messages=[{"role": "user", "content": text}],
        )

        findings: list[dict[str, str]] = []
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == _TOOL_NAME:
                findings = block.input.get("findings", [])
                break

        used_starts: set[int] = set()
        found: list[tuple[int, int, str]] = []
        for item in findings:
            value = item.get("value", "")
            label = item.get("label", "")
            located = locate_span(text, value, used_starts)
            if located is not None:
                found.append((located[0], located[1], label))
            else:
                self._unlocatable += 1
        return found
