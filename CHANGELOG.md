# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
for each published package (`maskflow-core`, `maskflow-pack-intl`, `maskflow-sdk`,
`@maskflow/detection`).

## [Unreleased]

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
