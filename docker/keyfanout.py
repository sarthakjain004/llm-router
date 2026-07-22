#!/usr/bin/env python3
"""Auto fan-out model_list deployments across numbered API keys.

For any deployment whose litellm_params.api_key is "os.environ/BASE", create one
load-balanced copy per environment variable named BASE, BASE_2, BASE_3, ... that is
set (non-empty). So adding BASE_2, BASE_3, ... to .env multiplies that provider's
rate limit automatically — no config edits. Runs at container start (entrypoint),
operating on the throwaway /tmp runtime config only (never the mounted source).
"""
import copy
import os
import re
import sys

import yaml


def numbered_keys(base):
    """Return [BASE, BASE_2, BASE_3, ...] for every one that is set & non-empty."""
    keys = [base] if os.environ.get(base) else []
    n = 2
    while os.environ.get(f"{base}_{n}"):
        keys.append(f"{base}_{n}")
        n += 1
    return keys


def main(path):
    with open(path) as fh:
        cfg = yaml.safe_load(fh)
    ml = cfg.get("model_list") or []
    out, fanned = [], {}
    for dep in ml:
        ak = (dep.get("litellm_params") or {}).get("api_key", "") or ""
        m = re.match(r"^os\.environ/(\w+)$", ak)
        keys = numbered_keys(m.group(1)) if m else []
        if not m or len(keys) <= 1:
            out.append(dep)               # not a fan-out candidate, or only 1 key
            continue
        for k in keys:                    # one load-balanced copy per key
            d = copy.deepcopy(dep)
            d["litellm_params"]["api_key"] = f"os.environ/{k}"
            out.append(d)
        fanned[m.group(1)] = len(keys)
    cfg["model_list"] = out
    with open(path, "w") as fh:
        yaml.safe_dump(cfg, fh, sort_keys=False, default_flow_style=False, allow_unicode=True)
    for base, n in sorted(fanned.items()):
        print(f"[keyfanout] {base}: load-balancing across {n} keys")


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    except Exception as exc:              # never block startup on a fan-out issue
        print(f"[keyfanout] skipped ({exc})", file=sys.stderr)
