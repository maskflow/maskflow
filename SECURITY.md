# Security Policy

MaskFlow is a security tool: it detects and masks PII before it reaches an LLM. Bugs here can
mean real PII leaking into a prompt or a log, so we take reports seriously and want to make
reporting them as easy as possible.

## Supported versions

MaskFlow is pre-1.0 and solo-maintained. There isn't a matrix of maintained release branches —
the latest published version of each package (`maskflow-core`, `maskflow-sdk` on PyPI,
`@maskflow/detection` on npm) is the supported one. If you're on an older version, please upgrade
before reporting, if practical.

## Scope

In scope:

- This repository (`core/`, `sdk/python/`, `packages/detection/`, CI/release workflows).
- All packages published from it: `maskflow-core` and `maskflow-sdk` on PyPI, `@maskflow/detection`
  on npm.
- Detection accuracy issues with security impact — e.g. a class of PII that reliably fails to be
  masked (false negative), or a masking/unmasking bug that could reconstruct or leak original PII
  it shouldn't.

Out of scope:

- The marketing site (maskflow.in) — that's static content, not the tool itself.
- General false positives/false negatives without a security angle — please file those as normal
  GitHub issues, not a security report (see CONTRIBUTING.md).
- Vulnerabilities in third-party dependencies (spaCy, etc.) — report those upstream, though we'd
  still appreciate a heads-up if it affects MaskFlow directly.

## Reporting a vulnerability

Email **somya@maskflow.in** with:

- A description of the issue and its potential impact.
- Steps to reproduce, or a minimal proof-of-concept (synthetic data only — see below).
- The affected package(s) and version(s).

Please don't open a public GitHub issue for security reports.

**Do not include real PII in a report.** If a report is easier to demonstrate with example data,
use clearly fake/synthetic values (e.g. `jane.doe@example.com`, `4111 1111 1111 1111`). Reports
containing real personal data will be redacted/deleted on receipt.

### What to expect

- **Acknowledgment within 24 hours.**
- We'll work with you to understand and confirm the issue, and agree on a disclosure timeline.
- **Coordinated disclosure target: 90 days** from initial report, or sooner once a fix is released.
  If a fix needs more time, we'll communicate that and why.
- Credit in the release notes / CHANGELOG if you'd like it (or anonymity if you'd prefer).

## Safe harbor

We consider security research conducted under this policy to be authorized:

- Good-faith testing that avoids privacy violations, service disruption, and data destruction.
- Testing limited to your own accounts/data or synthetic data — never real third-party PII you
  don't have permission to use.
- Reporting through the channel above, and giving us a reasonable opportunity to fix the issue
  before any public disclosure.

We won't pursue legal action against researchers who follow this policy. If a third party (e.g. a
package registry) initiates action related to your good-faith research, we will make it known that
your actions were conducted under this policy.
