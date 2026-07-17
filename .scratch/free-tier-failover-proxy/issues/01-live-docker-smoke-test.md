# 01 — Live `docker compose up` + smoke test on ARM64

Status: ready-for-human

## Why this is open

The build environment had **no running Docker daemon** and **no compose plugin**,
and **no provider API keys**, so acceptance criteria 1 & 2 (compose up clean;
curl returns a completion) could not be executed. All artifacts were verified
statically (YAML parse, `bash -n`, `py_compile`, a live refresh run).

## Steps to close

1. Start Docker Desktop (or colima) and confirm `docker compose version` works.
   The bundled Mac lacked the compose plugin — install Docker Desktop or
   `brew install docker-compose` and register it under `~/.docker/cli-plugins/`.
2. `cp .env.example .env`, `make genkey` → set `LITELLM_MASTER_KEY`, and add real
   `GEMINI_API_KEY` + `GROQ_API_KEY` (minimum to exercise the primary + first
   fallback).
3. `python3 scripts/refresh_models.py --write`
4. `make up` — confirm it builds natively (no `platform`/QEMU warnings) and the
   container reaches healthy.
5. `make smoke` — expect all 7 checks green. Record the exact `x-litellm-*`
   response header names printed in step 3 and, if they differ from
   `x-litellm-model-id` / `x-litellm-model-group`, tighten the assertions in
   `scripts/smoke.sh` and `scripts/failover_test.sh`.

## Definition of done

`make up` clean on arm64 + `make smoke` fully green, with the real header names
confirmed.
