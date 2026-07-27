# Deployment learnings

Operational gotchas hit while deploying llm-router to Oracle Cloud (Always Free,
ap-hyderabad-1) and the fixes that worked. Written 2026-07-27.

---

## 1. The one you just asked about — apt/dpkg lock on a fresh Ubuntu box

### What happened
On a brand-new `VM.Standard.E2.1.Micro` running **Ubuntu 24.04 Minimal**, the very
first `apt-get install docker.io ...` failed repeatedly with:

```
E: Could not get lock /var/lib/dpkg/lock-frontend. It is held by process 1705 (apt-get)
```

Docker/git never installed; only the base `python3` was present.

### Root cause
A fresh Ubuntu instance runs **first-boot automatic apt activity** —
`cloud-init` + `unattended-upgrades` (`apt.systemd.daily`) — for the first several
minutes after boot. That background process (here, **PID 1705**) holds the dpkg
lock. Any concurrent `apt-get install` is locked out.

Two things made it stubborn:
- **A "wait for the lock to be free" poll raced.** `unattended-upgrades` runs in
  phases and *releases and re-acquires* the lock between them. A momentary "lock is
  free" reading was immediately followed by the lock being re-taken before our
  `apt-get install` ran — so the install still failed right after the check passed.
- An earlier attempt also died mid-unpack with `Connection closed by remote host`
  (transient pressure on the tiny box while apt churned). SSH dropping does **not**
  kill the remote apt — it keeps running and keeps holding the lock.

### The fix — one clean approach that works
**Tell apt to wait for the lock itself** instead of failing instantly, so a late
re-grab can't lose the race:
```bash
sudo apt-get -o DPkg::Lock::Timeout=900 update
sudo apt-get -o DPkg::Lock::Timeout=900 install -y docker.io docker-compose-v2 git
```
`DPkg::Lock::Timeout=900` = block up to 15 min for the lock (`-1` = wait forever).
This alone is sufficient and robust.

### A wrong turn worth recording: don't "wait for the apt process to exit"
The tempting fix — poll `pgrep` until apt/unattended-upgrades is gone, *then*
install — **backfired**:
```bash
# DON'T: this never breaks
pgrep -f 'unattended-upgr|...' >/dev/null || break
```
On Ubuntu there's a **persistent** process, `unattended-upgrade-shutdown
--wait-for-signal` (PID ~985), that idles for the entire uptime waiting for a
shutdown signal. A naive `unattended-upgr` grep matches it, so the loop waits the
full timeout for a process that never exits — even though the real lock-holder
(`apt-get`) finished long ago. **Lesson:** don't gate on process presence; let
`DPkg::Lock::Timeout` do the waiting.

### Takeaway
On any freshly-booted Ubuntu cloud instance, **don't `apt install` immediately**.
Wait for `cloud-init`/`unattended-upgrades` to finish *and* pass
`-o DPkg::Lock::Timeout=<n>`. Also remember: a dropped SSH session leaves the
remote command running — reconnect and check state before retrying.

---

## 2. zsh doesn't word-split unquoted variables (broke an SSH call)

### What happened
Stashing SSH flags in a variable and reusing them silently failed:
```bash
SSHO="-i $KEY -o StrictHostKeyChecking=no ..."
ssh $SSHO ubuntu@$IP        # -> "Identity file <whole string> not accessible"
```
The entire `$SSHO` string was handed to `-i` as one filename.

### Root cause
The local shell is **zsh**, which — unlike bash — does **not** perform word
splitting on unquoted parameter expansion. `ssh $SSHO` passed one giant argument
instead of many flags.

### Fix
Pass flags **inline** (what ended up working everywhere), or force zsh splitting
with `${=SSHO}`:
```bash
ssh -i ~/.ssh/oci_llm_router -o StrictHostKeyChecking=no ... ubuntu@$IP
```

---

## 3. OCI API signing keys propagate slowly + intermittently

### What happened
Right after uploading the API public key, `oci` calls returned **intermittent**
`401 NotAuthenticated` — some succeeded, some failed, seemingly at random, for a
few minutes. The launcher even aborted once thinking it was a misconfig.

### Root cause
A freshly-added API key takes time to propagate across OCI's regional service
endpoints (identity authenticated before compute/`iaas` did). During that window
auth flaps.

### Fix
**Probe until auth is stable before relying on it** — require N consecutive
successes against the *specific* service you'll use:
```bash
streak=0
for i in $(seq 1 20); do
  if oci compute image list -c "$COMP" --limit 1 >/dev/null 2>&1; then
    streak=$((streak+1)); [ $streak -ge 3 ] && break
  else streak=0; fi
  sleep 10
