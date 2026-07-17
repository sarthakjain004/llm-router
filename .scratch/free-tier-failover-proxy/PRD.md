# PRD: Free-tier failover proxy

Status: in-progress

## Problem

LangGraph agents need one OpenAI-compatible endpoint that transparently fails
over across free-tier LLM providers, so inference is always $0. Managing five
providers' SDKs, model ids, and rate limits in agent code is untenable.

## Goal

A self-hosted LiteLLM proxy exposing `http://host:4000/v1` (chat completions +
streaming + tool calls), with automatic per-provider cooldown-on-429/5xx and
failover, deployable on an Oracle Cloud Always Free ARM64 box, tested locally on
Apple Silicon first.

## Scope (delivered)

- `config.yaml` — two-layer aliases (`agent-default` / `vision` / `long-context`
  + provider-pinned), fallback chains, cooldowns, pre-call checks. See CONTEXT.md
  and docs/adr/.
- `docker-compose.yml` + thin `docker/Dockerfile` + `docker/entrypoint.sh`
  (OTel toggle). Pinned `LITELLM_TAG=v1.92.0` (arm64-verified).
- `.env.example` (all keys via env; `.env` gitignored), Makefile.
- `scripts/refresh_models.py` — regenerates the `openrouter-free` group + validates
  pinned ids. **Verified working live** (pulled 4 Nemotron-3 `:free` models).
- `scripts/smoke.sh` + `scripts/failover_test.sh` (+ `compose.failover.yml`).
- `examples/langgraph_client.py`, `README.md` with the Oracle runbook.
- Optional, off by default: OTel callback, Neon Postgres logging, Ollama tier.

## Out of scope

- Public HTTPS / reverse proxy (private-network access only — ADR-0007).
- Multi-replica routing with shared Redis cooldown state.
- Multi-account key-farming (ToS violation) — one legit key per provider.

## Acceptance criteria

1. `docker compose up` starts cleanly on ARM64. — *pending live run (issue 01)*
2. curl smoke test returns a valid completion. — *pending keys (issue 01)*
3. Erroring the primary provider makes the next serve the request. — *pending (issue 03)*
4. No secrets committed; `.env` gitignored. — **met** (verify at commit).

## Verification done without Docker/keys

- `config.yaml` parses (15 deployments; all fallback targets resolve).
- `refresh_models.py` compiles, runs live, is idempotent, fixes generated-block indent.
- `smoke.sh` / `failover_test.sh` / `entrypoint.sh` pass `bash -n`.

## Open follow-ups

See `issues/` — the live Docker/provider-key tests couldn't run in the build
environment (no Docker daemon, no keys) and are tracked there.
