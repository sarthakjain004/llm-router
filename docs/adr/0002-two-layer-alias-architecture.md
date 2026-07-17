# 2. Two-layer alias architecture

Date: 2026-07-17
Status: Accepted

## Context

Agents must reference a **stable** model name, but the actual providers/models
behind it change constantly (deprecations, rotating `:free` lineups, quota cuts).
We also want to add capability tiers (`smart`, `fast`) later without touching
agent code, and we want different aliases to have *different* fallback chains
(e.g. `vision` must fall through vision-capable models only).

LiteLLM detail that constrains the design: `fallbacks` are defined **between
distinct `model_name`s**, and `rpm`/`tpm` are counted **per `model_list` entry**.
`model_group_alias` (multiple names → one group) can't carry per-alias fallback
chains, so it can't express "vision and default resolve differently."

## Decision

Two layers in `config.yaml`:

- **Semantic aliases** (`agent-default`, `vision`, `long-context`) — first-class
  `model_list` entries pointing at the Gemini primary. These are the only names
  agents use. Each has its own chain in `router_settings.fallbacks`.
- **Provider-pinned aliases** (`gemini-flash`, `groq-llama70b`, `cerebras-gptoss`,
  `openrouter-free`, `nim-*`) — the concrete deployments, doubling as fallback
  targets and as debug/pin handles.

Because Gemini's free quota is shared across every entry using its key, and
LiteLLM counts limits per entry, the ~10 RPM / 250K TPM budget is **explicitly
split** across the four Gemini entries (see the ledger comment in `config.yaml`)
so pre-call checks stay truthful.

## Decision — adding a tier later

A new tier is one new `model_list` entry (its primary) + one line in
`fallbacks`. Agents opt in with `model="<tier>"`. No agent-code change.

## Consequences

- The alias contract is decoupled from provider churn (the core goal).
- Pinned aliases intentionally **do not** fail over — a pinned call that fails,
  fails loudly, which is what you want when you pinned on purpose.
- Slight duplication: the Gemini primary appears in several entries. Accepted —
  it's what lets the shared quota be budgeted per use.
- The quota ledger must be kept consistent by hand if Gemini's free limits
  change; the split is documented inline so it's easy to re-balance.
