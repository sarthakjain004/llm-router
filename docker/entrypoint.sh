#!/bin/sh
# Renders the runtime config from the read-only mounted config.yaml, then starts
# the proxy. The mounted file is NEVER modified.
#
# OTel toggle: lines in config.yaml prefixed with "# __OTEL__ " are uncommented
# (indentation preserved) only when OTEL_ENABLED=true. This keeps one config
# file as the single source of truth with no host-file mutation and no YAML-merge
# risk.
set -eu

SRC="${LITELLM_CONFIG:-/app/config.yaml}"
RUNTIME=/tmp/runtime-config.yaml

cp "$SRC" "$RUNTIME"

if [ "${OTEL_ENABLED:-false}" = "true" ]; then
  sed -i 's/# __OTEL__ //' "$RUNTIME"
  echo "[entrypoint] OTel callback ENABLED (exporter=${OTEL_EXPORTER:-unset} endpoint=${OTEL_EXPORTER_OTLP_ENDPOINT:-unset})"
else
  echo "[entrypoint] OTel callback disabled (set OTEL_ENABLED=true to enable)"
fi

exec litellm --config "$RUNTIME" --host 0.0.0.0 --port 4000
