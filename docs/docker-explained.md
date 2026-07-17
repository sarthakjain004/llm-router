# Docker, explained (for this repo)

A from-scratch walkthrough of the Docker setup in `llm-router`. Assumes you can
program but have never really used Docker. If you already know Docker, the
[README](../README.md) and [ADRs](adr/) have what you need — this file is the
teaching version.

## The mental model (the only two words that matter)

- **Image** — a frozen snapshot of a filesystem plus "what to run." Read-only,
  sits on disk. Like a *class*: a template.
- **Container** — a running instance of an image. Like an *object*: you can start
  many from one image; each has its own memory and a writable scratch layer, but
  all begin from the same snapshot.

Why bother? The image bundles LiteLLM, Python, and every dependency into one
snapshot that runs **identically** on your Mac and on the Oracle ARM box. You
never `pip install litellm` on the server — you run the image. No
"works on my machine."

Everything below is detail on top of those two words.

## The stack has three layers

```
  ┌─ ghcr.io/berriai/litellm:v1.92.0  ← LiteLLM's official image (base). We didn't make this.
  │        ▲ FROM
  ├─ docker/Dockerfile                ← builds OUR thin image: base + OTel deps + our startup script
  │        ▲ build
  └─ docker-compose.yml               ← RUNS our image as a container: wires ports, env, files, restart
```

`docker-compose.yml` is the only thing you run day to day. The Dockerfile is how
the image gets built; compose then starts a container from it.

---

## File 1 — `docker/Dockerfile` (builds the image)

A Dockerfile is a recipe. Each line is a step; Docker runs them top to bottom and
bakes the result into the image.

```dockerfile
ARG LITELLM_TAG=v1.92.0
FROM ghcr.io/berriai/litellm:${LITELLM_TAG}
RUN pip install --no-cache-dir \
    opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
COPY docker/entrypoint.sh /usr/local/bin/llm-router-entrypoint.sh
ENTRYPOINT ["/bin/sh", "/usr/local/bin/llm-router-entrypoint.sh"]
```

- **`ARG LITELLM_TAG=v1.92.0`** — a *build-time* variable (exists only while
  building, not at runtime). Lets us pick the LiteLLM version without editing the
  file; compose passes it in.
- **`FROM ghcr.io/berriai/litellm:${LITELLM_TAG}`** — "start from LiteLLM's
  official image." `ghcr.io` is GitHub's Container Registry (like PyPI/npm, but
  for images). This one line pulls in LiteLLM, Python, and its whole environment.
  We inherit all of it.
- **`RUN pip install …`** — run a command *during the build* and bake the result
  in. We add three OpenTelemetry packages so the OTel export feature works. If the
  base already has them, it's a harmless no-op. **This is the only reason we build
  our own image** instead of using LiteLLM's directly — we needed these packages
  and our startup script.
- **`COPY docker/entrypoint.sh …`** — copy our startup script from the repo *into*
  the image at a fixed path. (`docker/entrypoint.sh` is relative to the "build
  context" — the folder compose sends to the builder, which for us is the repo
  root.)
- **`ENTRYPOINT [...]`** — the command that runs *when a container starts*. We
  override LiteLLM's default startup with our own script (File 2).

Built image = LiteLLM's image + OTel packages + our script as the startup command.

---

## File 2 — `docker/entrypoint.sh` (runs at container startup)

The very first thing that runs when the container starts. Its whole job: prepare
the config, then launch LiteLLM.

```sh
#!/bin/sh
set -eu
SRC="${LITELLM_CONFIG:-/app/config.yaml}"
RUNTIME=/tmp/runtime-config.yaml
cp "$SRC" "$RUNTIME"
if [ "${OTEL_ENABLED:-false}" = "true" ]; then
  sed -i 's/# __OTEL__ //' "$RUNTIME"
  echo "[entrypoint] OTel callback ENABLED ..."
else
  echo "[entrypoint] OTel callback disabled ..."
fi
exec litellm --config "$RUNTIME" --host 0.0.0.0 --port 4000
```

