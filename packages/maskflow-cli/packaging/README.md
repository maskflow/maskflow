# Packaging `maskflow`

How the CLI is distributed, and how each artifact is built.

| channel | what you get | NER pass (names/addresses/DOB)? |
|---|---|---|
| **pipx / pip** | `pip install maskflow-cli` (`[s3]` / `[postgres]` extras) | Yes, with `python -m spacy download en_core_web_sm` |
| **Docker** — `ghcr.io/maskflow/cli` | full CLI, spaCy + model baked in | Yes, out of the box |
| **Standalone binary** — GitHub Releases | single ~15 MB file, no Python needed | **No** — pattern/checksum pass only |
| **GitHub Action** — [`packaging/scan-action`](../../../packaging/scan-action/) | `maskflow scan` in CI, report as an artifact | Yes (downloads the model) |

## pipx

```bash
pipx install maskflow-cli
# or one-off:
pipx run maskflow-cli scan jsonl requests.jsonl --field 'messages[].content'
```

`maskflow-cli` publishes to PyPI from `.github/workflows/release-cli.yml`
on a `cli-py-v*` tag (trusted publishing, no stored token).

## Docker

`Dockerfile` in the package root. Built and pushed to
`ghcr.io/maskflow/cli:<version>` and `:latest` by the same release
workflow, `linux/amd64` + `linux/arm64`.

```bash
docker run --rm -v "$PWD:/work" ghcr.io/maskflow/cli \
  scan jsonl /work/requests.jsonl --field 'messages[].content' \
  --deep -o /work/exposure-report.html
```

## Standalone binary

`maskflow.spec` + `_entry.py` here, built with PyInstaller by the release
workflow's `binaries` matrix (linux/macos/windows) and attached to the
GitHub Release.

**The binary deliberately excludes spaCy** — bundling it and the model
turns ~15 MB into ~1 GB and is fragile across the three OSes. So the binary
runs the **pattern/checksum pass only**: Aadhaar, PAN, GSTIN, UPI, IFSC,
credit cards, email, phones, the Indian gazetteer-based name/address
layers, etc. It does *not* run the generic spaCy NER pass; `--deep` exits
with a message pointing at the pip / Docker install. Reports it generates
still contain no raw PII (excerpt dates are scrubbed regardless of NER).

```bash
pyinstaller --clean --noconfirm packages/maskflow-cli/packaging/maskflow.spec
./dist/maskflow scan jsonl requests.jsonl --field 'messages[].content'
```

`_entry.py` calls `multiprocessing.freeze_support()` first — without it a
`scan --workers >1` pool re-launches the frozen binary with
multiprocessing's own argv and Typer aborts on the unknown `-B`.