done
```
And make retry loops treat `NotAuthenticated`/`401` as **transient/retryable**, not
fatal.

---

## 4. A1 capacity + making the retry launcher actually effective

### What happened
`VM.Standard.A1.Flex` (the Ampere ARM free shape) is chronically **"out of host
capacity"** in single-AD ap-hyderabad-1. The auto-retry launcher is the answer —
but the first version was nearly useless:
- `oci compute instance launch --wait-for-state RUNNING` combined with the SDK's
  **default internal retry** made a single network-timeout call hang **15–18 min**,
  dropping effective capacity checks to ~3/hour.
- A 30s retry interval tripped OCI's `TooManyRequests` rate limit → many "attempts"
  never reached the real capacity check.

### Fix
- **Fail fast:** `--no-retry --connection-timeout 20 --read-timeout 45`, and
  **drop `--wait-for-state` from the hot loop** (wait for RUNNING only *after* a
  successful launch). Calls now return in ~0–1s.
- **Interval 60s**, not 30s — with fail-fast calls that's the sweet spot that stays
  under the launch rate limit, so *every* attempt is a genuine capacity check.
- Retry on capacity / 401 / throttle / 5xx / timeouts; **abort only** on clearly
  fatal errors (`LimitExceeded`, `QuotaExceeded`, `InvalidParameter`, …) so a real
  misconfig doesn't loop forever.

Net: ~3 → ~60 genuine capacity checks/hour.

### Related decision
Rather than wait indefinitely for A1, we launched the always-available x86
**`VM.Standard.E2.1.Micro`** (1 OCPU / **1 GB**) to go live now, and left the A1
launcher running to upgrade later. 1 GB is fine for this **proxy-only** workload
(it does no local inference) — with a **2 GB swap file** added for headroom, and
Open WebUI left disabled.

---

## 5. Config bugs the live tests caught (pre-deploy)

- **Ollama Cloud base URL:** `api.ollama.com/v1` **301-redirects** to
  `ollama.com/v1`, and clients don't re-POST across a 301 → silent failover. Use
  `https://ollama.com/v1`. (`gpt-oss:120b`/`:20b` are free; `deepseek-v4-flash`,
  `kimi-k2.6` are 403 subscription-only.)
- **Cloudflare Workers AI** needs **both** `CLOUDFLARE_API_KEY` *and*
  `CLOUDFLARE_ACCOUNT_ID` — the account ID is baked into the request path
  (`.../accounts/<id>/ai/run/...`), so the token alone can't work. The account ID
  is in the dashboard URL, not the user Profile page.

**Lesson:** live-verify each provider (a real `curl` to the endpoint) before trusting
config — both of these would have silently failed over in production.

---

## 6. litellm cold-boot is memory-heavy → healthcheck flapped on the 1 GB box

### What happened
On the `E2.1.Micro` (954 MB RAM + 2 GB swap) the container came up but was marked
**`unhealthy`**, and the smoke test's first `curl` got `Connection reset by peer`.

### Root cause
Not a crash (`OOMKilled=false`, exit 0). litellm's startup — importing the library
and building the Router from ~20 model deployments — used ~780 MB RAM + **~900 MB
swap**, so it booted *slowly* (~90s to bind `:4000`). The compose healthcheck's
`start_period: 45s` was shorter than the boot, so early probes failed and flipped
the container to `unhealthy`. It **self-healed to `healthy`** on the next probe once
uvicorn was listening — the flag was transient, the proxy was fine.

### Fix
- Bump `start_period` to **180s** in `docker-compose.yml` so a slow boot doesn't get
  flagged. Harmless on fast boxes (it only governs the grace window).
- Keep the **2 GB swap** (section 4) — it's what lets a 1 GB box survive the boot
  spike at all.
- It runs as a **single uvicorn worker** (good — multiple workers would multiply the
  footprint). If memory ever gets tighter, that's the first knob to guard.

### Verified working
All 7 smoke checks passed on the micro: health, model list, **real Gemini chat**,
SSE streaming, **tool calling**, fallback wiring, and the vision/long-context
escape hatches. Endpoint bound to `127.0.0.1:4000` (reach it via SSH tunnel).
