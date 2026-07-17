#!/usr/bin/env python3
"""Refresh the free-tier model list in config.yaml.

Free `:free` models on OpenRouter come and go, so the `openrouter-free`
load-balanced group is *generated* rather than hand-maintained. Everything else
in config.yaml is hand-pinned and only *validated* here (warn, never auto-edit).

What it does
------------
- Regenerates the block between the BEGIN/END GENERATED markers in config.yaml
  with the current tools-capable OpenRouter `:free` models (cross-referenced
  against cheahjs/free-llm-api-resources to catch models OpenRouter hasn't
  flagged free in its own pricing).
- Validates every hand-pinned model id against its provider's /models endpoint
  and WARNS about any that have disappeared (Groq/Cerebras/Gemini/NVIDIA
  deprecate aggressively). It never rewrites pinned entries.

No third-party dependencies (stdlib only) and no database — the block is written
straight into config.yaml, so it works with the DB-less default deployment.

Usage
-----
  python3 scripts/refresh_models.py --check            # dry run: diff + validation (default)
  python3 scripts/refresh_models.py --write            # rewrite the generated block
  python3 scripts/refresh_models.py --write --restart  # ...and `docker compose restart litellm` if it changed

Exit codes: 0 = clean, 2 = drift/missing found (useful for cron `--check`), 1 = error.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

MARKER_BEGIN = "# --- BEGIN GENERATED: openrouter-free (managed by scripts/refresh_models.py — DO NOT EDIT) ---"
MARKER_END = "# --- END GENERATED: openrouter-free ---"

# Ranking hint only (never a hard filter): prefer strong agentic/reasoning
# families when trimming to --limit. Order = priority.
PREFERRED_FAMILIES = ["nemotron", "gpt-oss", "qwen", "llama", "gemma"]

DEFAULT_CONFIG = os.path.join(os.path.dirname(__file__), "..", "config.yaml")


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
class NoAuthRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Drop the Authorization header when a redirect crosses to another host,
    so a provider key is never leaked to an unexpected origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and _host(newurl) != _host(req.full_url):
            new.headers.pop("Authorization", None)
            new.headers.pop("authorization", None)
        return new


def _host(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc


_OPENER = urllib.request.build_opener(NoAuthRedirectHandler())


def http_get_json(url: str, headers: dict | None = None, timeout: int = 20):
    """GET JSON. Returns parsed body, or raises. Never prints URLs verbatim
    (they may contain ?key=... for Gemini)."""
    req = urllib.request.Request(url, headers=headers or {})
    with _OPENER.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _safe(url: str) -> str:
    """Redact a query string so an API key never lands in logs."""
    return url.split("?")[0] + ("?…" if "?" in url else "")


# --------------------------------------------------------------------------- #
# .env loader (stdlib) — lets this run on the host with no deps
# --------------------------------------------------------------------------- #
def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            # strip trailing inline comments on unquoted values
            val = val.split("  #")[0].strip()
            if key and val:
                os.environ.setdefault(key, val)


# --------------------------------------------------------------------------- #
# OpenRouter free-model discovery
# --------------------------------------------------------------------------- #
def fetch_openrouter_models() -> list[dict]:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    data = http_get_json("https://openrouter.ai/api/v1/models", headers=headers)
    return data.get("data", [])


def filter_openrouter_free(models: list[dict]) -> list[dict]:
    """Keep zero-priced models that support tool calling."""
    out = []
    for m in models:
        pricing = m.get("pricing") or {}
        if str(pricing.get("prompt")) != "0" or str(pricing.get("completion")) != "0":
            continue
        if "tools" not in (m.get("supported_parameters") or []):
            continue
        out.append(m)
    return out


def fetch_cheahjs_free_ids() -> set[str]:
    """Scrape OpenRouter `:free` ids from the cheahjs community list. Non-fatal."""
    url = "https://raw.githubusercontent.com/cheahjs/free-llm-api-resources/main/README.md"
    try:
        req = urllib.request.Request(url)
        with _OPENER.open(req, timeout=20) as resp:
            text = resp.read().decode("utf-8", "replace")
    except Exception as exc:  # network hiccup, rename, etc.
        print(f"  ! cheahjs cross-reference unavailable ({exc}); using OpenRouter API only", file=sys.stderr)
        return set()
    return set(re.findall(r"openrouter\.ai/([^)\"'\s]+:free)", text))


def _family_rank(model_id: str) -> int:
    low = model_id.lower()
    for i, fam in enumerate(PREFERRED_FAMILIES):
        if fam in low:
            return i
    return len(PREFERRED_FAMILIES)


def select_openrouter(api_models: list[dict], cheahjs_ids: set[str], limit: int = 4) -> list[dict]:
    """Union of (a) API-flagged free+tools models and (b) cheahjs `:free` ids that
    also exist in the full API list with tool support. Ranked, deduped, trimmed."""
    by_id = {m["id"]: m for m in api_models}
    free_ids = {m["id"] for m in filter_openrouter_free(api_models)}

    for cid in cheahjs_ids:
        m = by_id.get(cid)
        if m and "tools" in (m.get("supported_parameters") or []):
            free_ids.add(cid)

    chosen = [by_id[i] for i in free_ids if i in by_id]
    chosen.sort(key=lambda m: (_family_rank(m["id"]), -int(m.get("context_length") or 0), m["id"]))
    return chosen[:limit]


def render_block(selected: list[dict]) -> str:
    """Deterministic YAML, column-0-relative (no timestamps => byte-idempotent).
    replace_between_markers() applies the container's base indent uniformly."""
    lines = [
        MARKER_BEGIN,
        "# Populated by:  python3 scripts/refresh_models.py --write",
        "# All entries share model_name `openrouter-free` => one load-balanced group.",
        "# Account cap is 20 RPM / 50 requests-per-day, split as rpm across <=4 entries.",
    ]
    if not selected:
        lines.append("# (no tools-capable :free models found on the last refresh)")
    else:
        share = max(1, 20 // len(selected))
        for m in selected:
            mid = m["id"]
            ctx = int(m.get("context_length") or 131072)
            lines.append("- model_name: openrouter-free")
            lines.append("  litellm_params:")
            lines.append(f"    model: openrouter/{mid}")
            lines.append("    api_key: os.environ/OPENROUTER_API_KEY")
            lines.append(f"    rpm: {share}")
            lines.append(f"  model_info: {{ supports_function_calling: true, max_input_tokens: {ctx} }}")
    lines.append(MARKER_END)
    return "\n".join(lines) + "\n"


def replace_between_markers(text: str, block: str) -> str:
    begin = text.find(MARKER_BEGIN)
    end = text.find(MARKER_END)
    if begin == -1 or end == -1:
        raise SystemExit(f"ERROR: markers not found in config. Expected:\n  {MARKER_BEGIN}\n  {MARKER_END}")
    if text.count(MARKER_BEGIN) != 1 or text.count(MARKER_END) != 1:
        raise SystemExit("ERROR: markers must appear exactly once each.")
    # Preserve leading indentation of the BEGIN marker line.
    line_start = text.rfind("\n", 0, begin) + 1
    indent = text[line_start:begin]
    indented = "".join((indent + ln if ln.strip() else ln) + "\n" for ln in block.rstrip("\n").split("\n"))
    end_line_end = text.find("\n", end)
    end_line_end = len(text) if end_line_end == -1 else end_line_end + 1
    return text[:line_start] + indented + text[end_line_end:]


# --------------------------------------------------------------------------- #
# Pinned-model validators (warn only)
# --------------------------------------------------------------------------- #
def _ids_or_none(fn):
    try:
        return fn()
    except Exception as exc:
        print(f"  ! validation skipped ({exc})", file=sys.stderr)
        return None


def fetch_groq_ids() -> set[str]:
    key = os.environ["GROQ_API_KEY"]
    data = http_get_json("https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {key}"})
    bad = ("whisper", "tts", "guard", "embed")
    return {m["id"] for m in data.get("data", []) if not any(b in m["id"].lower() for b in bad)}


