#!/usr/bin/env python3
"""Memory comparison. Starts each stack's already-built artifact, samples
its resident set size (RSS) once idle, then again while a `hey` load burst
runs against GET /posts/1, and writes results/memory.json. Invoked by
`make memory-stats`.

Same preconditions as startup_compare.py: `make setup` + `make build`
first. Measures the main server process only (none of the six forks
worker processes for this workload); the number is directional, like the
rest of the Results section.
"""
import json
import subprocess
import sys
import time

from stacks import ROOT, STACKS, stack_env, wait_for_200

TIMEOUT_S = 30
IDLE_SETTLE_S = 2
LOAD_DURATION_S = 10
LOAD_CONCURRENCY = 50


def rss_mb(pid):
    """Main-process RSS in MiB, via ps (KiB on macOS and Linux)."""
    out = subprocess.check_output(["ps", "-o", "rss=", "-p", str(pid)], text=True).strip()
    return round(int(out) / 1024, 1)


def sample_max(pid, seconds, interval=0.5):
    peak = rss_mb(pid)
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        time.sleep(interval)
        try:
            peak = max(peak, rss_mb(pid))
        except (subprocess.CalledProcessError, ValueError):
            break
    return peak


def main():
    result = {}
    for stack, (subdir, port, cmd, artifact) in STACKS.items():
        cwd = ROOT / subdir
        if not (cwd / artifact).exists():
            print(f"error: {stack}: missing {artifact} — run `make build` first", file=sys.stderr)
            sys.exit(1)

        proc = subprocess.Popen(
            cmd, cwd=cwd, env=stack_env(port),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            if wait_for_200(f"http://localhost:{port}/api/v1/posts/1",
                            time.perf_counter() + TIMEOUT_S) is None:
                print(f"error: {stack}: no 200 from :{port} within {TIMEOUT_S}s", file=sys.stderr)
                sys.exit(1)

            time.sleep(IDLE_SETTLE_S)
            idle = rss_mb(proc.pid)

            load = subprocess.Popen(
                ["hey", "-z", f"{LOAD_DURATION_S}s", "-c", str(LOAD_CONCURRENCY),
                 f"http://localhost:{port}/api/v1/posts/1"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            under_load = sample_max(proc.pid, LOAD_DURATION_S)
            load.wait()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

        result[stack] = {"idle_rss_mb": idle, "under_load_rss_mb": under_load}

    out_path = ROOT / "results" / "memory.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {out_path}")
    for stack, m in result.items():
        print(f"  {stack:10s} idle={m['idle_rss_mb']:7.1f}MiB  under_load={m['under_load_rss_mb']:7.1f}MiB")


if __name__ == "__main__":
    main()
