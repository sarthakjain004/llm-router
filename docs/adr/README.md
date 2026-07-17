# Architecture Decision Records

Why the project is built the way it is. Format: [Michael Nygard's ADR
template](https://github.com/joelparkerhenderson/architecture-decision-record).
One decision per file; supersede rather than rewrite.

| ADR | Decision |
| --- | -------- |
| [0001](0001-litellm-proxy-as-gateway.md) | LiteLLM proxy as the single OpenAI-compatible gateway |
| [0002](0002-two-layer-alias-architecture.md) | Two-layer alias architecture (semantic vs provider-pinned) |
| [0003](0003-provider-fallback-ordering.md) | Provider fallback ordering (renewable before finite) |
| [0004](0004-otel-toggle-sentinel-entrypoint.md) | Env-toggled OpenTelemetry via a sentinel-line entrypoint |
| [0005](0005-postgres-neon-optional.md) | Postgres/Neon logging optional and off by default |
| [0006](0006-generated-openrouter-block.md) | Generated `openrouter-free` block via the refresh script |
| [0007](0007-security-master-key-private-network.md) | Security: master key + private-network binding |
| [0008](0008-pin-explicit-image-tag.md) | Pin an explicit LiteLLM image tag (`v1.92.0`, arm64) |
| [0009](0009-free-provider-admission-criteria.md) | Free-provider admission criteria (recurring-free, no-card, tool-calling, no forced training) |
