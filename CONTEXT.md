# Context: llm-router

A self-hosted [LiteLLM](https://docs.litellm.ai) proxy that gives agents **one**
OpenAI-compatible endpoint and fails over across free-tier LLM providers so
inference costs nothing. Single bounded context; domain docs live at the repo
root (this file) plus `docs/adr/`.

## Purpose

LangGraph agents point their `base_url` at this proxy and call a stable
**semantic alias**. The proxy chooses a live free provider, streams the response
back OpenAI-style, and transparently retries/fails over when a provider is rate-
limited or down. Agent code never names a provider.

## Ubiquitous language

Use these exact terms in issues, ADRs, comments, and test names. Avoid the
synonyms in the last column.

| Term | Meaning | Avoid |
| ---- | ------- | ----- |
| **endpoint** | The single OpenAI-compatible URL the proxy exposes: `http://host:4000/v1`. | "the API", "the server" |
| **semantic alias** | A stable, capability-named model id agents call: `agent-default`, `vision`, `long-context`. The public contract. | "model name" (ambiguous) |
| **pinned alias** | A provider-specific model id (`groq-llama70b`, `gemini-flash`, `nim-llama`) used for debugging or deliberate pinning, and as a fallback target. Does **not** fail over. | "direct model" |
| **deployment** | One `model_list` entry: a `(model_name, litellm_params)` pair mapping an alias to a concrete `provider/model` with rpm/tpm annotations. | "route", "backend" |
| **model group** | All deployments sharing one `model_name`; LiteLLM load-balances within a group. `openrouter-free` is a group of several `:free` models. | "cluster" |
| **fallback chain** | The ordered list of aliases a semantic alias falls through on failure, defined once in `router_settings.fallbacks`. | "failover list", "cascade" |
| **cooldown** | The period a deployment is benched after a 429/5xx (`cooldown_time`). Router routes around it. | "backoff", "ban" |
| **pre-call check** | Router filtering that skips a deployment already over its annotated rpm/tpm before dispatch (`enable_pre_call_checks`). | "rate check" |
| **rpm / tpm / rpd / tpd** | Requests- and tokens-per-minute/day. Free-tier ceilings. rpm/tpm are enforced by the router; rpd/tpd are absorbed by cooldowns. | — |
| **free tier** | A provider's no-cost usage allowance. One legitimate key per provider — no multi-account key-farming (ToS violation). | "free plan" |
| **generated block** | The `openrouter-free` region of `config.yaml` between `BEGIN/END GENERATED` markers, owned by the refresh script. Hand edits are overwritten. | — |
| **refresh** | Running `scripts/refresh_models.py` to regenerate the generated block and validate pinned ids. | "sync", "update" |
| **master key** | `LITELLM_MASTER_KEY` — the single bearer token agents present as their OpenAI `api_key`. | "API key" (that's a provider key) |
| **provider key** | A provider's own credential (`GEMINI_API_KEY`, etc.), never exposed to agents. | — |
| **escape hatch** | Calling a pinned alias to bypass the default chain for one request. | — |
| **tier** | A capability band of semantic aliases (today: the default; future: `smart` / `fast`). | "level" |

## Invariants

1. **Agents depend only on semantic aliases.** Provider/model churn happens
   behind them; the alias contract is stable. (ADR-0002)
2. **Fallback order is edited in exactly one place** — `router_settings.fallbacks`
   in `config.yaml`. (ADR-0003)
3. **No secrets in git.** All keys come from `.env` (gitignored); only
   `.env.example` is tracked.
4. **The generated block is script-owned.** Hand-pinned deployments are only
   *validated* by the refresh script, never rewritten. (ADR-0006)
5. **Runs DB-less by default.** Postgres/Neon is opt-in and env-gated. (ADR-0005)
6. **The endpoint is never publicly exposed.** Master key + private-network
   bind; no TLS layer in this stack. (ADR-0007)
7. **Everything runs on ARM64** (Apple Silicon + Oracle aarch64) natively.

## Where the code actually runs

This repo is **declarative configuration only** — there is no routing, retry, or
proxy code here. The *logic* that reads `config.yaml` and does the work lives in
the upstream **`litellm` package baked into the container image**
(`ghcr.io/berriai/litellm:v1.92.0`), not in these files. `config.yaml`'s
`router_settings` simply parameterizes LiteLLM's built-in `Router`. (ADR-0001)

Chain: `docker/entrypoint.sh` → `litellm --config …` (`litellm/proxy/proxy_cli.py`)
→ the FastAPI app in `litellm/proxy/proxy_server.py` → a `litellm.Router` built
from our config. The mechanisms (paths confirmed at tag `v1.92.0`):

| Behavior | Upstream file (inside the image) | Our config knob |
| -------- | -------------------------------- | --------------- |
| retries within a model group | `litellm/router.py` → `async_function_with_retries` | `num_retries`, `retry_after` |
| failover between aliases | `litellm/router.py` → `async_function_with_fallbacks` | `fallbacks` |
| per-error-type retry counts | `litellm/router_utils/get_retry_from_policy.py` | `retry_policy` |
| cooldown on 429/5xx | `litellm/router_utils/cooldown_handlers.py`, `cooldown_cache.py` | `cooldown_time`, `allowed_fails`, `allowed_fails_policy` |
| `x-litellm-*` response headers | `litellm/router_utils/add_retry_fallback_headers.py` | — |
| the `/v1/...` HTTP surface | `litellm/proxy/proxy_server.py` | `model_list`, `general_settings` |

To read it: `https://github.com/BerriAI/litellm/blob/v1.92.0/litellm/router.py`,
or in the running container —
`docker exec llm-router python3 -c "import litellm,os;print(os.path.dirname(litellm.__file__))"`.
Changing *how* failover behaves (not just order/limits) means configuring
`router_settings` or forking the image; this repo's job is to declare intent.

## Where things live (in this repo)

- Interface contract & runbook → [`README.md`](README.md)
- Decisions & their rationale → [`docs/adr/`](docs/adr/)
- Open work / follow-ups → [`.scratch/`](.scratch/) (see `docs/agents/issue-tracker.md`)
