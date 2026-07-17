# 6. Generated `openrouter-free` block via the refresh script

Date: 2026-07-17
Status: Accepted

## Context

OpenRouter's `:free` model lineup rotates frequently (as of July 2026 the
DeepSeek/Mistral free variants are gone; Nemotron 3 / gpt-oss / Gemma are in).
Hardcoding `:free` ids means stale config; the reference proxy repos solve this
with a refresh script. One reference (tomaasz) registers models at runtime via
LiteLLM's `POST /model/new` — but that requires `DATABASE_URL` +
`STORE_MODEL_IN_DB`, which conflicts with our DB-off default (ADR-0005).

## Decision

`scripts/refresh_models.py` (stdlib-only, no DB) **regenerates a marker-delimited
block** in `config.yaml`:

- It queries `GET https://openrouter.ai/api/v1/models` (works unauthenticated),
  keeps zero-priced models that support `tools`, and unions that with
  `:free` ids scraped from cheahjs/free-llm-api-resources (to catch models
  OpenRouter hasn't flagged free in its own pricing). It ranks by preferred
  family + context length and writes up to `--limit` (default 4) entries, all
  sharing `model_name: openrouter-free` (a load-balanced group), splitting the
  20 RPM account cap across them.
- Only the region between `# --- BEGIN GENERATED …` / `# --- END GENERATED …`
  markers is rewritten. Everything else is hand-pinned.
- Hand-pinned ids (Gemini/Groq/Cerebras/NIM) are **validated, never edited**:
  the script warns if a pinned id has vanished from a provider's `/models`
  endpoint (only for providers whose key is present).
- Output is deterministic and byte-idempotent (no timestamps), so `--check` in
  cron is meaningful (exit 2 = drift) and `--write` twice is a no-op.
- Security: a redirect handler strips `Authorization` on cross-host redirects,
  and URLs containing `?key=` are never logged verbatim.

CLI: `--check` (default, dry-run diff + validation), `--write`, `--write
--restart`.

## Consequences

- The free-model list stays current without a database and without touching
  hand-curated deployments.
- The generated region is script-owned — a hand edit inside the markers is
  overwritten on the next `--write` (documented in the block header).
- Cron `--check` surfaces upstream deprecations early; a human decides whether to
  replace a pinned model (the script won't silently swap a pinned id).
- If OpenRouter or cheahjs is unreachable, the script degrades gracefully
  (cheahjs is non-fatal; an OpenRouter failure exits non-zero without writing).
