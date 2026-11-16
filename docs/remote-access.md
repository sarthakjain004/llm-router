# Accessing the router from a remote machine (HF Spaces, another cloud VM, …)

How a machine **somewhere else** — a Hugging Face Space, a second cloud VM, a
laptop, a CI runner — can call this llm-router deployment.

> **Verified 2026-07-28** against the live Oracle deployment
> (`129.159.239.116`, endpoint on `127.0.0.1:4000`). The SSH-tunnel path
> (Approach A) was tested end-to-end — health, `/v1/models`, and a real
> `agent-default` completion (served by Gemini) all flow through it. The
> Tailscale path (Approach B) is documented with exact steps but requires a
> one-time change to the box and a Tailscale account, so it is not live-verified
> here.

---

## The security model — read this first

The endpoint is **not public**, by design (CONTEXT invariant 6):

- It binds to `127.0.0.1:4000` on the Oracle box (`BIND_ADDR=127.0.0.1`). Nothing
  on the public internet can reach port 4000 — verified: from off-box,
  `curl http://129.159.239.116:4000/...` fails/hangs.
- The **only** public-facing port is **22 (SSH)**, protected by the key pair
  `~/.ssh/oci_llm_router`.
- Auth to the proxy itself is the **master key** (`LITELLM_MASTER_KEY` in `.env`),
  which agents send as their OpenAI `api_key`.

So "remote access" means **building a private tunnel to the box**, never opening
port 4000 to the world. Two supported ways:

| | Approach A — SSH tunnel | Approach B — Tailscale |
|---|---|---|
| **Best for** | one or few clients you fully control | many clients / HF Spaces / a fleet |
| **Box changes** | none (works today) | install Tailscale + change `BIND_ADDR` |
| **On the remote** | `ssh` + the private key | `tailscaled` + an auth key |
| **Network path** | port-forward over SSH (port 22) | encrypted WireGuard overlay |
| **Verified live** | ✅ yes | ⚠️ documented, not live-tested |

---

## Approach A — SSH forward tunnel (verified, works today)

The remote opens an SSH connection to the box and **forwards a local port** to the
box's `127.0.0.1:4000`. Your app then talks to `localhost` and the traffic tunnels
over SSH.

### A.1 Put the private key on the remote

Copy `~/.ssh/oci_llm_router` (the private key, from your Mac) to the remote machine
— e.g. to `~/.ssh/oci_llm_router` there — and lock it down:

```bash
chmod 600 ~/.ssh/oci_llm_router
```

> Ideally mint a **separate** key per remote so you can revoke one without
> affecting others (see "Hardening" below). Reusing the existing key is fine to
> start.

### A.2 Open the tunnel

```bash
ssh -i ~/.ssh/oci_llm_router \
    -o StrictHostKeyChecking=accept-new \
    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -N -f -L 4000:127.0.0.1:4000 \
    ubuntu@129.159.239.116
```

- `-L 4000:127.0.0.1:4000` — local port 4000 → the box's loopback 4000.
- `-N` — no remote shell, just forwarding. `-f` — background after connecting.
- `ServerAlive*` — detect a dead link and drop, so a supervisor can restart it.

Now the endpoint is reachable **on the remote** at `http://127.0.0.1:4000/v1`.

### A.3 Verify (exactly what was tested)

```bash
MK='<your LITELLM_MASTER_KEY>'

# health (no auth)
curl -fsS http://127.0.0.1:4000/health/liveliness            # -> "I'm alive!"

# models (auth)
curl -fsS -H "Authorization: Bearer $MK" http://127.0.0.1:4000/v1/models

# real completion
curl -fsS -H "Authorization: Bearer $MK" -H "Content-Type: application/json" \
  http://127.0.0.1:4000/v1/chat/completions \
  -d '{"model":"agent-default","messages":[{"role":"user","content":"Reply with exactly: TUNNEL_OK"}],"max_tokens":200}'
# -> {"choices":[{"message":{"content":"TUNNEL_OK"}}], ...}  served by Gemini
```

### A.4 Keep it alive (production)

A bare `ssh -f` dies if the network blips. Use one of:

**autossh (simplest):**
```bash
sudo apt-get install -y autossh          # or: apk add autossh / brew install autossh
autossh -M 0 -f -N \
  -o "ServerAliveInterval=30" -o "ServerAliveCountMax=3" \
  -o "ExitOnForwardFailure=yes" -o "StrictHostKeyChecking=accept-new" \
  -i ~/.ssh/oci_llm_router \
  -L 4000:127.0.0.1:4000 ubuntu@129.159.239.116
```

**systemd unit** (`/etc/systemd/system/llm-router-tunnel.service`) on a VM:
```ini
[Unit]
Description=SSH tunnel to llm-router
After=network-online.target
Wants=network-online.target

[Service]
User=youruser
ExecStart=/usr/bin/ssh -NT \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new \
  -i /home/youruser/.ssh/oci_llm_router \
  -L 4000:127.0.0.1:4000 ubuntu@129.159.239.116
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now llm-router-tunnel
```

---

## Approach B — Tailscale (best for HF Spaces & multiple clients)

A private WireGuard mesh: the box and every client get a stable `100.x.y.z` address
and talk directly, no SSH process to babysit. **Requires a one-time change to the
box** (it currently binds loopback-only).

### B.1 One-time: put the box on your tailnet

