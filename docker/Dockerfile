# Thin image over the official LiteLLM proxy.
# The base is multi-arch (linux/amd64 + linux/arm64), so this builds natively on
# Apple Silicon and on the Oracle Cloud ARM64 VM with no emulation.
ARG LITELLM_TAG=v1.92.0
FROM ghcr.io/berriai/litellm:${LITELLM_TAG}

# OpenTelemetry deps for the "otel" callback. HTTP exporter only — no grpcio
# (OpenLIT and most collectors accept OTLP/HTTP on :4318). Idempotent: a no-op
# if the base tag already bundles these.
RUN pip install --no-cache-dir \
    opentelemetry-api \
    opentelemetry-sdk \
    opentelemetry-exporter-otlp-proto-http

# Render-the-config entrypoint (handles the OTEL_ENABLED toggle).
COPY docker/entrypoint.sh /usr/local/bin/llm-router-entrypoint.sh
ENTRYPOINT ["/bin/sh", "/usr/local/bin/llm-router-entrypoint.sh"]
