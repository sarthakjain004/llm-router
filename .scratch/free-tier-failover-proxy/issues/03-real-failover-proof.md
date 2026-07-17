# 03 — Prove real (not mocked) failover

Status: ready-for-human

## Why this is open

Acceptance criterion 3 (erroring the primary makes the next provider serve the
request) needs a running stack + keys. `scripts/failover_test.sh` and
`compose.failover.yml` are written but unexecuted.

## Steps to close

1. With a healthy stack (issue 01) and at least `GEMINI_API_KEY` + `GROQ_API_KEY`:
   `make failover`
2. Expect: the poisoned-Gemini run is served by Groq (`groq/...` in the response
   `model` field), the log trail shows fallback/cooldown lines, and the restore
   step returns Gemini.
3. If the serving-model assertion is fuzzy, tighten the `grep` in
   `scripts/failover_test.sh` once the real `model`/`x-litellm-*` values are known.

## Definition of done

`make failover` prints PASS (Groq served the poisoned-Gemini request) and cleanly
restores the healthy stack.
