# 04 — OTel → OpenLIT end-to-end check

Status: ready-for-agent

## Why this is open

The `OTEL_ENABLED` sentinel-line toggle (ADR-0004) is implemented but not
exercised against a live collector.

## Steps to close

1. Point at the user's OpenLIT OTLP receiver, or spin a throwaway collector:
   `docker run --rm -p 4318:4318 otel/opentelemetry-collector`
2. In `.env`: `OTEL_ENABLED=true`, `OTEL_EXPORTER=otlp_http`,
   `OTEL_EXPORTER_OTLP_ENDPOINT=http://<host>:4318`; `make restart`.
3. Confirm the entrypoint logs `OTel callback ENABLED`, send one `agent-default`
   request, and confirm spans arrive at the collector.
4. Set `OTEL_ENABLED=false`, `make restart`; confirm zero OTLP exporter errors in
   the logs (the callback line stays commented).

## Definition of done

Spans visible in OpenLIT when on; no exporter noise when off.
