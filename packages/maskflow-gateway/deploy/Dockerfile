# MaskFlow Gateway -- OpenAI/Anthropic-compatible masking proxy.
#
# Build (multi-arch in CI via buildx):
#   docker build -f packages/maskflow-gateway/deploy/Dockerfile \
#     --build-arg MASKFLOW_GATEWAY_VERSION=0.1.0 \
#     -t maskflow/gateway packages/maskflow-gateway
#
# The spaCy model is baked in so MASKFLOW_GATEWAY_NER=1 works out of the
# box; it is inert (never loaded) when NER is off, which is the default.
#
# Published as ghcr.io/maskflow/gateway:<version> and :latest by
# .github/workflows/release-gateway.yml on a `gateway-v*` tag.

FROM python:3.12-slim AS build

ARG MASKFLOW_GATEWAY_VERSION=""
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN set -eux; \
    pip install "maskflow-gateway[redis]${MASKFLOW_GATEWAY_VERSION:+==${MASKFLOW_GATEWAY_VERSION}}"; \
    python -m spacy download en_core_web_sm; \
    python -c "import maskflow_gateway.app, maskflow_pack_india, maskflow_pack_intl"

FROM python:3.12-slim

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    MASKFLOW_GATEWAY_JSON_LOGS=1
COPY --from=build /opt/venv /opt/venv

RUN useradd --create-home --uid 10001 gateway
USER gateway
WORKDIR /home/gateway

EXPOSE 8000
# Liveness only -- /readyz (which pings Redis) is for the orchestrator.
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"

ENTRYPOINT ["maskflow-gateway"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
