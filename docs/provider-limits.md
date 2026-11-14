# Observed free-tier limits (real, per-account)

These are the **actual** limits observed for this deployment's keys, not the
marketing/doc numbers. They are **account-specific and drift** — re-check
periodically (Gemini: [aistudio.google.com/rate-limit](https://aistudio.google.com/rate-limit);
Groq: response headers). Last checked **2026-07-20**; latency and availability re-measured **2026-11-14** (next section).

Format below: `RPM` = requests/min, `TPM` = tokens/min, `RPD` = requests/day.

## Measured 2026-11-14 (one 1.9K-token prompt, two runs each, direct to each provider)

Evidence from one prompt on one afternoon, not a benchmark. The prompt asked for JSON edits to a
résumé (about 1,900 tokens in, 400 to 1,100 out).

| Model | Time | Result |
|---|---|---|
| Groq `openai/gpt-oss-20b`, low reasoning | 1.1 to 1.3 s | valid JSON; serves the `fast` alias |
| Gemini `gemini-3.5-flash-lite` | 1.9 s | valid JSON |
| Gemini `gemini-3.1-flash-lite` | 2.2 to 2.4 s | valid JSON |
| Groq `openai/gpt-oss-120b`, low reasoning | 2.5 to 2.9 s | valid JSON |
| Groq `qwen/qwen3.8-27b` | 2.2 s, then 429 | output-token limit hit on the second call |
| Cloudflare `llama-3.3-70b-instruct-fp8-fast` | 9.4 s | valid JSON |
| Cloudflare `gpt-oss-120b` | 9 to 18 s | valid JSON |
| Gemini `gemini-3.5-flash`, low reasoning | 16 to 17 s | valid JSON |
| Gemini `gemini-3.6-flash`, low reasoning | 18 s | valid JSON; serves the `smart` alias |
| Gemini `gemini-3.6-flash`, default reasoning | over 30 s | ran past the router timeout twice |
| Gemini `gemini-3.7-flash`, `gemini-3.8-flash` | no answer in 60 s | both runs timed out |
| Gemini `gemini-2.5-flash`, `gemini-2.5-flash-lite` | 404 | retired for new users |
| OpenRouter `:free` models | 45 to 480 s | reasoning models that mostly hit the token ceiling |
| Cerebras (both models) | 402 | still gated behind billing |
| Ollama Cloud | 402 | asks for credits |
| NVIDIA NIM `llama-3.3-70b-instruct` | 410 | model retired 2026-08-26 |
| Z.AI, GitHub Models, Cohere | error | no key set; the router errors on them rather than skipping (Cohere after 17 s) |

**Free-tier Gemini stalls on its own.** Ten short calls sent straight to `gemini-3.1-flash-lite`
(no router): seven answered in about 1 s, one took 11.6 s, one returned 503 "high demand" after
57 s, and one gave no answer in 90 s. Connects to Google took 10 to 30 ms throughout and the
router's own overhead was under 3 ms, so the stalls are the provider's. That is why a timed-out
call is no longer retried on the same provider (`TimeoutErrorRetries: 0`) and why `fast` and
`smart` carry their own short timeouts.

**Groq (from response headers):** 1,000 requests a day and 8,000 tokens a minute for each of
`gpt-oss-20b`, `gpt-oss-120b` and `qwen3.8-27b`. The Llama models the Groq section below lists
are gone from the key (404).

## Google Gemini (AI Studio free tier — from the user's dashboard, 2026-07-20)

Only the text-generation models that matter for this proxy are listed.

**New (2026-07-22):** `gemini-3.6-flash` and `gemini-3.5-flash-lite` are now on the
key (41 models total). The config's premium aliases use **`gemini-flash-latest`**
(auto-tracks the newest Flash → currently 3.6-flash), so future releases need no
code change. The new models' exact RPD are dashboard-only — check
[aistudio.google.com/rate-limit](https://aistudio.google.com/rate-limit); if
`gemini-3.5-flash-lite`'s RPD is ≥ 500, switch the workhorse to it. Extra keys
auto load-balance: add `GEMINI_API_KEY_2/_3` to `.env` (see `docker/keyfanout.py`).

| Model | RPM | TPM | **RPD** | Context | Notes |
|---|---|---|---|---|---|
| **Gemini 3.1 Flash Lite** | 15 | 250K | **500** | 1M | ⭐ the real workhorse — 25× the daily volume of 3.5 Flash |
| Gemini 3.5 Flash | 5 | 250K | **20** | 1M | best quality, but only **20 requests/day** |
| Gemini 3 Flash | 5 | 250K | 20 | 1M | |
| Gemini 2.5 Flash | 5 | 250K | 20 | 1M | |
| Gemini 2.5 Flash Lite | 10 | 250K | 20 | 1M | |
| Gemma 4 26B | 30 | 16K | — | 128K | highest RPM, but low TPM |
| Gemini Embedding 1 / 2 | 100 | 30K | 1K | — | for the *retrieval* side of RAG |

**Key takeaway:** across all the free Flash models, **TPM is a generous 250K** and
the **context window is 1M** — excellent for RAG. The binding limit is **RPD**:
Gemini 3.5 Flash is capped at **20 requests/day**, while **3.1 Flash Lite gives
500/day**. Google does not publish a tokens/day (TPD) cap — RPD is the daily wall.

## Groq (free tier — from live response headers, 2026-07-20)

| Model | RPM | TPM | RPD | TPD | Context |
|---|---|---|---|---|---|
| `llama-3.3-70b-versatile` (groq-llama70b) | 30 | 12K | 1,000 | ~100K | 131K |
| `llama-3.1-8b-instant` (groq-fast) | 30 | 6K | 14,400 | ~500K | 131K |

RPM/TPM/RPD are live-verified; TPD is from Groq's docs. For RAG, **the 70B's ~100K
TPD is the real ceiling** (a ~7K-token RAG call ≈ only ~14 big queries/day).

## Cerebras

**Gated behind billing** as of 2026-07-20 — the key returns HTTP 402
("Payment required — visit billing tab"). No usable no-card free tier. Kept in the
config but dormant; the router skips it.

## How this maps to the fallback chain

`agent-default`'s chain is `gemini-3.5-flash → gemini-3.1-flash-lite → groq-llama70b → …`.
Given the numbers above, your **effective daily generation capacity** is roughly:

- ~**20** top-tier requests (Gemini 3.5 Flash), then automatically
- ~**500** high-quality requests (Gemini 3.1 Flash Lite, 250K TPM, 1M context), then
- ~**1,000** fast requests (Groq 70B) / ~**14,400** (Groq 8B), then OpenRouter (50/day), etc.

This is **by design** and healthy — you get the best model for a small daily
allowance, then fall through to very capable, higher-volume tiers. It's also why
`agent-default` is usually served by `gemini-3.1-flash-lite`, not 3.5 Flash.

**For RAG specifically:** 3.1 Flash Lite (500 RPD, 250K TPM, 1M context) is the
practical primary. If you want *consistent* behaviour (not 20 requests of one model
then a switch), consider making `gemini-3.1-flash-lite` the `agent-default` primary
directly. Note LiteLLM's pre-call checks enforce RPM/TPM but **not RPD** — the daily
cap is handled by cooldowns on the 429 (a spent-for-the-day model benches and the
router falls through).
