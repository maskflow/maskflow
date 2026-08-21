# Configuration (`.maskflowrc`)

A `.maskflowrc` file configures entity thresholds, strategies, custom
entity patterns, and exclusions declaratively, instead of hand-building a
`MaskPolicy`/`ResolveConfig` in Python. The config engine
(`maskflow_core.config`: schema, discovery, precedence/merge, validation,
and compiling a resolved config into detection/masking primitives) lives
in `maskflow-core` itself, since core is what actually consumes it.
`maskflow-cli` builds `maskflow config validate`/`show` on top of it, and
`maskflow-sdk`'s `mask()`/`mask_and_call()`/`session()` all read it
automatically -- see "SDK wiring" below.

## Schema

```toml
[maskflow]
packs = ["india"]
default_strategy = "replace"   # one of: replace, redact, mask, hash, surrogate

[entities.AADHAAR]
enabled = true
threshold = 0.6                # 0.0-1.0
strategy = "mask"               # overrides maskflow.default_strategy for this entity

[custom.EMPLOYEE_ID]
pattern = '\bEMP-\d{6}\b'
score = 0.9                     # 0.0-1.0, base confidence for a match
context = ["employee"]          # optional context keywords (see maskflow_core.context)

[exclusions]
values = ["test@example.com"]   # literal values never flagged as PII
patterns = ['\bDEMO-\d+\b']     # regex; a match is never flagged
```

TOML is primary (an extensionless `.maskflowrc` is always parsed as TOML,
using stdlib `tomllib` on 3.11+ or the `tomli` dependency on the 3.10
floor -- always available, no extra needed). JSON (`.maskflowrc.json`) is
also always available. YAML (`.maskflowrc.yaml`/`.yml`) needs the optional
`maskflow-core[yaml]` extra -- most users will never write YAML config, so
`pyyaml` is only imported when a YAML file is actually read, and a bare
install raises a clear "install maskflow-core[yaml]" error if it finds one
without that extra.

Every table uses strict validation: an unknown key is a hard error with a
did-you-mean suggestion, not a silently-ignored typo. `[entities.<NAME>]`/
`[custom.<NAME>]` keys must be `UPPER_SNAKE` (e.g. `AADHAAR`,
`EMPLOYEE_ID`). `entities.*.threshold`/`entities.*.strategy` default to
`null`/unset, meaning "inherit `maskflow.default_strategy`" — distinct from
explicitly repeating the default value.

`maskflow config validate` also does a **soft** cross-check: it prints a
`WARNING` (never a hard failure) for any `entities`/`custom` name that
doesn't match a currently-installed pack's registered entity type, since
the pack that would provide it (e.g. `maskflow-pack-india`) may simply not
be installed — that's expected, not a config bug.

## Precedence

Lowest to highest:

1. **Schema defaults**
2. **User file** — `~/.config/maskflow/config.toml` (or `.yaml`/`.yml`/`.json`)
3. **Project file** — discovered by walking up from the current directory:
   `.maskflowrc`, `.maskflowrc.toml`, `.maskflowrc.yaml`, `.maskflowrc.yml`,
   `.maskflowrc.json`, first match wins per directory. The walk stops after
   checking a directory containing `.git` (the repo root) and never
   searches `$HOME` itself — that's the user file's territory. Pass
   `--config PATH` to use an explicit file instead of discovery.
4. **Environment variables** — prefix `MASKFLOW_`, `__` as the nesting
   separator, matching the schema's own field names:
   `MASKFLOW_DEFAULT_STRATEGY`, `MASKFLOW_PACKS` (JSON array or bare
   comma-list), `MASKFLOW_ENTITIES__AADHAAR__THRESHOLD`,
   `MASKFLOW_EXCLUSIONS__VALUES`. `MASKFLOW_HASH_KEY`/`MASKFLOW_MAPPING_KEY`
   (existing envs, unrelated to this config) are never swept in. Any other
   unrecognized `MASKFLOW_*` variable is a hard error, same as an unknown
   file key.
5. **CLI `--set`** — repeatable, e.g. `--set entities.AADHAAR.threshold=0.7`.
   The value is parsed as JSON first (covers numbers/bools/lists/null),
   falling back to a bare comma-list, then a raw string.

A higher-precedence source overriding one field of an entity (e.g. just
`threshold`) never erases sibling fields set by a lower-precedence source
(e.g. `strategy`) — merging happens field-by-field. List-valued fields
(`packs`, `exclusions.values`, `exclusions.patterns`, `context`) are
**whole-list replace**, not append, across precedence levels.

## Commands

```
maskflow config validate [--config PATH] [--set KEY=VALUE ...]
maskflow config show [--resolved] [--config PATH] [--set KEY=VALUE ...]
```

`validate` reports every problem found in one pass (not just the first),
each annotated with its file and line number when known, e.g.:

```
./.maskflowrc:11: entities.PAN.threshod - unknown key (did you mean 'threshold'?)
```

`show` prints the merged, validated config as plain TOML. `show --resolved`
instead prints one line per field, annotated with where the value came
from:

```
entities.AADHAAR.threshold = 0.6   (project file: ./.maskflowrc:8)
entities.PAN.threshold     = 0.5   (default)
```

Both commands **redact `exclusions.values`** in all output (masked to
first/last character) — those are free-form user text that could itself be
PII-shaped, and CLAUDE.md's rule against printing PII applies to config
output too.

## SDK wiring

`maskflow.mask()`, `maskflow.mask_and_call()`, and
`maskflow.session()`/`async_session()` all read `.maskflowrc`
automatically — no extra step needed. A resolved config can change:

