"""Shared config for the runtime-measurement scripts (startup, memory,
warmup). Each of those starts every stack's already-built artifact the same
way, so the how-to-start table lives here once.
"""
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# base env shared by every stack, same values as .env.example
BASE_ENV = {
    "DB_PATH": "./blog.db",
    "JWT_SECRET": "runtime-stats-secret",
    "JWT_EXPIRY": "24h",
    "PROFANITY_URL": "http://localhost:9090",
    "PROFANITY_TIMEOUT": "2s",
}

# stack -> (cwd, port, command, artifact that `make build` must have produced)
STACKS = {
    "go": ("go", 8080, ["./bin/blog-go"], "bin/blog-go"),
    "ballerina": ("ballerina", 8081, ["java", "-jar", "target/bin/blog_ballerina.jar"], "target/bin/blog_ballerina.jar"),
    "python": ("python", 8082, [".venv/bin/python", "main.py"], ".venv/bin/python"),
    "node": ("node", 8083, ["node", "server.js"], "node_modules"),
    "bun": ("bun", 8084, ["bun", "server.ts"], "node_modules"),
    "rust": ("rust", 8085, ["./target/release/blog-rust"], "target/release/blog-rust"),
}


def stack_env(port):
    return {**os.environ, **BASE_ENV, "PORT": str(port)}


def wait_for_200(url, deadline, poll_interval_s=0.01):
    """Poll url until it returns 200 or the deadline passes. Returns elapsed
    seconds from the call, or None on timeout."""
    start = time.perf_counter()
    while time.perf_counter() < deadline:
        try:
            if urllib.request.urlopen(url, timeout=1).status == 200:
                return time.perf_counter() - start
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(poll_interval_s)
    return None
