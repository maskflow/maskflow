"""Duck-typed stand-ins for LiteLLM's response objects, so the
provider-agnostic modules can be tested without importing ``litellm``."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def message(
    content: Any = None, tool_calls: list[Any] | None = None, **extra: Any
) -> SimpleNamespace:
    return SimpleNamespace(content=content, tool_calls=tool_calls, **extra)


def choice(msg: SimpleNamespace, index: int = 0) -> SimpleNamespace:
    return SimpleNamespace(index=index, message=msg)


def model_response(*choices: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(choices=list(choices))


def tool_call(name: str, arguments: str, index: int = 0) -> SimpleNamespace:
    return SimpleNamespace(index=index, function=SimpleNamespace(name=name, arguments=arguments))


# -- streaming chunks -------------------------------------------------------
def delta(content: Any = None, tool_calls: list[Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def stream_choice(
    d: SimpleNamespace, index: int = 0, finish_reason: str | None = None
) -> SimpleNamespace:
    return SimpleNamespace(index=index, delta=d, finish_reason=finish_reason)


def stream_chunk(*choices: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(choices=list(choices))


async def aiter(items: list[Any]) -> Any:
    for item in items:
        yield item
