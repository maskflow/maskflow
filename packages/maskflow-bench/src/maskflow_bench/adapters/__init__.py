"""Just the one adapter this package owns (`maskflow_adapter.MaskflowAdapter`)
plus the `Adapter` protocol (`base.Adapter`) it implements. The other five
competitor adapters (Presidio, mask-privacy, naive regex, an LLM judge)
stay in bench/indiapii/harness/adapters/ -- they pull heavy, optional
third-party dependencies (presidio-analyzer, mask-privacy, anthropic) this
package never needs, and they are only ever used by the dev-only
multi-adapter comparison harness, never by `maskflow bench --my-data`.
"""

from __future__ import annotations

from .base import Adapter, AdapterEntry
from .maskflow_adapter import MaskflowAdapter

__all__ = ["Adapter", "AdapterEntry", "MaskflowAdapter"]
