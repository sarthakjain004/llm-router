# 5. Postgres/Neon logging optional and off by default

Date: 2026-07-17
Status: Accepted

## Context

LiteLLM can persist spend logs, virtual keys, budgets, and user/team data to
Postgres. The user wants this available via a Neon free-tier connection string
but **off by default** — the core routing+failover use case needs no database.
LiteLLM's current plain image bundles Prisma and runs migrations automatically
**iff** `DATABASE_URL` is set.

A sharp edge: LiteLLM treats an **empty** `DATABASE_URL=""` as "present," so it
still attempts Prisma migrations and crash-loops if the value is blank.

## Decision

- No local Postgres container. The proxy runs DB-less by default.
- `DATABASE_URL` (and `STORE_MODEL_IN_DB`) ship **commented out** in
  `.env.example`. Enabling = uncomment + paste the Neon pooled connection string
  + `make restart`.
- The compose service uses `env_file: .env` only. `DATABASE_URL` is **never**
  placed in an `environment:` block (which couldn't be disabled without editing
  compose).
- No `database_url`/`store_model_in_db` keys in `config.yaml` — DB config stays
  env-only, read automatically when present.

## Consequences

- Default deploy is simpler and lighter (no DB, no migrations) — ideal for a
  12 GB Always-Free box.
- "Disable" means *comment the line out entirely*; the empty-string footgun is
  called out in `.env.example`, the README, and this ADR.
- Turning it on later is a one-line `.env` change with no schema work (Prisma
  migrates on boot). Neon's pooled endpoint + `sslmode=require` is required.
- Spend tracking / virtual keys / budgets are unavailable until the DB is on —
  acceptable, since the goal is $0 inference, not billing analytics.
