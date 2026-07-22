# Observed free-tier limits (real, per-account)

These are the **actual** limits observed for this deployment's keys, not the
marketing/doc numbers. They are **account-specific and drift** — re-check
periodically (Gemini: [aistudio.google.com/rate-limit](https://aistudio.google.com/rate-limit);
Groq: response headers). Last checked **2026-07-20**.

Format below: `RPM` = requests/min, `TPM` = tokens/min, `RPD` = requests/day.

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
