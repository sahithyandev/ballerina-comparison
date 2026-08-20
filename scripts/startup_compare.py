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
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

POLL_INTERVAL_S = 0.01
POLL_INTERVAL_MS = POLL_INTERVAL_S * 1000
TIMEOUT_S = 30

# base env shared by every stack, same values as .env.example
BASE_ENV = {
    "DB_PATH": "./blog.db",
    "JWT_SECRET": "startup-stats-secret",
    "JWT_EXPIRY": "24h",
    "PROFANITY_URL": "http://localhost:9090",
    "PROFANITY_TIMEOUT": "2s",
}

# (cwd, port, command, required artifact relative to cwd)
STACKS = {
    "go": ("go", 8080, ["./bin/blog-go"], "bin/blog-go"),
    "ballerina": ("ballerina", 8081, ["java", "-jar", "target/bin/blog_ballerina.jar"], "target/bin/blog_ballerina.jar"),
    "python": ("python", 8082, [".venv/bin/python", "main.py"], ".venv/bin/python"),
    "node": ("node", 8083, ["node", "server.js"], "node_modules"),
    "bun": ("bun", 8084, ["bun", "server.ts"], "node_modules"),
    "rust": ("rust", 8085, ["./target/release/blog-rust"], "target/release/blog-rust"),
}


def wait_for_200(url, deadline):
    while time.perf_counter() < deadline:
        try:
            if urllib.request.urlopen(url, timeout=1).status == 200:
                return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(POLL_INTERVAL_S)
    return False


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

        env = {**os.environ, **BASE_ENV, "PORT": str(port)}
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        start = time.perf_counter()
        try:
            ok = wait_for_200(f"http://localhost:{port}/api/v1/posts/1", start + TIMEOUT_S)
            elapsed = time.perf_counter() - start
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

        if not ok:
            print(f"error: {stack}: no 200 from :{port} within {TIMEOUT_S}s", file=sys.stderr)
            sys.exit(1)
        result[stack] = {
            "startup_ms": round(elapsed * 1000, 1),
            "poll_interval_ms": POLL_INTERVAL_MS,
        }

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "startup.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {out_path}")
    for stack, m in result.items():
        print(f"  {stack:10s} startup_ms={m['startup_ms']:.1f}")


if __name__ == "__main__":
    main()