- **which entities are detected** — `entities.*.threshold`,
  `entities.*.enabled`, `custom.*` (adds a brand-new entity type),
  `exclusions.*`
- **how a match is substituted** — `maskflow.default_strategy`,
  `entities.*.strategy` (replace/redact/mask/hash/surrogate)

```python
import maskflow

# Uses whatever .maskflowrc is discovered (or none -- all defaults).
result = maskflow.mask("Reach me at alice@example.com.")

# Bypasses discovery entirely for this call.
from maskflow_core.config import RootConfig, EntityConfig
from maskflow_core.strategies import Strategy

result = maskflow.mask(
    "Reach me at alice@example.com.",
    config=RootConfig(entities={"EMAIL": EntityConfig(strategy=Strategy.MASK)}),
)
```

A `RootConfig` built this way is **not** re-validated — no did-you-mean,
type checking, or ReDoS check runs, since those live in
`maskflow_core.config.schema.validate_root_config()`, which only the
file/env/CLI discovery path calls. This is the same trust boundary
`register_pattern()` has always had for pack authors: code you wrote and
are passing directly to `config=` is trusted the way any other Python call
is, not re-validated as if it were untrusted external text. A `.maskflowrc`
file is the untrusted side of that boundary, and gets full validation.

Discovery runs **once per process**, lazily, and is cached — a
long-running server doesn't re-stat the filesystem on every call. Call
`maskflow.reload_config()` to force a fresh discovery (e.g. after
deploying a new `.maskflowrc`); an already-open `Session` keeps whatever
config it compiled when it was constructed, since a session is meant to
behave consistently for its whole lifetime — only new `mask()`/
`mask_and_call()` calls and newly-opened sessions see the reload.

**Hard guarantee: with no `.maskflowrc` anywhere and no `config=` passed,
output is byte-identical to `.maskflowrc` never having existed** — config
only ever *adds* behavior, never silently changes the default. This is
proven with a 10,000-example property test (`maskflow-core/tests/
test_masking.py::test_mask_with_policy_default_matches_mask`), not just
asserted.

Two scope boundaries worth knowing:

- `maskflow.mask()`'s return type (`MaskResult`, a plain `{token:
  original}` dict) predates config. A redact/mask/hash substitution isn't
  reversible, so it's simply **omitted** from that dict rather than
  requiring a type change — `unmask()` only touches tokens present in it,
  so this is safe and type-compatible with existing callers.
- `Session.mask_json()`'s numeric leaves always use the numeric-surrogate
  scheme (a same-digit-count fake int), regardless of a configured
  strategy — swapping a JSON int leaf for a string would break
  `mask_json()`'s documented "leaf's JSON type never changes" invariant.
  Threshold/enabled/custom/exclusions still apply to numeric leaves; only
  the *substitution* is fixed.

## Regex safety (ReDoS)

`custom.<NAME>.pattern` and every `exclusions.patterns` entry are
untrusted, user-supplied regex. Before being accepted, each pattern goes
through:

1. **A static shape check** for the classic catastrophic-backtracking
   causes — a group containing an unbounded quantifier (`+`, `*`, `{n,}`)
   that is itself unbounded-quantified (`(a+)+`, `(a*)*`), or a group
   containing alternation that is itself unbounded-quantified (`(a|ab)*`).
   This is **intentionally conservative**: it's a shape heuristic, not a
   sound or complete analysis, so it will occasionally reject a safe
   pattern that happens to share the shape. Rejections explain the rule
   that fired and suggest a bounded rewrite (e.g. `{1,20}` instead of `+`).
2. **An adversarial timing probe** — the compiled pattern is run against
   several generated pathological inputs at a few lengths, each under a
   hard per-probe timeout in a child process (not the main process, so a
   genuine hang gets killed rather than wedging the CLI).
3. **A size cap at match time.** `maskflow_core.config.redos.safe_match()`
   is the sanctioned way to run one of these patterns against arbitrary
   text; `detect()` doesn't call it directly (core's detection code stays
   independent of the config subpackage -- config depends on detection's
   types, never the reverse), but applies the equivalent cap itself when
   matching `[exclusions].patterns` against a candidate span's text.
   `[custom.*].pattern` matches carry no additional per-call cap beyond
   the regex engine itself, same as every built-in pack-provided pattern
   -- the safety guarantee comes from bounding which pattern *shapes* are
   accepted at config-validation time (steps 1-2), not from capping input
   length on every match.

### Why not `google-re2`?

`google-re2` guarantees linear-time matching (no catastrophic
backtracking, by construction), which sounds like a better fit than a
heuristic static check + timing probe. It isn't adopted in this release
because:

- It's a genuinely different regex dialect: **no backreferences and no
  lookaround** (`(?=...)`, `(?!...)`, `(?<=...)`). A user's otherwise
  reasonable custom pattern could stop compiling on upgrade, silently or
  loudly depending on how the switch is done — not something to introduce
  as a default without a major-version-level heads up.
- Adding it as a dependency of `maskflow-core` widens the footprint of
  every install (not just ones that touch `.maskflowrc`) for a guarantee
  the static-check + timeout-probe combination already covers for the
  patterns MaskFlow actually expects (bounded custom-entity regex, not
  arbitrary user-submitted regex at scale).

The recommendation is to ship `google-re2` support later as an **opt-in**
`--engine=re2` validation mode (reject at `validate` time whatever re2
can't compile, rather than silently falling back), so users who want the
stronger guarantee can opt in without every existing `.maskflowrc`
breaking on upgrade.
