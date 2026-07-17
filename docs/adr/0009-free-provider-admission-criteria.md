# 9. Free-provider admission criteria

Date: 2026-07-17
Status: Accepted

## Context

New free LLM APIs appear (and disappear) constantly — the refresh script exists
precisely because the roster churns. Without a stated rule for *which* free
providers we actually wire into the failover chain, every candidate gets
re-litigated from scratch ("why not Mistral? it has the biggest quota"). We want a
durable checklist so the roster can grow by *applying* a policy, not by making a
fresh decision each time — and so the deliberate exclusions are recorded once.

This ADR is the policy. The concrete list of admitted providers is volatile config
detail and lives in `config.yaml` / the README, not here.

## Decision

A free provider earns a pinned deployment and a slot in a fallback chain only if
it meets **all** of:

1. **Recurring-free** — a renewing free tier or daily/monthly quota, *not* one-time
   trial credits that deplete or expire. (Excludes Together, Nebius, DeepInfra,
   Fireworks, Hyperbolic, etc.)
2. **No credit card** to obtain the free tier (email / account / phone-only is OK).
3. **Config, not code** — natively supported by LiteLLM (preferred), or reachable
   via the generic OpenAI-compatible path (`model: openai/<id>` + `api_base`). No
   image changes. (See ADR-0001.)
4. **Tool/function calling** on at least one free model — evaluated per model, not
   per provider, since agents depend on it. Set `supports_function_calling: true`.
5. **Data-privacy gate** — exclude any provider whose free tier *requires* opting
   into training on your data. Gemini already trains on free traffic and is
   accepted as the primary; we won't *expand* that exposure by mandate. Providers
   where training is off-by-default or optional are fine.

Ordering within a chain follows ADR-0003 (most free headroom first; finite
reserves last). Keys ship **blank** in `.env.example`, so an admitted provider is
inert until a key is filled and the router skips it — adoption is opt-in.

## Consequences

- The roster grows by running the checklist; **no new ADR per addition**. The
  current members live in `config.yaml` (with per-provider limits and
  `# VERIFY-AT-BUILD` model ids) and the README provider table.
- Deliberate exclusions are now on record: **Mistral** (biggest free quota, but its
  free "Experiment" tier requires the training opt-in → fails criterion 5);
  trial-credit shops (fail 1); **Vercel AI Gateway** (passes on merits but
  redundant with cheaper adds); **Chutes / Featherless** (no longer free).
- Criterion 5 is a margin call: "requires opt-in to training" excludes; "optional
  / default-off" is allowed. Record the determination in the commit when admitting
  a borderline provider.
- As of this ADR the admitted extras are **Cloudflare Workers AI, Z.AI/Zhipu GLM,
  GitHub Models, and Cohere** — all no-card, LiteLLM-native, tool-capable. Exact
  ids, prefixes, env vars, and limits: see `config.yaml` and `.env.example`.
- The refresh script currently validates only the original providers' pinned ids;
  adding validators for newly-admitted providers is an optional follow-up.
