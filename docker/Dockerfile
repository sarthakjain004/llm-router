# Thin image over the official LiteLLM proxy.
# The base is multi-arch (linux/amd64 + linux/arm64), so this builds natively on
# Apple Silicon and on the Oracle Cloud ARM64 VM with no emulation.
ARG LITELLM_TAG=v1.92.0
FROM ghcr.io/berriai/litellm:${LITELLM_TAG}

# NOTE: the OpenTelemetry deps the "otel" callback needs (opentelemetry-api/sdk +
# the OTLP/HTTP exporter) are ALREADY bundled in this base image — verified:
#   python3 -c "import opentelemetry.exporter.otlp.proto.http"   # succeeds
# The image ships a uv-managed venv at /app/.venv with NO `pip`, so do not add a
# `RUN pip install ...` here (it fails with "pip: not found"). If a future base
# tag ever drops these, install with `RUN uv pip install <pkg>` instead.

# Render-the-config entrypoint (handles the OTEL_ENABLED toggle).
COPY docker/entrypoint.sh /usr/local/bin/llm-router-entrypoint.sh
ENTRYPOINT ["/bin/sh", "/usr/local/bin/llm-router-entrypoint.sh"]
