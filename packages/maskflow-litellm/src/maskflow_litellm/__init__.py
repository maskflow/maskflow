"""MaskFlow guardrail for LiteLLM.

Point a ``config.yaml`` guardrail at ``maskflow_litellm.MaskflowGuardrail``
(see that class's docstring).

``MaskflowGuardrail`` and ``initialize_guardrail`` are imported lazily: they
pull in ``litellm``, which is a peer dependency (the proxy provides it), so
importing this package does not require it. The provider-agnostic
submodules (``_masking``, ``_streaming``, ``_sessions``) import cleanly on
their own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["MaskflowGuardrail", "initialize_guardrail"]

if TYPE_CHECKING:
    from litellm.integrations.custom_guardrail import CustomGuardrail

    from .guardrail import MaskflowGuardrail


def __getattr__(name: str) -> Any:
    if name == "MaskflowGuardrail":
        from .guardrail import MaskflowGuardrail

        return MaskflowGuardrail
    if name == "initialize_guardrail":
        return _initialize_guardrail
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _initialize_guardrail(litellm_params: Any, guardrail: Any) -> CustomGuardrail:
    """Entry point for LiteLLM's guardrail initializer registry (used only if
    ``maskflow`` is registered as a first-class integration; the
    ``guardrail: maskflow_litellm.MaskflowGuardrail`` class path does not
    need this)."""
    import litellm

    from .guardrail import MaskflowGuardrail

    extra = (
        litellm_params.model_dump(exclude_none=True)
        if hasattr(litellm_params, "model_dump")
        else dict(litellm_params or {})
    )
    for key in ("guardrail", "mode", "default_on"):
        extra.pop(key, None)

    callback = MaskflowGuardrail(
        guardrail_name=guardrail.get("guardrail_name", ""),
        event_hook=getattr(litellm_params, "mode", None),
        default_on=getattr(litellm_params, "default_on", False),
        **extra,
    )
    litellm.logging_callback_manager.add_litellm_callback(callback)
    return callback