def fetch_cerebras_ids() -> set[str]:
    key = os.environ["CEREBRAS_API_KEY"]
    data = http_get_json("https://api.cerebras.ai/v1/models", {"Authorization": f"Bearer {key}"})
    return {m["id"] for m in data.get("data", [])}


def fetch_gemini_ids() -> set[str]:
    key = os.environ["GEMINI_API_KEY"]
    data = http_get_json(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}")
    return {m["name"].split("/", 1)[-1] for m in data.get("models", [])}


def fetch_nim_ids() -> set[str]:
    key = os.environ["NVIDIA_NIM_API_KEY"]
    base = os.environ.get("NVIDIA_NIM_API_BASE", "https://integrate.api.nvidia.com/v1/").rstrip("/")
    data = http_get_json(f"{base}/models", {"Authorization": f"Bearer {key}"})
    return {m["id"] for m in data.get("data", [])}


PROVIDER_VALIDATORS = {
    "gemini": ("GEMINI_API_KEY", fetch_gemini_ids),
    "groq": ("GROQ_API_KEY", fetch_groq_ids),
    "cerebras": ("CEREBRAS_API_KEY", fetch_cerebras_ids),
    "nvidia_nim": ("NVIDIA_NIM_API_KEY", fetch_nim_ids),
}