On the Oracle box:
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up                       # authenticate; note the 100.x.y.z it prints
```

Then make the endpoint listen on the tailnet interface instead of loopback:
```bash
cd ~/llm-router
sed -i 's/^BIND_ADDR=.*/BIND_ADDR=100.x.y.z/' .env    # the box's tailnet IP
docker compose up -d --force-recreate litellm
```

> This keeps it private — it's now reachable **only** over the tailnet, still never
> on the public internet. (Docker-published ports bypass ufw, so `BIND_ADDR` is the
> real control here — same rule as the README's Oracle section.)

### B.2 On the remote: join the tailnet and call the box

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --authkey=<TS_AUTHKEY>     # a reusable/ephemeral key from the admin console
```
Now reach it directly:
```bash
curl -fsS -H "Authorization: Bearer $MK" http://100.x.y.z:4000/v1/models
```

---

## Hugging Face Spaces — concrete recipe

A Space is an **ephemeral, outbound-only Docker container**. It can't receive
inbound connections, but it *can* dial out — which is exactly what we need (the
Space is a client of the router). Store secrets in **Settings → Variables and
secrets**, never in the repo.

Set these Space **secrets**:
- `LITELLM_MASTER_KEY` — the router's master key
- `OCI_SSH_KEY` — the **contents** of the private key `oci_llm_router` (Approach A), **or**
- `TS_AUTHKEY` — a Tailscale auth key (Approach B)

### Option 1 (recommended for HF): SSH tunnel inside the Space

Use a **Docker Space** with this `Dockerfile`:

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-client autossh && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY start.sh /start.sh
RUN chmod +x /start.sh
CMD ["/start.sh"]
```

`start.sh` — writes the key from the secret, opens the tunnel, then launches the app:
```bash
#!/usr/bin/env bash
set -e
mkdir -p ~/.ssh
printf '%s\n' "$OCI_SSH_KEY" > ~/.ssh/oci_llm_router
chmod 600 ~/.ssh/oci_llm_router

autossh -M 0 -f -N \
  -o "ServerAliveInterval=30" -o "ServerAliveCountMax=3" \
  -o "ExitOnForwardFailure=yes" -o "StrictHostKeyChecking=accept-new" \
  -i ~/.ssh/oci_llm_router \
  -L 4000:127.0.0.1:4000 ubuntu@129.159.239.116

# wait until the tunnel is serving, then start the app
for i in $(seq 1 30); do
  curl -fsS http://127.0.0.1:4000/health/liveliness >/dev/null 2>&1 && break
  sleep 2
done

exec python app.py        # your Space's app; it points at http://127.0.0.1:4000/v1
```

### Option 2: Tailscale userspace inside the Space

Requires Approach B set up on the box first. In the Space, run `tailscaled` in
**userspace** mode (Spaces have no `/dev/net/tun`):
```bash
tailscaled --tun=userspace-networking \
  --socks5-server=localhost:1055 \
  --outbound-http-proxy-listen=localhost:1055 &
tailscale up --authkey="$TS_AUTHKEY" --hostname=hf-space
```
Because it's userspace, route your client through the proxy it exposes:
```bash
export ALL_PROXY=socks5://localhost:1055
export HTTP_PROXY=http://localhost:1055
# then call http://100.x.y.z:4000/v1 (the box's tailnet IP)
```
This proxy nuance is why **Option 1 (SSH tunnel) is simpler for HF** — the app just
uses `localhost:4000` with no proxy env.

### Your Space's client code (either option)

```python
import os
from openai import OpenAI          # or langchain_openai.ChatOpenAI

client = OpenAI(
    base_url="http://127.0.0.1:4000/v1",     # Option 1: localhost via the tunnel
    api_key=os.environ["LITELLM_MASTER_KEY"], # from the Space secret
)
resp = client.chat.completions.create(
    model="agent-default",                    # or "vision" / "long-context"
    messages=[{"role": "user", "content": "hello"}],
    max_tokens=200,                           # keep generous — the primary is a
)                                             # reasoning model; tiny budgets → empty
print(resp.choices[0].message.content)
```
(LangChain: `ChatOpenAI(base_url=..., api_key=..., model="agent-default", max_retries=0)`.)

---

## Hardening (recommended once it works)

- **One key per remote.** On your Mac: `ssh-keygen -t ed25519 -f ~/.ssh/hf_space -N ""`,
  append the `.pub` to the box's `~/.ssh/authorized_keys`, and give the Space only
  that private key. Revoke by deleting its line in `authorized_keys` — no impact on
  other clients.
- **Restrict the forwarded key.** In the box's `authorized_keys`, prefix a client's
  key with `command="",permitopen="127.0.0.1:4000",no-pty,no-agent-forwarding,no-X11-forwarding`
  so that key can *only* forward to the endpoint — no shell, no other ports.
- **Rotate `LITELLM_MASTER_KEY`** if it ever leaks: change it in `.env`,
  `docker compose up -d --force-recreate litellm`, update each client's secret.
- **Tailscale ACLs** (Approach B): scope which tailnet nodes may reach
  `100.x.y.z:4000`.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Connection refused` on `localhost:4000` | Tunnel isn't up. Check the `ssh`/`autossh` process; re-open the tunnel. |
| `curl` to the box's **public** IP:4000 hangs | Expected — it's private. Use the tunnel/tailnet, not the public IP. |
| `401` / `Authentication Error` | Wrong or missing `LITELLM_MASTER_KEY`. It must match the box's `.env`. |
| First request after boot is slow / resets | Cold-boot on the 1 GB micro (swap-slow ~90s). Retry; it self-heals. See `learnings.md`. |
| `content: null` on a short reply | The primary (`gemini-flash-latest`) is a reasoning model; raise `max_tokens`. |
| Tunnel drops periodically | Add `ServerAliveInterval=30` / use `autossh` or the systemd unit above. |
| Permission denied (publickey) | Wrong key or perms. `chmod 600` the key; confirm it's the one whose `.pub` is in the box's `authorized_keys`. |
