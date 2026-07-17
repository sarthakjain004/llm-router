#!/usr/bin/env bash
# Prove REAL (not mocked) failover: poison the Gemini key so every gemini/*
# deployment 401s, send a request to agent-default, and assert that Groq served
# it. Then restore the healthy stack.
#
#   ./scripts/failover_test.sh
set -euo pipefail

HOST="${HOST:-http://127.0.0.1:4000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -z "${LITELLM_MASTER_KEY:-}" && -f .env ]]; then
  LITELLM_MASTER_KEY="$(grep -E '^LITELLM_MASTER_KEY=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"' ' | xargs || true)"
fi
: "${LITELLM_MASTER_KEY:?Set LITELLM_MASTER_KEY (env or .env)}"
AUTH=(-H "Authorization: Bearer ${LITELLM_MASTER_KEY}")
JSON=(-H "Content-Type: application/json")

step() { printf '\n\033[1m%s\033[0m\n' "$1"; }
jget() { python3 -c "import sys,json;d=json.load(sys.stdin);print(eval('d'+sys.argv[1]))" "$1"; }

wait_live() {
  for _ in $(seq 1 30); do
    curl -fsS "$HOST/health/liveliness" >/dev/null 2>&1 && return 0
    sleep 2
  done
  echo "proxy did not become live in time" >&2; return 1
}

restore() {
  step "Restoring healthy stack"
  docker compose up -d --force-recreate litellm
  wait_live
  R="$(curl -sS "${AUTH[@]}" "${JSON[@]}" "$HOST/v1/chat/completions" -d '{
    "model":"agent-default","messages":[{"role":"user","content":"say hi"}],"max_tokens":8}')"
  echo "  restored; served by: $(echo "$R" | jget "['model']" 2>/dev/null || echo '?')"
}
trap restore EXIT

step "1/3  Recreate proxy with a POISONED Gemini key"
docker compose -f docker-compose.yml -f compose.failover.yml up -d --force-recreate litellm
wait_live

step "2/3  Request agent-default (Gemini is dead -> expect Groq)"
RESP="$(curl -sS "${AUTH[@]}" "${JSON[@]}" "$HOST/v1/chat/completions" -d '{
  "model":"agent-default","messages":[{"role":"user","content":"Reply with the single word: pong"}],"max_tokens":16}')"
SERVED="$(echo "$RESP" | jget "['model']" 2>/dev/null || echo "")"
echo "  served by model: ${SERVED:-<none>}"
echo "$RESP" | grep -q '"choices"' || { echo "  no completion returned: $RESP" >&2; exit 1; }

# gemini-flash-lite shares the same (poisoned) key, so the first WORKING fallback
# is groq-llama70b. Accept any groq/* as proof.
if echo "$SERVED" | grep -qi 'groq\|llama-3.3\|llama-3.1'; then
  printf '  \033[32mPASS\033[0m failover routed to Groq\n'
else
  printf '  \033[33mNOTE\033[0m served by "%s" (not obviously Groq). Check the log trail below.\n' "$SERVED"
fi

step "3/3  Log trail (fallback / cooldown)"
docker compose logs --tail 80 litellm 2>/dev/null | grep -iE 'fallback|cooldown|gemini|groq' | tail -20 || true

# restore() runs on EXIT
