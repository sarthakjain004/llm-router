#!/usr/bin/env bash
# Smoke test for the llm-router proxy: liveness, model list, non-stream chat,
# SSE streaming, tool calling, and a MOCKED fallback proof. Uses curl + python3
# (no jq). Exits non-zero on the first failure.
#
#   HOST=http://127.0.0.1:4000 ./scripts/smoke.sh
set -euo pipefail

HOST="${HOST:-http://127.0.0.1:4000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Master key from env or .env
if [[ -z "${LITELLM_MASTER_KEY:-}" && -f "$ROOT/.env" ]]; then
  LITELLM_MASTER_KEY="$(grep -E '^LITELLM_MASTER_KEY=' "$ROOT/.env" | head -1 | cut -d= -f2- | tr -d '"'"'"' ' | xargs || true)"
fi
: "${LITELLM_MASTER_KEY:?Set LITELLM_MASTER_KEY (env or .env)}"
AUTH=(-H "Authorization: Bearer ${LITELLM_MASTER_KEY}")
JSON=(-H "Content-Type: application/json")

pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; exit 1; }
step() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# python helpers (read stdin)
jget() { python3 -c "import sys,json;d=json.load(sys.stdin);print(eval('d'+sys.argv[1]))" "$1"; }

step "1/7  Health (unauthenticated)"
curl -fsS "$HOST/health/liveliness" >/dev/null && pass "/health/liveliness" || fail "/health/liveliness"
curl -fsS "$HOST/health/readiness"  >/dev/null && pass "/health/readiness"  || fail "/health/readiness"

step "2/7  Model list"
MODELS="$(curl -fsS "${AUTH[@]}" "$HOST/v1/models")"
for m in agent-default vision long-context; do
  echo "$MODELS" | grep -q "\"$m\"" && pass "$m present" || fail "$m missing from /v1/models"
done
echo "$MODELS" | grep -q "openrouter-free" \
  && pass "openrouter-free present" \
  || printf '  \033[33mWARN\033[0m openrouter-free absent (run: python3 scripts/refresh_models.py --write)\n'

step "3/7  Non-streaming chat on agent-default"
RESP="$(curl -sS -D /tmp/llmr_headers.txt "${AUTH[@]}" "${JSON[@]}" "$HOST/v1/chat/completions" -d '{
  "model":"agent-default",
  "messages":[{"role":"user","content":"Reply with exactly the single word: pong"}],
  "max_tokens":16
}')"
CONTENT="$(echo "$RESP" | jget "['choices'][0]['message']['content']" 2>/dev/null || echo "")"
[[ -n "$CONTENT" ]] && pass "got content: ${CONTENT:0:40}" || fail "empty completion: $RESP"
echo "  served by model: $(echo "$RESP" | jget "['model']" 2>/dev/null || echo '?')"
echo "  routing headers:"; grep -i '^x-litellm' /tmp/llmr_headers.txt | sed 's/^/    /' || echo "    (none — confirm header names on your version)"

step "4/7  Streaming (SSE)"
STREAM="$(curl -sSN "${AUTH[@]}" "${JSON[@]}" "$HOST/v1/chat/completions" -d '{
  "model":"agent-default","stream":true,
  "messages":[{"role":"user","content":"Count: one two three"}],"max_tokens":24
}')"
echo "$STREAM" | grep -q '^data: '     && pass "received data: chunks"     || fail "no SSE chunks"
echo "$STREAM" | grep -q '\[DONE\]'    && pass "stream terminated [DONE]"  || fail "no [DONE] terminator"

step "5/7  Tool / function calling"
TOOL="$(curl -sS "${AUTH[@]}" "${JSON[@]}" "$HOST/v1/chat/completions" -d '{
  "model":"agent-default",
  "messages":[{"role":"user","content":"What is the weather in Paris? Use the tool."}],
  "tools":[{"type":"function","function":{"name":"get_weather",
    "description":"Get current weather for a city",
    "parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}],
  "tool_choice":"auto"
}')"
FINISH="$(echo "$TOOL" | jget "['choices'][0]['finish_reason']" 2>/dev/null || echo "")"
if [[ "$FINISH" == "tool_calls" ]]; then
  ARGS="$(echo "$TOOL" | jget "['choices'][0]['message']['tool_calls'][0]['function']['arguments']" 2>/dev/null || echo "")"
  echo "$ARGS" | python3 -c "import sys,json;json.loads(sys.stdin.read())" \
    && pass "tool_calls with valid JSON args: $ARGS" \
    || fail "tool_call args not valid JSON: $ARGS"
else
  printf '  \033[33mWARN\033[0m finish_reason=%s (the serving model may have answered directly)\n' "$FINISH"
fi

step "6/7  Fallback wiring (mock_testing_fallbacks)"
MOCK="$(curl -sS "${AUTH[@]}" "${JSON[@]}" "$HOST/v1/chat/completions" -d '{
  "model":"agent-default","mock_testing_fallbacks":true,
  "messages":[{"role":"user","content":"hi"}],"max_tokens":8
}')"
SERVED="$(echo "$MOCK" | jget "['model']" 2>/dev/null || echo "")"
if echo "$MOCK" | grep -q '"choices"'; then
  pass "fallback path returned a completion (served by: ${SERVED:-?})"
else
  fail "mock fallback did not return a completion: $MOCK"
fi

step "7/7  Escape-hatch aliases"
for alias in vision long-context; do
  R="$(curl -sS "${AUTH[@]}" "${JSON[@]}" "$HOST/v1/chat/completions" -d "{
    \"model\":\"$alias\",\"messages\":[{\"role\":\"user\",\"content\":\"say hi\"}],\"max_tokens\":8}")"
  echo "$R" | grep -q '"choices"' && pass "$alias responded" || fail "$alias failed: $R"
done

printf '\n\033[32mAll smoke checks passed.\033[0m\n'
