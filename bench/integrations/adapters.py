"""One adapter per integration. Each exposes:

    available() -> (bool, reason)
    run(text)  -> MaskRun(masked_text, pairs, roundtrip)

`pairs` is the set of `(entity_type, original_value)` the integration
masked; `roundtrip` is the integration's OWN unmask of `masked_text`. The
harness compares every adapter's `pairs` to `core`'s and checks
`roundtrip == text`.

The integrations' framework-free masking layers are used where they exist
(`maskflow_litellm._masking`, `maskflow_llamaindex._masking`,
`maskflow_mcp._masking` carry no framework import); LangChain uses the real
`MaskflowReversibleAnonymizer` (needs `langchain_core`, present in the
bench CI leg).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"<([A-Z][A-Z0-9_]*?)_\d+(?:_[0-9a-f]+)?>")


@dataclass
class MaskRun:
    masked_text: str
    token_map: dict[str, str]  # {'<PAN_1>': 'ABCPE1234F'}
    roundtrip: str  # the integration's OWN unmask of masked_text

    @property
    def pairs(self) -> frozenset[tuple[str, str]]:
        """`{('PAN', 'ABCPE1234F'), ...}` -- identity is (type, value), not
        the token name, so `<PAN_1>` vs `<PAN_3>` across integrations is fine."""
        out: set[tuple[str, str]] = set()
        for token, value in self.token_map.items():
            m = _TOKEN_RE.fullmatch(token)
            if m:
                out.add((m.group(1), value))
        return frozenset(out)


# --------------------------------------------------------------------------


class CoreAdapter:
    name = "core"

    def available(self) -> tuple[bool, str]:
        return True, ""

    def run(self, text: str) -> MaskRun:
        import maskflow

        result = maskflow.mask(text)
        token_map = dict(result.mapping)
        return MaskRun(
            masked_text=result.masked_text,
            token_map=token_map,
            roundtrip=maskflow.unmask(result.masked_text, result.mapping),
        )


class LiteLLMAdapter:
    name = "litellm"

    def available(self) -> tuple[bool, str]:
        try:
            import maskflow_litellm._masking  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            return False, f"maskflow-litellm not importable ({exc})"
        return True, ""

    def run(self, text: str) -> MaskRun:
        from maskflow import Session
        from maskflow_litellm._masking import mask_request_data, unmask_model_response

        with Session(ttl_seconds=None) as session:
            data = {"messages": [{"role": "user", "content": text}]}
            mask_request_data(session, data)
            masked = data["messages"][0]["content"]
            token_map = {tok: session.mapping[tok].original for tok in session.mapping}
            response = _FakeResponse(masked)
            unmask_model_response(session, response)
            return MaskRun(masked, token_map, response.choices[0].message.content)


class LangChainAdapter:
    name = "langchain"

    def available(self) -> tuple[bool, str]:
        try:
            import langchain_core  # noqa: F401
            from maskflow_langchain import MaskflowReversibleAnonymizer  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            return False, f"maskflow-langchain / langchain_core not importable ({exc})"
        return True, ""

    def run(self, text: str) -> MaskRun:
        from maskflow_langchain import MaskflowReversibleAnonymizer

        anon = MaskflowReversibleAnonymizer()
        masked = anon.anonymize(text)
        token_map = {
            token: value
            for inner in anon.deanonymizer_mapping.values()
            for token, value in inner.items()
        }
        return MaskRun(masked, token_map, anon.deanonymize(masked))


class LlamaIndexAdapter:
    name = "llamaindex"

    def available(self) -> tuple[bool, str]:
        try:
            import maskflow_llamaindex._masking  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            return False, f"maskflow-llamaindex not importable ({exc})"
        return True, ""

    def run(self, text: str) -> MaskRun:
        from maskflow.streaming import unmask_whole
        from maskflow_llamaindex._masking import mask_pii

        masked, mapping = mask_pii(text)
        return MaskRun(masked, dict(mapping), unmask_whole(masked, mapping))


class McpAdapter:
    name = "mcp"

    def available(self) -> tuple[bool, str]:
        try:
            import maskflow_mcp._masking  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            return False, f"maskflow-mcp not importable ({exc})"
        return True, ""

    def run(self, text: str) -> MaskRun:
        from maskflow import Session
        from maskflow_mcp._masking import mask_arguments, unmask_json

        with Session(ttl_seconds=None) as session:
            masked_args = mask_arguments(session, {"content": text})
            masked = masked_args["content"]
            token_map = {tok: session.mapping[tok].original for tok in session.mapping}
            roundtrip = unmask_json(session, masked_args)["content"]
            return MaskRun(masked, token_map, roundtrip)


# --- minimal litellm ModelResponse duck-type (no litellm import) -----------


class _FakeFn:
    def __init__(self, arguments: str) -> None:
        self.arguments = arguments


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content
        self.tool_calls: list = []


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


ALL_ADAPTERS = (
    CoreAdapter(),
    LiteLLMAdapter(),
    LangChainAdapter(),
    LlamaIndexAdapter(),
    McpAdapter(),
)
