# 3. Provider fallback ordering

Date: 2026-07-17
Status: Accepted

## Context

Five hosted free tiers, each with different strengths and limits:

| Provider | Strength | Binding free-tier constraint |
| -------- | -------- | ---------------------------- |
| Gemini 2.5 Flash | strong reasoning, only free 1M-context, vision | ~10 RPM / 250 RPD / 250K TPM |
| Groq | very fast, reliable tool-calling | 30 RPM but ~100K TPD |
| Cerebras | fastest tokens/sec | only 5 RPM |
| OpenRouter `:free` | widest model choice | 20 RPM / 50 requests/day |
| NVIDIA NIM | 40 RPM (highest), 100+ models | **finite ~1000 credits, non-renewing** |

The user's requested priority is Gemini → Groq → Cerebras → OpenRouter → NIM.
The one genuine question is OpenRouter (50/day) vs NIM ordering.

## Decision

Keep the user's order. The `agent-default` chain is:

```
agent-default: [gemini-flash-lite, groq-llama70b, cerebras-gptoss, openrouter-free, nim-llama]
```

**OpenRouter before NIM**, because OpenRouter's 50 requests/day is a *renewable*
resource that resets daily (unused quota evaporates), whereas NIM's ~1000 credits
are *finite and non-renewing*. Spend the renewable resource first and preserve
the finite one as the true last-resort reserve. NIM's 40 RPM (the highest in the
stack) also makes it the best emergency-burst reserve during multi-provider
outages.

Reordering is a one-line edit: swap the two names in the `agent-default` list.
`vision` and `long-context` have their own shorter chains constrained by
capability (vision-capable models; context-window fallbacks).

## Consequences

- On a normal day, OpenRouter absorbs overflow and NIM credits are barely
  touched — the reserve lasts.
- Downside: on a day when Gemini/Groq/Cerebras are all exhausted, the 50/day
  OpenRouter cap is hit quickly and traffic reaches NIM sooner. Acceptable: that
  is exactly the emergency the reserve exists for.
- `retry_policy.RateLimitErrorRetries: 0` means a 429 goes straight to the next
  tier instead of burning retries on a spent window.
- If the user later does OpenRouter's $10 top-up (1,000/day), no structural
  change is needed — just bump the generated `rpm` split.
