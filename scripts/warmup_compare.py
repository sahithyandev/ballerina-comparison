#!/usr/bin/env python3
"""Cold-start warm-up comparison. startup_compare.py measures time to the
*first* 200; this measures how long the stack stays slow after that. Right
after the first 200 it fires N sequential GET /posts/1 requests, timing
each, and compares p99/avg of the first 100 against the last 100 — the
JIT/VM warm-up (or import-cost amortization) that the steady-state load
test never sees. Writes results/warmup.json. Invoked by `make warmup-stats`.

Same preconditions as startup_compare.py: `make setup` + `make build`.
Sequential on purpose: one client, one connection, a clean per-request
timeline that `hey` can't give.
"""
import json
import subprocess
import sys
import time
import urllib.request

from stacks import ROOT, STACKS, stack_env, wait_for_200

TIMEOUT_S = 30
N_REQUESTS = 600
WINDOW = 100


def pctl(values, p):
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * len(s))))]


def summarize(samples_ms):
    return {
        "avg_ms": round(sum(samples_ms) / len(samples_ms), 1),
        "p99_ms": round(pctl(samples_ms, 99), 1),
    }


def main():
    result = {}
    for stack, (subdir, port, cmd, artifact) in STACKS.items():
        cwd = ROOT / subdir
        if not (cwd / artifact).exists():
            print(f"error: {stack}: missing {artifact} — run `make build` first", file=sys.stderr)
            sys.exit(1)

        url = f"http://localhost:{port}/api/v1/posts/1"
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=stack_env(port),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            if wait_for_200(url, time.perf_counter() + TIMEOUT_S) is None:
                print(f"error: {stack}: no 200 from :{port} within {TIMEOUT_S}s", file=sys.stderr)
                sys.exit(1)

            samples = []
            for _ in range(N_REQUESTS):
                t0 = time.perf_counter()
                urllib.request.urlopen(url, timeout=5).read()
                samples.append((time.perf_counter() - t0) * 1000)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

        result[stack] = {
            "first_100": summarize(samples[:WINDOW]),
            "last_100": summarize(samples[-WINDOW:]),
            "n_requests": N_REQUESTS,
        }

    out_path = ROOT / "results" / "warmup.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {out_path}")
    for stack, m in result.items():
        f, l = m["first_100"], m["last_100"]
        print(f"  {stack:10s} first100 p99={f['p99_ms']:6.1f}ms  last100 p99={l['p99_ms']:6.1f}ms")


if __name__ == "__main__":
    main()
