# 05 — Add `smart` / `fast` capability tiers

Status: ready-for-agent

## Why this is open

A planned future enhancement, deliberately deferred. The two-layer architecture
(ADR-0002) was designed so this needs no agent-code change — capturing it here so
the extension point isn't forgotten.

## Steps to close

In `config.yaml`, for each new tier add one `model_list` entry (its primary) and
one line in `router_settings.fallbacks`. Suggested starting shapes:

- `fast` (latency-first): primary `groq/llama-3.1-8b-instant`; chain
  `[groq-fast, cerebras-gptoss, gemini-flash-lite]`.
- `smart` (capability-first): primary `gemini/gemini-2.5-flash`; chain
  `[groq-llama70b, cerebras-gptoss, openrouter-free, nim-llama]`.

Then `make restart` and add a smoke-test case per new alias.

## Definition of done

`smart` and `fast` appear in `/v1/models`, each fails over per its chain, and the
README alias table is updated. Agents opt in with `model="smart"` / `"fast"`.
