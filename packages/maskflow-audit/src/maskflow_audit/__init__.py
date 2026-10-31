"""maskflow-audit: find and prove unmasked LLM egress paths in a codebase.

`maskflow scan` answers a retrospective question -- what PII is already
sitting in my logs. This package answers the forward one: **where in this
source tree does text leave for an LLM provider, and is that path masked?**

The promise is "proven, not guessed", which sets the shape of everything
here: a finding is either a static trace (honest about its confidence, and
allowed to answer `unknown`) or -- from M2 -- an observed canary escape with
the Python call stack captured at send time. The LLM is never in the
detection path; discovery and classification are pure, offline and
deterministic, so the same tree always yields the same report and a CI gate
can be trusted.

Module map:
  sinks/registry.yaml   every known egress sink, as data -- a contributor
                        adds one by editing YAML, never by touching code
  sinks/loader.py       parse + validate that registry (collects every
                        problem before raising, like core's config schema)
  discovery/symbols.py  per-module symbol table: import aliases, names
                        bound to constructed clients, self.x attributes
  discovery/walk.py     the ast pass -- resolves call targets against the
                        symbol table and yields SinkHit per egress call
  discovery/flows.py    the Flow model + stable, non-line-based flow IDs
  discovery/masking.py  masked-via-mask()/gateway/integration vs unmasked
  trace/backward.py     intra-procedural backward trace: sink argument ->
                        the DB column, request field or file it came from
  report/summary.py     AuditSummary -- the PII-free, versioned data model
                        every renderer reads from, and nothing else
  report/json_out.py    audit.json
  api.py                run_audit(): the one entry point the CLI calls

Nothing in this package imports a provider SDK. It reads source text with
`ast` and never executes it.
"""

from __future__ import annotations

# Both packs register PERSON_NAME and the LAST registration wins for its
# context keywords and spaCy mapping (pack-india extends pack-intl's; the
# reverse order silently drops pack-india's). Same ordering, and the same
# isort: split guard, as maskflow_cli/app.py.
import maskflow_pack_intl  # noqa: F401 -- import side effect registers pack-intl's entity types

# isort: split
# pack-india ships no py.typed yet, so --strict needs the ignore -- same
# inline form maskflow-agent's doctor.py uses for its checksums import.
import maskflow_pack_india  # type: ignore[import-untyped]  # noqa: F401 -- registers entity types

__version__ = "0.1.0"

__all__ = ["__version__"]
