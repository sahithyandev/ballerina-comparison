#!/usr/bin/env python3
"""Startup comparison (plan.md criterion: startup time). Starts each stack's
already-built artifact (not a compile step), polls GET /api/v1/posts/1 until
the first 200, records elapsed time, and writes results/startup.json.
Invoked by `make startup-stats`.

Requires `make setup` (env + db) and `make build` to have run first — this
script does not build anything, so a missing artifact is a clear error, not
a silent rebuild that would leak compile time into the startup number.
"""
import json
import subprocess
import sys
import time

from stacks import ROOT, STACKS, stack_env, wait_for_200

POLL_INTERVAL_S = 0.01
POLL_INTERVAL_MS = POLL_INTERVAL_S * 1000
TIMEOUT_S = 30


def main():
    result = {}
    for stack, (subdir, port, cmd, artifact) in STACKS.items():
        cwd = ROOT / subdir
        if not (cwd / artifact).exists():
            print(f"error: {stack}: missing {artifact} — run `make build` first", file=sys.stderr)
            sys.exit(1)
        if not (cwd / "blog.db").exists():
            print(f"error: {stack}: missing blog.db — run `make setup` first", file=sys.stderr)
            sys.exit(1)

        proc = subprocess.Popen(
            cmd, cwd=cwd, env=stack_env(port),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        start = time.perf_counter()
        try:
            elapsed = wait_for_200(
                f"http://localhost:{port}/api/v1/posts/1", start + TIMEOUT_S, POLL_INTERVAL_S
            )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

        if elapsed is None:
            print(f"error: {stack}: no 200 from :{port} within {TIMEOUT_S}s", file=sys.stderr)
            sys.exit(1)
        result[stack] = {
            "startup_ms": round(elapsed * 1000, 1),
            "poll_interval_ms": POLL_INTERVAL_MS,
        }

    out_path = ROOT / "results" / "startup.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {out_path}")
    for stack, m in result.items():
        print(f"  {stack:10s} startup_ms={m['startup_ms']:.1f}")


if __name__ == "__main__":
    main()
