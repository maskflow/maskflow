# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
for each published package (`maskflow-core`, `maskflow-sdk`, `@maskflow/detection`).

## [Unreleased]

### Fixed

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

## [0.1.0] - 2026-08-06

### Added

- `maskflow-core`: PII detection and reversible masking engine. Three-layer detection pipeline
  (regex + structural validation, keyword-context confidence boosting, spaCy NER) covering 12 PII
  types: email, phone, SSN, credit card, IPv4/IPv6, AWS access key, API key/generic secret, JWT,
  IBAN, street address, person name, date of birth.
- `maskflow-sdk`: Python SDK built on `maskflow-core`, with `mask_and_call` for masking a prompt,
  calling any LLM, and unmasking the response.
- `@maskflow/detection`: TypeScript port of the regex/structural detection layer.

[unreleased]: https://github.com/maskflow/maskflow/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/maskflow/maskflow/releases/tag/v0.1.0
