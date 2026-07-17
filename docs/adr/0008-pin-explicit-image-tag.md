# 8. Pin an explicit LiteLLM image tag

Date: 2026-07-17
Status: Accepted

## Context

LiteLLM historically shipped a `main-stable` tag, but it is being **retired
around September 2026** in favour of explicit version tags. Tracking a moving tag
also means a `docker compose up --build` could silently pull a new, possibly
breaking, proxy version. We also must guarantee the image runs natively on ARM64
(Apple Silicon dev + Oracle aarch64 prod) with no emulation.

## Decision

Pin an explicit version via the `LITELLM_TAG` build arg / env var, default
`v1.92.0` — the latest stable line as of July 2026 (v1.93 is only `-rc`, v1.94 is
`-dev`). Verified against the registry: `ghcr.io/berriai/litellm:v1.92.0` is a
multi-arch manifest containing both `linux/amd64` and `linux/arm64`. (Note: the
`main-v1.92.0` variant does **not** exist — use the bare `v1.92.0` tag.)

`LITELLM_TAG` lives in `.env` and flows to both the Dockerfile `FROM` and the
compose `image:` name, so upgrading is a one-line change plus a rebuild.

## Consequences

- Reproducible builds; upgrades are deliberate (bump `LITELLM_TAG`, rebuild,
  re-run the smoke test).
- We must periodically check https://github.com/BerriAI/litellm/releases for a
  newer stable line and re-verify config-schema compatibility before bumping.
- ARM64 is guaranteed at the pinned tag; no `--platform` override or QEMU.
- A thin local Dockerfile wraps this base to add the OTel exporter deps and the
  config-rendering entrypoint (see [ADR-0004](0004-otel-toggle-sentinel-entrypoint.md)),
  so the pin is the only image coordinate we manage.
