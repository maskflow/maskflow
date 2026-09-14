# Attestations — reproducible, signed accuracy claims

Detection accuracy is measured and published, never asserted (see
[`docs/bench.md`](bench.md) and the IndiaPII-Bench results). An
attestation makes one specific pack version's measured accuracy **citable,
dated, and independently verifiable by a third party** — not a new claim,
a provenance wrapper around an existing one.

> **Status.** The mechanism (`maskflow-attest`, issue
> [#43](https://github.com/maskflow/maskflow/issues/43) /
> [#109](https://github.com/maskflow/maskflow/issues/109)) is shipped.
> Minting a real production signing key and publishing its first
> attestation is a separate, offline operational step, not yet done — the
> public key below is a placeholder until that happens.

## Design constraint

This must never create an incentive to keep the measurement closed.
Everything that could produce an attestation is public: the benchmark
harness (`maskflow-bench`, reused unmodified — no separate scoring code
exists for attestations), the IndiaPII-Bench dataset, and the exact
reproduction command each attestation carries. The signature adds
provenance — who ran it, against which dataset version, on what date —
never secrecy. If anyone reproduces the numbers and disagrees, that is the
system working as intended.

## What an attestation contains

Pack name/version, corpus name/version and document count, per-entity
strict-span and partial-overlap precision/recall/F1, a methodology
summary, the exact reproduction command, an issue/validity window (default
90 days), and the engine version. Never a raw value, never anything about
a specific document — same metadata-only discipline as the
[evidence layer](evidence.md).

## Verifying an attestation

```bash
pip install maskflow-attest
maskflow-attest verify attestation.json --public-key-hex <trusted key, see below>
```

`verify` always requires **you** to supply the trusted public key — never
a key found inside the attestation file itself, which would let a
re-signed forgery vouch for its own forger. Get the current trusted key
only from this page, never from anywhere in the file you're checking.

**Current public key:** not yet issued — see Status above.

## Reproducing the underlying numbers yourself

An attestation's `reproduction_command` field is the exact command that
produced it. For the published IndiaPII-Bench corpus, that looks like:

```bash
git clone https://github.com/maskflow/maskflow
cd maskflow
uv sync --all-extras
uv run python -m spacy download en_core_web_sm
pip install "maskflow-pack-india==<pinned version>"

maskflow-attest run \
  --pack-name maskflow-pack-india --pack-version <pinned version> \
  --corpus bench/indiapii/data/indiapii-v1.0.jsonl \
  --corpus-name indiapii-v1.0 --corpus-version 1.0 \
  --methodology "Full IndiaPII-Bench v1.0, strict-span and partial-overlap matching, MaskFlow's own detector only." \
  --reproduction-command "<this same command>" \
  --private-key-file <your own test key -- see maskflow-attest keygen> \
  --out my-attestation.json
```

Your numbers should match the published attestation's `metrics` field
exactly (same dataset, same pinned pack version, same deterministic
detector). They won't be signed with MaskFlow's key — that's expected;
reproducing the *numbers* is the point, not reproducing the *signature*
(only MaskFlow's own signing key can produce that, by design — see the
key-custody note below).

## Revocation

`maskflow-attest registry revoke` flips a `revoked` flag on a record; it
never deletes the record or its original signature, so a
previously-downloaded copy of a since-revoked attestation still verifies
and is still marked revoked — a correction layered on top, never an
erasure. Reasons for revocation might include a dataset bug found after
issuance, or a pack version pulled for an unrelated defect.

## Key custody

The private signing key is generated once, offline (`maskflow-attest
keygen`), and never committed to this repo or any CI run — store it only
in a deploy-environment secret store, scoped to whatever process actually
runs `maskflow-attest run` on a schedule. The mechanism, the key format,
and verification all work identically whether that's run by hand, by a
cron job, or by a hosted service — nothing here depends on which.
