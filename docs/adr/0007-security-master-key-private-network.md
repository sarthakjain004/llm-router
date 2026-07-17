# 7. Security posture: master key + private-network binding

Date: 2026-07-17
Status: Accepted

## Context

The proxy holds every provider key and can spend (finite) NIM credits, so its
endpoint must not be openly reachable. The deploy target is an Oracle Cloud
Always Free VM. The user reaches it over a private network (Tailscale or SSH
tunnel) and does not want a public HTTPS/reverse-proxy layer in this stack.

A critical platform detail: **docker-published ports bypass `ufw`** on Linux.
Publishing `0.0.0.0:4000` would expose the proxy to the internet regardless of
firewall rules.

## Decision

- **Auth:** require `LITELLM_MASTER_KEY` (`general_settings.master_key`). Agents
  present it as their OpenAI `api_key`. Generate with
  `echo "sk-$(openssl rand -hex 32)"` (Makefile `genkey`).
- **Binding is the firewall:** the compose port mapping is
  `${BIND_ADDR}:4000:4000`. `BIND_ADDR` = `127.0.0.1` locally (reach via SSH
  tunnel) or the box's Tailscale IP (`100.x.y.z`) in prod. Never `0.0.0.0`.
- **No public ingress:** do not open TCP 4000 in the Oracle Security List/NSG;
  leave Oracle Ubuntu's default-REJECT iptables in place.
- **No TLS in-stack:** private-network transport (Tailscale/WireGuard/SSH) is the
  encryption boundary. A public HTTPS variant (Caddy) is explicitly out of scope.
- **No secrets in git:** keys only in `.env` (gitignored); only `.env.example`
  tracked.
- **`/health` is authenticated** (and heavy — it calls every model, spending NIM
  credits); probes use the unauthenticated `/health/liveliness`.

## Consequences

- Attack surface is limited to devices on the tailnet (or with SSH access). Even
  there, the master key gates use.
- The operator must verify non-exposure after deploy (`curl` the public IP:4000
  → must fail) — the bind is the control, and mistakes are silent.
- Losing/leaking the master key means rotating it in `.env` + `make restart` +
  updating agents; provider keys are unaffected.
- If public access is ever needed, that's a new decision (add a reverse proxy
  with TLS + rate limiting) — superseding this ADR, not amending it.