- **`set -eu`** — exit immediately if any command fails (`e`) or an unset variable
  is used (`u`). Fail loud, not silent.
- **`cp "$SRC" "$RUNTIME"`** — copy the config to a scratch file in `/tmp`. Why
  copy? Because the real `config.yaml` is mounted **read-only** (see File 3), and
  we want to *maybe edit* it. So we edit a throwaway copy, never the original.
- **the `if` block** — the OTel toggle ([ADR-0004](adr/0004-otel-toggle-sentinel-entrypoint.md)).
  In `config.yaml` the OTel line is written as a disabled comment:
  `# __OTEL__ callbacks: ["otel"]`. If `OTEL_ENABLED=true`, `sed` deletes the
  `# __OTEL__ ` prefix, turning the comment into a live line. Otherwise it stays a
  comment and OTel never runs. That's how a *config* setting becomes controllable
  by an *env var*.
- **`exec litellm --config … --host 0.0.0.0 --port 4000`** — start LiteLLM's proxy
  server. `exec` *replaces* the shell with the litellm process (so litellm becomes
  the container's main process and receives shutdown signals cleanly).
  `--host 0.0.0.0` means "listen on all interfaces *inside the container*" — normal
  and safe; the container is a sealed box, and what's exposed to the outside world
  is controlled entirely by compose's `ports` (File 3).

---

## File 3 — `docker-compose.yml` (runs the container)

The Dockerfile *builds*; compose *runs*. A YAML description of one container
("service") and how it's wired to your machine.

```yaml
services:
  litellm:                              # our one service
    build:                              # build the image from our Dockerfile...
      context: .                        #   ...using the repo root as build context
      dockerfile: docker/Dockerfile
      args:
        LITELLM_TAG: ${LITELLM_TAG:-v1.92.0}   # feed the ARG; default if .env doesn't set it
    image: llm-router-litellm:${LITELLM_TAG:-v1.92.0}   # name for the built image
    container_name: llm-router          # fixed name (so `docker logs llm-router` works)
    restart: unless-stopped             # auto-restart on crash or reboot
    env_file:
      - .env                            # load all your keys/settings as env vars
    volumes:
      - ./config.yaml:/app/config.yaml:ro   # mount your config INTO the container, read-only
    ports:
      - "${BIND_ADDR:-127.0.0.1}:4000:4000" # expose port 4000 to your machine
    healthcheck:
      test: ["CMD", "python3", "-c", "...urlopen('http://127.0.0.1:4000/health/liveliness')..."]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 45s
```

Each key is a real Docker idea worth knowing:

- **`env_file: .env`** — takes every `KEY=value` in `.env` and injects it as an
  environment variable inside the container. This is how `GEMINI_API_KEY`,
  `LITELLM_MASTER_KEY`, etc. reach LiteLLM. The config references them as
  `os.environ/GEMINI_API_KEY`, so secrets live only in `.env` — never in the image
  or the config file.

- **`volumes: ./config.yaml:/app/config.yaml:ro`** — a **bind mount**. It makes
  your host file `./config.yaml` *appear* inside the container at
  `/app/config.yaml`; `:ro` = read-only from the container's side. The important
  design choice: the config is **not baked into the image** — it's mounted live.
  So you edit `config.yaml` on your Mac, run `make restart`, and the new config
  takes effect **without rebuilding the image**. It's also why the refresh script
  can rewrite `config.yaml` on the host and the container just picks it up on
  restart.

- **`ports: "${BIND_ADDR:-127.0.0.1}:4000:4000"`** — port publishing, read as
  `HOST_IP:HOST_PORT:CONTAINER_PORT`. The container listens on 4000 internally;
  this forwards a port on *your machine* to it. The `BIND_ADDR` prefix is the
  security lever ([ADR-0007](adr/0007-security-master-key-private-network.md)):
  `127.0.0.1` = only your own machine can reach it; on the Oracle box you set it to
  the Tailscale IP so only your private network can. **Never `0.0.0.0`** — published
  Docker ports punch straight through the Linux firewall (ufw), so this bind
  address, not a firewall rule, is what keeps the proxy private.

- **`restart: unless-stopped`** — if the container crashes, or the VM reboots,
  Docker restarts it automatically. No systemd needed. It only *stays* down if you
  explicitly `docker compose down`.

- **`healthcheck`** — Docker runs this little command on a schedule to decide if
  the container is "healthy." Ours asks the proxy's own `/health/liveliness`
  endpoint (unauthenticated and cheap — it doesn't call any provider).
  `start_period: 45s` gives LiteLLM time to boot before failures count. This is
  what makes `docker compose ps` show `healthy` vs `unhealthy`.

- **`${VAR:-default}`** everywhere — standard shell "use `VAR` from `.env`, or this
  default if unset." That's why the stack runs even with a minimal `.env`.

---

## File 4 — `compose.failover.yml` (the override trick)

Compose lets you stack files: `-f base.yml -f override.yml`. Later files *merge on
top of* earlier ones. This one is tiny and exists only for the failover test:

```yaml
services:
  litellm:
    environment:
      GEMINI_API_KEY: sk-invalid-failover-test
```

`environment:` beats `env_file:` when both set the same variable. So the failover
test runs `docker compose -f docker-compose.yml -f compose.failover.yml up …` —
everything identical *except* Gemini's key is deliberately garbage. Every Gemini
call then fails with an auth error, which proves the router really falls through
to Groq (a genuine failure, not a simulation). A clean way to change one thing for
one test without touching your real config.

---

## What `make up` actually does, start to finish

`make up` runs `docker compose up -d --build`:

1. **Build** (`--build`): compose reads the Dockerfile, pulls the LiteLLM base
   image from ghcr.io, runs the `pip install`, copies in `entrypoint.sh`, and
   produces your `llm-router-litellm:v1.92.0` image.
2. **Create the container** from that image, applying everything in compose:
   injects `.env`, bind-mounts `config.yaml`, publishes port 4000 on `BIND_ADDR`.
3. **Start it** (`-d` = detached/background). The container's `ENTRYPOINT` fires →
   `entrypoint.sh` runs → copies the config, maybe flips the OTel line, then
   `exec`s `litellm`, which boots the FastAPI proxy on port 4000.
4. **Health**: Docker polls `/health/liveliness`; after ~45s the container flips to
   `healthy`.

From then on, a request from your agent to
`http://127.0.0.1:4000/v1/chat/completions` hits your host's port 4000 → forwarded
into the container → LiteLLM's router reads the mounted config, picks a provider,
and does the failover logic (all in `litellm/router.py`, upstream — see
[CONTEXT.md → "Where the code actually runs"](../CONTEXT.md#where-the-code-actually-runs)).

---

## The one thing to remember

Two files cross the container boundary as **live mounts/injections**, not baked-in
copies:

- **`config.yaml`** is mounted (read-only) → edit + `make restart`, no rebuild.
- **`.env`** is injected → your secrets never enter the image or git.

Everything else — LiteLLM, Python, OTel deps — is baked into the image and
identical everywhere. That split (immutable image, mutable config/secrets from
outside) is the whole philosophy, and it's why the same image runs unchanged on
your Mac and the Oracle box.

## Command cheat-sheet

| Command | What it does |
| ------- | ------------ |
| `make up` | build the image + start the container in the background |
| `make logs` | tail the proxy's logs |
| `make ps` | show container status (healthy/unhealthy) |
| `make restart` | recreate the container to pick up `.env` / `config.yaml` changes |
| `make down` | stop and remove the container |
| `docker compose build` | rebuild the image only (after changing the Dockerfile or `LITELLM_TAG`) |
| `docker exec -it llm-router sh` | open a shell *inside* the running container to poke around |
