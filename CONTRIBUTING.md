# Contributing to MaskFlow

Thanks for considering a contribution. MaskFlow is solo-maintained, so response times can vary,
but every issue and PR gets read.

## Project layout

- [`core/`](core) — `maskflow-core`, the Python detection/masking engine (Python, uv).
- [`sdk/python/`](sdk/python) — `maskflow-sdk`, the Python SDK built on `core` (Python, uv).
- [`packages/detection/`](packages/detection) — `@maskflow/detection`, the TypeScript port of the
  regex/structural detection layer (npm workspace).

## Setup

### Python packages (`core/`, `sdk/python/`)

Requires [uv](https://docs.astral.sh/uv/).

```bash
cd core   # or sdk/python
uv sync --extra dev
uv run python -m spacy download en_core_web_sm
```

### TypeScript package (`packages/detection/`)

From the repo root (it's an npm workspace):

```bash
npm ci
npm run build -w @maskflow/detection
```

## Running tests

```bash
# core
cd core && uv run pytest

# sdk/python
cd sdk/python && uv run pytest

# @maskflow/detection
npm test -w @maskflow/detection
```

CI runs these same commands per package, only on paths that changed (see
`.github/workflows/ci.yml`).

## PR expectations

- Keep changes scoped to one package where possible — it keeps CI fast and review focused.
- Add or update tests for any behavior change, especially detection logic.
- Update `CHANGELOG.md` under `[Unreleased]`.
- If you're touching detection patterns, run the full test suite for that package, not just the
  test you added — regex changes have a way of shifting other matches.

## Reporting false negatives and false positives

These reports are genuinely valuable and you don't need a code fix in hand to file one — a clear
example is enough. Use the issue templates:

- **False negative** — PII that should have been detected/masked but wasn't.
- **False positive** — non-PII that got flagged/masked incorrectly.
- **New entity type request** — a PII category MaskFlow doesn't cover yet.

## Fixtures and test data — synthetic PII only, no exceptions

**Every fixture, test case, and example in this repo must use synthetic (fake) PII. Never real
PII — not yours, not a coworker's, not "public" data scraped from somewhere.**

This applies to:

- Test fixtures (e.g. `core/tests/fixtures/pii_samples.py`, `packages/detection/tests/fixtures.json`)
- Inline examples in code, docstrings, and READMEs
- Issue and PR descriptions (see the issue templates' synthetic-data warnings)

Good synthetic examples:

- Emails: `@example.com` / `@example.org` domains, or obviously fake names.
- Phone numbers: use reserved ranges (e.g. US `555` exchange).
- Credit cards: use published test numbers (e.g. the card networks' test-account numbers), not a
  real card run through Luhn.
- Names/addresses: invented, or drawn from a synthetic-data generator — not a real person's.

PRs that introduce real-looking PII sourced from a real person or real breach data will be
rejected, even if the intent was just "realistic test data."
