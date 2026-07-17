# 02 — Re-validate every VERIFY-AT-BUILD model id with real keys

Status: ready-for-human

## Why this is open

The hand-pinned model ids in `config.yaml` are marked `# VERIFY-AT-BUILD` because
provider lineups drift (Groq/Cerebras/Gemini/NIM deprecate aggressively). They
were set from July-2026 research but not confirmed against live `/models`
endpoints, which needs each provider's key.

## Steps to close

With keys in `.env`, run the validator (it warns on any pinned id missing
upstream, per provider whose key is present):

```bash
python3 scripts/refresh_models.py --check
```

Then confirm/replace, in `config.yaml`:

- `gemini/gemini-2.5-flash`, `gemini/gemini-2.5-flash-lite` — and evaluate whether
  a free 3.x Flash preview has a better RPD; re-balance the Gemini quota ledger
  comment if limits changed.
- `groq/llama-3.3-70b-versatile`, `groq/llama-3.1-8b-instant`,
  `groq/meta-llama/llama-4-scout-17b-16e-instruct`.
- `cerebras/gpt-oss-120b` (alts: `zai-glm-4.7`, `gemma-4-31b`).
- `nvidia_nim/meta/llama-3.3-70b-instruct`, `nvidia_nim/meta/llama-4-scout-17b-16e-instruct`.

## Definition of done

`--check` reports zero pinned-model warnings for every provider that has a key.
