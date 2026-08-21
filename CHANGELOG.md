# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
for each published package (`maskflow-core`, `maskflow-pack-intl`, `maskflow-sdk`,
`@maskflow/detection`).

## [Unreleased]

### Added

- `maskflow-core`: `.maskflowrc` configuration file support --
  `maskflow_core.config`, TOML (primary, stdlib `tomllib`/`tomli`), YAML
  (optional `maskflow-core[yaml]` extra), and JSON. Config resolves
  through five precedence levels (schema defaults < user file
  `~/.config/maskflow/config.toml` < project file, discovered by walking up
  from cwd and stopping at the repo root < environment variables
  (`MASKFLOW_*`) < CLI `--set`/`--config`), tracking per-field provenance.
  Validation (hand-rolled dataclasses + validators -- no pydantic, to keep
  core's footprint essentially unchanged) rejects unknown keys with a
  did-you-mean suggestion (`entities.PAN.threshod` -> "did you mean
  'threshold'?") and reports every problem found in one pass, annotated
  with file:line when known. User-supplied regex (`custom.<NAME>.pattern`,
  `exclusions.patterns`) goes through a ReDoS safety check (static shape
  check + timeboxed adversarial probe) before being accepted. See
  `docs/configuration.md` for the full schema and precedence reference.
- `maskflow-core`: `detect()` and `mask_with_policy()` gain five
  keyword-only params (`per_entity_threshold`, `disabled_types`,
  `extra_patterns`, `exclusion_values`, `exclusion_patterns`) -- how
  resolved `.maskflowrc` config reaches detection/masking
  (`maskflow_core.config.engine.compile_config()`). Every one defaults to
  "no effect", so existing calls are unmodified both in output and in the
  code path they run; `maskflow_core.masking.mask()` itself is untouched.
  Also exports `surrogate_substitute` (renamed from the former private
  `_surrogate_substitute`, no behavior change).
- `maskflow-cli` (new package, 0.1.0): `maskflow config validate` and
  `maskflow config show [--resolved]`, built on `maskflow_core.config`.
  `exclusions.values` is redacted in all CLI output.
- `maskflow-core`/`maskflow-pack-intl`: added `py.typed` markers (PEP 561)
  so downstream packages can be type-checked against them without
  `ignore_missing_imports` -- no behavior change.
- `maskflow-sdk`: `mask()`, `mask_and_call()`, `session()`/`async_session()`
  all gain an optional `config=` parameter (a `maskflow_core.config.
  RootConfig`) that changes which entities are detected
  (threshold/enabled/custom patterns/exclusions) and how they're
  substituted (strategy: replace/redact/mask/hash/surrogate).
  `config=None` (the default) uses the ambient `.maskflowrc` discovered
  from the filesystem, cached once per process -- a long-running server
  doesn't re-stat the filesystem on every call; `maskflow.reload_config()`
  forces a fresh discovery. Passing `config=` explicitly bypasses
  discovery entirely, for a library embedded in someone else's
  application. **With no `.maskflowrc` anywhere and no `config=` passed,
  output is byte-identical to before this change** -- proven with a
  10,000-example hypothesis property test
  (`maskflow-core/tests/test_masking.py::
  test_mask_with_policy_default_matches_mask`) asserting
  `mask_with_policy(text, MaskPolicy())` is byte-identical to `mask(text)`
  for arbitrary text and threshold, which is what the config-aware
  `mask()` wrapper delegates to. Non-reversible substitutions
  (redact/mask/hash) are simply omitted from `MaskResult.mapping` rather
  than requiring a type change. `Session` compiles its config once at
  construction (not per call); numeric `mask_json()` leaves keep their
  numeric-surrogate scheme regardless of configured strategy, preserving
  the documented "leaf's JSON type never changes" invariant.
- `maskflow-sdk`: `maskflow.session()` / `maskflow.async_session()` --
  session-scoped masking for multi-turn/multi-tool-call agents. Unlike
  `mask()` (counters and value->token identity reset every call), a
  `Session` keeps that identity stable for its whole lifetime, so the same
  PII value always gets the same `<TYPE_n>` token across separate
  `.mask()`/`.mask_json()` calls instead of each call independently
  restarting its own numbering (see `docs/agent-sessions.md` for the
  concrete before/after). `Session.mask_json()` walks a nested
  dict/list/tuple structure, masking string leaf *values* only -- dict keys
  are never touched, and a PII-shaped integer leaf is replaced with a
  same-digit-count integer surrogate rather than a schema-breaking string,
  so a masked tool-call payload keeps its original JSON shape. Sessions are
  closeable (`with maskflow.session() as s: ...`, or `s.close()`) and
  TTL-bounded (`ttl_seconds`, default 3600); either purges the mapping, and
  any further call raises the new `SessionClosedError` instead of silently
  no-op'ing. `AsyncSession`/`async_session()` wrap the same `Session` via
  `asyncio.to_thread` with no changes to core. Neither `Session` nor
  `AsyncSession` is thread-safe -- documented explicitly rather than
  silently assumed. No change to `mask()`/`unmask()`/`mask_and_call()`.

### Fixed

- `maskflow-core`: `pytest -m leak` run on its own used to deselect every
  test except the leak-gate assertion itself, so `LEAK_POOL` -- filled only
  by whatever ran earlier in the same process -- stayed empty and the gate
  passed trivially even with an active PII leak elsewhere in the code
  (verified: adding a deliberate `logger.debug(span.text)` to a recognizer
  and running `pytest -m leak` alone did not fail). `pytest_configure` in
  `maskflow_core.testing` now neutralizes any `-m`/markexpr mentioning
  "leak" so the whole session still runs -- the marker is for ordering
  (leak-gate test runs last) and identification, not selection.

### Changed

- `maskflow-core` / `maskflow-sdk` / `maskflow-pack-intl`: raised the minimum
  supported Python from 3.9 to 3.10 (`requires-python = ">=3.10"`). Python
  3.9 reached upstream end-of-life on 2025-10-05 and no longer receives
  security patches; it was also the direct cause of CI's slowest jobs
  (~15 min) -- spaCy's `blis` dependency has no prebuilt wheel for 3.9 on
  several platforms, forcing a from-source build every run. `ci.yml`'s test
  matrix drops 3.9 (and the Windows+3.9 exclude workaround it needed) in
  favor of 3.10/3.11/3.13; `ruff`'s `target-version` and ambient code style
  move to `py310` accordingly (e.g. `Union[X, Y]` -> `X | Y`, `zip()` calls
  now specify `strict=` explicitly, newly enforceable now that all
  supported versions have it).

### Added

- `maskflow-core`: `mask_with_policy(text, policy, min_confidence)` alongside
  the untouched `mask()`/`unmask()`/`mask_and_call()` (`maskflow-sdk`'s
  0.1.0 API is unchanged -- new capability lives entirely in new functions).
  Five substitution strategies, selected per entity type via
  `MaskPolicy(default_strategy, per_entity_strategy)`: `REPLACE` (the
  existing typed-placeholder behavior), `REDACT` (constant
  `[REDACTED_TYPE]` marker), `MASK` (partial reveal, e.g. `XXXX XXXX 9012`,
  configurable via `MaskConfig`), `HASH` (HMAC-SHA256, stable per value,
  keyed via `HashConfig` or `MASKFLOW_HASH_KEY`), and `SURROGATE` (a
  plausible fake of the same type, via `register_surrogate_generator()`;
  falls back to `REPLACE` for any type with no registered generator).
  `REPLACE`/`SURROGATE` are reversible via the same `unmask()`; `REDACT`/
  `MASK`/`HASH` are intentionally one-way. `mask_with_policy()` returns a
  `PolicyMaskResult` whose mapping is a `Mapping` (token -> `MappingEntry`),
  not a plain dict -- `MappingEntry.original` is repr-excluded like
  `Span.text` (rule 1).
- `maskflow-core`: `MappingStore` protocol plus `InMemoryMappingStore`
  (TTL-expiring, process-local, the default), `EncryptedFileMappingStore`
  (AES-GCM at rest, key from `MASKFLOW_MAPPING_KEY` or passed explicitly --
  requires the new optional `maskflow-core[store]` extra), and
  `RedisMappingStore` (interface-only stub this round -- every method
  raises `NotImplementedError`). Masking itself stays pure/stateless; a
  `MappingStore` is an opt-in way for a caller to persist a `Mapping`
  across requests/processes.
- `maskflow-core`: 10,000-example Hypothesis property test
  (`unmask(mask(t).masked_text, mapping) == t` for arbitrary `st.text()`)
  plus explicit empty-string/index-0/final-index/combining-character cases,
  proving CLAUDE.md's "round-trip sacred" guarantee (rule 5) rather than
  just asserting it. Offsets are documented as Python `str` code-point
  offsets throughout (`detect()`/`mask()`/`mask_with_policy()`), not byte
  offsets -- consistent, and safe for non-ASCII PII.
- `maskflow-core` / `maskflow-pack-intl`: whole-session leak gate
  (`maskflow_core.testing`, `pytest -m leak`) -- captures every log record
  and exception raised during a package's test session and asserts none of
  its known PII fixture values ever appeared in either, in addition to the
  existing per-class repr checks. Runs as part of each package's normal
  `pytest` step in CI (the marker doesn't exclude, so no separate CI job
  was needed).
- `maskflow-pack-intl`: `Strategy.SURROGATE` generators for EMAIL, PHONE,
  SSN, CREDIT_CARD, IBAN, PERSON_NAME, and ADDRESS, each drawing from a
  documented reserved/invalid range or embedded synthetic corpus (see the
  package README's surrogate table) so a generated value never collides
  with something a real issuer could plausibly assign.

### Changed

- `maskflow-core`: `mask()` now reuses the same `<TYPE_n>` token for a
  repeated identical PII value within one call, instead of minting a new
  numbered token for every occurrence (CLAUDE.md design decision #3,
  "same value -> same token per session"). Round-trip behavior is
  unaffected either way (`str.replace()` already restores every occurrence
  of a token); output for text with no repeated values is unchanged.
- `maskflow-core`: replaced the ad hoc per-recognizer overlap merge with a
  central `SpanSet.resolve(config)` pipeline (`maskflow_core.spanset`).
  `Finding` is renamed `Span` (`type`/`value` fields renamed
  `entity_type`/`text`); every span now also carries `recognizer` and an
  `explanation` trail. Overlap resolution supports a configurable per-entity
  policy -- `STRICT` (default, no overlaps survive), `CONTAINED` (a more
  specific nested span wins over a same-status containing one), `MERGE`
  (adjacent same-type spans separated by whitespace/a punctuation character
  join into one) -- while the existing invariant is unchanged: a
  checksum-validated span never loses to an overlapping unvalidated one.
  Detection now runs a tier-0 excision pass -- confidently-resolved regex
  spans are blanked out (same-length filler, so char offsets are preserved)
  before the NER pass runs over the remainder, rather than NER scanning raw
  PII text. No change to `mask()`/`unmask()`/`mask_and_call()` signatures or
  behavior. `maskflow-sdk` and `maskflow-pack-intl` updated accordingly
  (`Finding` -> `Span` in `maskflow-sdk`'s exports too).

## [sdk 0.1.1] - 2026-08-20

### Changed

- `maskflow-sdk`: now depends on `maskflow-core>=0.2.0,<0.3` and
  `maskflow-pack-intl>=0.1.0,<0.2` (previously `maskflow-core>=0.1.0,<0.2` with
  recognizers bundled directly into core). No public API change --
  `mask()`/`unmask()`/`mask_and_call()` are identical -- this just moves
  `pip install maskflow-sdk` onto the split core/pack-intl architecture
  published in `core 0.2.0, pack-intl 0.1.0` below.

## [core 0.2.0, pack-intl 0.1.0] - 2026-08-19

### Changed

- **Workspace restructure**: the repo is now a real [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/)
  rooted at `pyproject.toml`, with members under `packages/*` and `packs/*`. `core/` moved to
  `packages/maskflow-core`, `sdk/python/` moved to `packages/maskflow-sdk`, and
  `packages/detection/` moved to `packages/maskflow-js` (npm package name unchanged --
  still publishes as `@maskflow/detection`). No published-artifact behavior changes; import
  paths (`from maskflow_core import ...`, `from maskflow import ...`) are unaffected.
- `maskflow-core` no longer ships any recognizers -- `patterns.py` and the PERSON_NAME/
  DATE_OF_BIRTH NER logic moved to a new package, **`maskflow-pack-intl`**, which registers
  all 12 original types (email, phone, SSN, credit card, IP, AWS/API keys, JWT, IBAN, address,
  person name, date of birth) against core on import. `maskflow-sdk` now depends on
  `maskflow-pack-intl` automatically, so `pip install maskflow-sdk` behaves identically to
  before -- this only matters for code importing `maskflow_core` directly without a pack.
- `maskflow-core`: `registry.py` gained `register_ner_recognizer()` alongside the existing
  `register_pattern()`, so spaCy-label-based recognizers (like PERSON_NAME/DATE_OF_BIRTH) are
  now pack content too, registered the same way regex-based ones are. Both registration
  functions accept an optional `context_keywords` argument, replacing the previously-hardcoded
  `CONTEXT_KEYWORDS` table.
- `maskflow-core`: spaCy moved from a required dependency to an optional one
  (`maskflow-core[nlp]`). Without it installed, the NER pass is skipped with a single warning
  and pattern-based recognizers are unaffected.

### Fixed

- `maskflow-core` / `maskflow-pack-intl`: fixed a latent Python 3.9 incompatibility (`X | None`
  return/parameter annotations evaluated eagerly instead of deferred) that would have broken
  on 3.9 the first time CI actually tested that version -- added `from __future__ import
  annotations` to the affected modules.

- `maskflow-core`: `Finding.value` no longer appears in default `repr()`
  output, and test-failure messages no longer interpolate raw sample text or
  matched values -- closes a PII leak surface in test/debug output. Registered
  the `benchmark`/`leak` pytest markers referenced by CLAUDE.md's commands.
- `maskflow-core` / `@maskflow/detection`: bounded the two unbounded `\w*`
  quantifiers in the generic-secret-assignment regex (was O(n^2) on long
  word-runs with no `:`/`=`).

- `maskflow-core` / `@maskflow/detection`: `mask()` now pre-scans input text
  for placeholder-lookalike substrings (e.g. a prompt that already contains
  `<EMAIL_1>`) and falls back to a nonce-suffixed token on collision.

### Added

- `maskflow-core` / `@maskflow/detection`: unicode/emoji/RTL/zero-width
  round-trip test coverage for `mask()`/`unmask()`.
- `maskflow-core` / `@maskflow/detection`: `Finding.validated` -- true when a
  structural validator (Luhn, IBAN mod-97, SSN area-code check) confirmed the
  match. Central overlap resolution now sorts by (validated desc, confidence
  desc, length desc, start asc), so a checksum-validated span always beats an
  overlapping unvalidated one.
- `maskflow-core`: `PIIType` is now an open registry (`PIIType.register(...)`)
  instead of a closed `Enum`, and `register_pattern()` lets a future pack
  (e.g. `maskflow-pack-india`) add new PII types and recognizer rules without
  editing `maskflow-core` itself. Existing built-in types and their `.value`/
  equality/`isinstance` behavior are unchanged.

## [0.1.0] - 2026-08-06

### Added

- `maskflow-core`: PII detection and reversible masking engine. Three-layer detection pipeline
  (regex + structural validation, keyword-context confidence boosting, spaCy NER) covering 12 PII
  types: email, phone, SSN, credit card, IPv4/IPv6, AWS access key, API key/generic secret, JWT,
  IBAN, street address, person name, date of birth.
- `maskflow-sdk`: Python SDK built on `maskflow-core`, with `mask_and_call` for masking a prompt,
  calling any LLM, and unmasking the response.
- `@maskflow/detection`: TypeScript port of the regex/structural detection layer.

[unreleased]: https://github.com/maskflow/maskflow/compare/sdk-py-v0.1.1...HEAD
[sdk 0.1.1]: https://github.com/maskflow/maskflow/compare/sdk-py-v0.1.0...sdk-py-v0.1.1
[core 0.2.0, pack-intl 0.1.0]: https://github.com/maskflow/maskflow/compare/core-v0.1.1...core-v0.2.0
[0.1.0]: https://github.com/maskflow/maskflow/releases/tag/v0.1.0