def extract_pinned(config_text: str) -> list[tuple[str, str]]:
    """(provider, model_id) for every `model:` line OUTSIDE the generated block
    and not itself a comment."""
    begin = config_text.find(MARKER_BEGIN)
    end = config_text.find(MARKER_END)
    pinned = []
    for m in re.finditer(r"^\s*model:\s*([a-z_]+)/(\S+)", config_text, re.MULTILINE):
        pos = m.start()
        if begin != -1 and end != -1 and begin <= pos <= end:
            continue  # inside generated block
        provider, model_id = m.group(1), m.group(2)
        # ollama etc. have no /models validator; skipped in validate_pinned
        pinned.append((provider, model_id))
    return pinned


def validate_pinned(pinned: list[tuple[str, str]], skip: bool) -> int:
    if skip:
        return 0
    missing = 0
    cache: dict[str, set[str] | None] = {}
    for provider, model_id in pinned:
        if provider not in PROVIDER_VALIDATORS:
            continue
        env_key, fn = PROVIDER_VALIDATORS[provider]
        if not os.environ.get(env_key):
            continue  # no key -> can't validate this provider; silent
        if provider not in cache:
            print(f"  validating {provider} models…")
            cache[provider] = _ids_or_none(fn)
        ids = cache[provider]
        if ids is None:
            continue
        # Gemini ids may be bare (gemini-2.5-flash); NIM/groq ids include a path.
        if model_id not in ids and model_id.split("/")[-1] not in {i.split("/")[-1] for i in ids}:
            print(f"  ⚠ pinned {provider}/{model_id} not found upstream — verify/replace it", file=sys.stderr)
            missing += 1
    return missing


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh the openrouter-free block in config.yaml.")
    ap.add_argument("--check", action="store_true", help="dry run: show diff + validation without writing (default)")
    ap.add_argument("--write", action="store_true", help="rewrite the generated block")
    ap.add_argument("--restart", action="store_true", help="with --write: docker compose restart litellm if the file changed")
    ap.add_argument("--limit", type=int, default=4, help="max openrouter-free entries (default 4)")
    ap.add_argument("--skip-validate", action="store_true", help="skip pinned-model validation")
    ap.add_argument("--config", default=DEFAULT_CONFIG, help="path to config.yaml")
    args = ap.parse_args()

    load_dotenv(os.path.join(os.path.dirname(args.config), ".env"))
    load_dotenv(".env")

    config_path = os.path.abspath(args.config)
    with open(config_path, "r", encoding="utf-8") as fh:
        current = fh.read()

    print(f"Fetching OpenRouter models… ({_safe('https://openrouter.ai/api/v1/models')})")
    try:
        api_models = fetch_openrouter_models()
    except Exception as exc:
        print(f"ERROR: could not fetch OpenRouter models: {exc}", file=sys.stderr)
        return 1
    cheahjs = fetch_cheahjs_free_ids()
    selected = select_openrouter(api_models, cheahjs, limit=args.limit)
    print(f"Selected {len(selected)} tools-capable :free model(s):")
    for m in selected:
        print(f"    openrouter/{m['id']}  (ctx {m.get('context_length')})")

    new_block = render_block(selected)
    updated = replace_between_markers(current, new_block)
    changed = updated != current

    # Show the diff of just the generated region.
    diff = "\n".join(difflib.unified_diff(
        current.splitlines(), updated.splitlines(),
        fromfile="config.yaml (current)", tofile="config.yaml (would-be)", lineterm="",
    ))
    if changed and diff:
        print("\n--- generated-block diff ---")
        print(diff)
    else:
        print("\nGenerated block already up to date.")

    missing = validate_pinned(extract_pinned(current), args.skip_validate)

    if args.write:
        if changed:
            with open(config_path, "w", encoding="utf-8") as fh:
                fh.write(updated)
            print(f"\n✓ wrote {config_path}")
            if args.restart:
                print("Restarting litellm…")
                subprocess.run(["docker", "compose", "restart", "litellm"], check=False)
        else:
            print("\nNothing to write.")
        return 2 if missing else 0

    # --check
    if changed or missing:
        print(f"\nDrift detected (block changed={changed}, pinned missing={missing}). Run --write to apply.")
        return 2
    print("\n✓ clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
