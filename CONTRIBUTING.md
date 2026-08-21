# Contributing to MaskFlow

Thanks for considering a contribution. MaskFlow is solo-maintained, so response times can vary,
but every issue and PR gets read.

## Project layout

MaskFlow is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) (Python)
plus an npm workspace (TypeScript), rooted in the same repo:

- [`packages/maskflow-core/`](packages/maskflow-core) — `maskflow-core`, the detection/masking
  engine. Ships **zero recognizers** — no PII type is built in, packs register them.
- [`packs/maskflow-pack-intl/`](packs/maskflow-pack-intl) — `maskflow-pack-intl`, the original
  12 intl/US-shaped recognizers (email, phone, SSN, credit card, IP, AWS/API keys, JWT, IBAN,
  address, person name, date of birth), registered against `maskflow-core` on import.
- [`packages/maskflow-sdk/`](packages/maskflow-sdk) — `maskflow-sdk`, the Python SDK, built on
  `maskflow-core` + `maskflow-pack-intl`.
- [`packages/maskflow-cli/`](packages/maskflow-cli) — `maskflow-cli`, the `maskflow config
  validate`/`show` command line tool for `.maskflowrc` (the config engine itself --
  schema/discovery/validation -- lives in `maskflow_core.config`, not here). Not yet published to
  PyPI.
- [`packages/maskflow-js/`](packages/maskflow-js) — `@maskflow/detection`, the TypeScript port of
  the regex/structural detection layer (npm workspace; package name unchanged despite the
  directory name).

## Setup

### Python packages (`packages/maskflow-core`, `packs/maskflow-pack-intl`, `packages/maskflow-sdk`, `packages/maskflow-cli`)

Requires [uv](https://docs.astral.sh/uv/). Run from the **repo root** — it's a single uv
workspace with one shared lockfile:

```bash
uv sync --all-extras
uv run python -m spacy download en_core_web_sm
```

### TypeScript package (`packages/maskflow-js`)

From the repo root (it's an npm workspace):

```bash
npm ci
npm run build -w @maskflow/detection
```

## Running tests

```bash
# maskflow-core
uv run pytest packages/maskflow-core/tests

# maskflow-pack-intl
uv run pytest packs/maskflow-pack-intl/tests

# maskflow-sdk
uv run pytest packages/maskflow-sdk/tests

# maskflow-cli
uv run pytest packages/maskflow-cli/tests

# @maskflow/detection
npm test -w @maskflow/detection
```

Also run `ruff check .`, `ruff format --check .`, and `mypy packages/maskflow-core --strict`
before pushing — `pre-commit install` wires up ruff/mypy/gitleaks to run automatically on commit.

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

- Test fixtures (e.g. `packs/maskflow-pack-intl/tests/fixtures/pii_samples.py`,
  `packages/maskflow-js/tests/fixtures.json`)
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
