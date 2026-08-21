# Configuration (`.maskflowrc`)

`maskflow-cli` reads a `.maskflowrc` file to configure entity thresholds,
strategies, custom entity patterns, and exclusions declaratively, instead
of hand-building a `MaskPolicy`/`ResolveConfig` in Python.

> **Scope note:** this release ships the config file format, the
> precedence/validation engine, and `maskflow config validate`/`show`.
> `mask()`/`mask_and_call()`/`session()` do not read `.maskflowrc` yet —
> that wiring is planned as a follow-up.

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

TOML is primary (an extensionless `.maskflowrc` is always parsed as TOML).
YAML (`.maskflowrc.yaml`/`.yml`) and JSON (`.maskflowrc.json`) are also
accepted, with the same schema.

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
./.maskflowrc:11: entities.PAN.threshod - Extra inputs are not permitted (did you mean 'threshold'?)
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
3. **A size cap at match time** (`maskflow_cli.config.redos.safe_match()`),
   independent of the above two, for whatever eventually runs these
   patterns against real text.

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
- Adding it as a hard dependency of `maskflow-cli` widens this package's
  install footprint for a guarantee the static-check + timeout-probe
  combination already covers for the patterns MaskFlow actually expects
  (bounded custom-entity regex, not arbitrary user-submitted regex at
  scale).

The recommendation is to ship `google-re2` support later as an **opt-in**
`--engine=re2` validation mode (reject at `validate` time whatever re2
can't compile, rather than silently falling back), so users who want the
stronger guarantee can opt in without every existing `.maskflowrc`
breaking on upgrade.
