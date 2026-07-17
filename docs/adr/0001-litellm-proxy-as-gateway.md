# 1. LiteLLM proxy as the single OpenAI-compatible gateway

Date: 2026-07-17
Status: Accepted

## Context

LangGraph agents need one `base_url` that speaks the OpenAI Chat Completions API
(streaming + tool calls) while, underneath, requests are spread across several
free-tier providers with different SDKs, model ids, and rate limits. We need
provider fan-out, health-aware routing, retries, and failover — none of which we
want to hand-roll in agent code.

Options considered:
- **Custom FastAPI shim** in front of each provider SDK — full control, but we'd
  reimplement routing, cooldowns, retries, streaming translation, and tool-call
  passthrough for every provider, and maintain it forever.
- **LiteLLM proxy** — a mature open-source proxy that already exposes an
  OpenAI-compatible surface, normalizes ~100 providers, and has a router with
  fallbacks, cooldowns, and per-deployment rate-limit awareness.
- **OpenRouter alone** — a hosted aggregator, but its free tier is a single 50
  requests/day bucket; it isn't a general free-tier aggregator across Gemini/
  Groq/Cerebras/NIM.

## Decision

Use the **LiteLLM proxy** (`ghcr.io/berriai/litellm`) as the gateway, configured
declaratively via `config.yaml`. Agents talk only to it.

Pin an explicit image tag rather than `main-stable` (which is being retired
~Sept 2026): `v1.92.0`, verified multi-arch incl. `linux/arm64`. See
[ADR-0008](0008-pin-explicit-image-tag.md).

## Consequences

- We get streaming, tool/function-call passthrough, `/v1/models`, per-deployment
  `rpm`/`tpm`, cooldowns, and fallbacks for free; our job is configuration.
- We inherit LiteLLM's release cadence and occasional config-schema changes —
  mitigated by pinning a version and verifying syntax against current docs.
- `drop_params: true` is required so a request that works on one provider doesn't
  break when it fails over to another that rejects an unknown param.
- The proxy is a single process on one host; horizontal scale (shared cooldown
  state across replicas) would need Redis + `usage-based-routing-v2`. Out of
  scope for a single Always-Free VM.
