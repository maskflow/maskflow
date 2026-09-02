from . import anthropic, openai

PROVIDERS = {"openai": openai, "anthropic": anthropic}

__all__ = ["openai", "anthropic", "PROVIDERS"]
