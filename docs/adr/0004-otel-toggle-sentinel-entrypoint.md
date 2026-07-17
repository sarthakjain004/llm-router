# 4. Env-toggled OpenTelemetry via a sentinel-line entrypoint

Date: 2026-07-17
Status: Accepted

## Context

The user has an existing OTel/OpenLIT stack and wants LiteLLM's OpenTelemetry
callback **toggleable via env**, off by default. LiteLLM enables it with a config
key (`litellm_settings.callbacks: ["otel"]`) — but that lives in `config.yaml`,
not an env var, and the config is mounted read-only. When the callback is enabled
with no reachable collector, the OTLP exporter retries and logs errors
continuously, so "always on" is not acceptable as a default.

Options:
- **Always-on callback** — noisy exporter errors when no collector; rejected.
- **`include:` a second config** — LiteLLM's merge semantics for `litellm_settings`
  across included files are unverified; risky.
- **Two config files** (`config.yaml` / `config.otel.yaml`) selected by env —
  duplicates the whole config; drift risk.
- **Sentinel-line entrypoint** — keep one config with the callback line commented
  behind a sentinel, uncomment it at boot only when enabled.

## Decision

In `config.yaml` the callback line is written as a sentinel comment:

```yaml
litellm_settings:
  # __OTEL__ callbacks: ["otel"]
```

`docker/entrypoint.sh` copies the read-only mounted config to
`/tmp/runtime-config.yaml`, and when `OTEL_ENABLED=true` strips the `# __OTEL__ `
prefix with `sed` (indentation preserved), then `exec litellm --config
/tmp/runtime-config.yaml`. The exporter is configured via the standard env vars
(`OTEL_EXPORTER`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`).

The thin Dockerfile installs the OTel HTTP exporter deps unconditionally
(idempotent; OpenLIT accepts OTLP/HTTP on :4318, so no grpcio).

## Consequences

- One config file is the single source of truth; the mounted file is never
  mutated (copy-then-edit in `/tmp`).
- `OTEL_ENABLED=false` → the callback line stays commented → zero exporter noise.
- Pure `sh` + `sed`, both present in the Debian-based image; no extra tooling.
- The mechanism is generic: any future "enable only when env set" config line can
  reuse the `# __OTEL__ ` pattern (or a sibling sentinel).
