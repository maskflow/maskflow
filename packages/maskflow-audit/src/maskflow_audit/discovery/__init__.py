"""Static discovery: source tree -> flow inventory.

symbols.py resolves a call target to a dotted path, walk.py finds the calls
the registry knows about, flows.py gives each one a stable identity, and
masking.py decides whether that path is guarded.
"""

from __future__ import annotations
