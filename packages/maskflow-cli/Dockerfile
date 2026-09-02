# `maskflow` CLI -- full image, including the spaCy NER pass so
# `maskflow scan --deep` (bare names & addresses) works out of the box.
#
# Build (nothing is COPY'd, so the context is just this directory):
#   docker build -f packages/maskflow-cli/Dockerfile \
#     --build-arg MASKFLOW_CLI_VERSION=0.6.0 \
#     -t maskflow/cli packages/maskflow-cli
#
# Run -- mount the directory holding your data as /work:
#   docker run --rm -v "$PWD:/work" ghcr.io/maskflow/cli \
#     scan jsonl /work/requests.jsonl --field 'messages[].content' \
#     --deep -o /work/exposure-report.html
#
# Published as ghcr.io/maskflow/cli:<version> and :latest by
# .github/workflows/release-cli.yml on a `cli-py-v*` tag.

FROM python:3.12-slim

# Empty => install the latest published maskflow-cli. A release build pins
# the exact version so the image matches the tag.
ARG MASKFLOW_CLI_VERSION=""

RUN set -eux; \
    pip install --no-cache-dir \
      "maskflow-cli[s3,postgres]${MASKFLOW_CLI_VERSION:+==${MASKFLOW_CLI_VERSION}}"; \
    python -m spacy download en_core_web_sm; \
    python -c "import maskflow_cli.app, maskflow_pack_india, maskflow_pack_intl"; \
    maskflow --help >/dev/null

# Unprivileged; /work is the mount point for the caller's data.
RUN useradd --create-home --uid 10001 scanner
USER scanner
WORKDIR /work

ENTRYPOINT ["maskflow"]
CMD ["--help"]
