# maskflow-attest

Reproducible, signed accuracy attestations for a pinned MaskFlow recognizer
pack version. Given a pack version, `maskflow-attest run` runs the full
public benchmark harness against it and produces a dated document; Ed25519
signing makes it a citable, independently checkable claim rather than an
assertion.

> Part of [MaskFlow](https://github.com/maskflow/maskflow). MIT, free
> forever, no telemetry. Implements issue
> [#43](https://github.com/maskflow/maskflow/issues/43).

## Design constraint

This must never create an incentive to keep the measurement closed. The
harness, the dataset, and the reproduction command are all public — the
signature adds provenance (who ran it, against which dataset version, on
what date), never secrecy. If anyone can reproduce the numbers and
disagree, that is the system working as intended.

## What an attestation contains

Pack name/version, corpus name/version, per-entity strict-span and
partial-overlap precision/recall/F1, a methodology summary, the exact
reproduction command, an issue/validity window, and the engine version —
never a raw value, never anything about a specific document.

## Usage

```bash
# Once, offline -- never commit the private key.
maskflow-attest keygen --out-dir keys/

# Run the attestation (the pack under attestation must already be
# installed at exactly this version).
maskflow-attest run \
  --pack-name maskflow-pack-india --pack-version 0.5.1 \
  --corpus bench/indiapii/data/indiapii-v1.0.jsonl \
  --corpus-name indiapii-v1.0 --corpus-version 1.0 \
  --methodology "Full IndiaPII-Bench v1.0, strict-span and partial-overlap matching, MaskFlow's own detector only." \
  --reproduction-command "maskflow-attest run --pack-name maskflow-pack-india --pack-version 0.5.1 --corpus bench/indiapii/data/indiapii-v1.0.jsonl --corpus-name indiapii-v1.0 --corpus-version 1.0" \
  --private-key-file keys/private_key.hex \
  --out attestation.json

# Anyone, anywhere, with the published public key:
maskflow-attest verify attestation.json --public-key-hex <published key>
```

## Security note

`verify` always checks a signature against a public key **you already
trust from an out-of-band source** — this package's docs, a pinned config
value. It never trusts a key embedded in the attestation file being
checked; a re-signed forgery can trivially carry its own "matching" key
along, so only a key the verifier already had before opening the file
means anything.

## Registry

`maskflow-attest registry add/revoke/show` maintains a local, append-only
JSON-lines file of every attestation issued. Revocation flips a flag; it
never deletes the record or its original signature. A hosted registry
endpoint can mirror this same format at scale — this is the mechanism
such a service would wrap, not a stub waiting to be replaced by one.
