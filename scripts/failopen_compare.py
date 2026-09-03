#!/usr/bin/env python3
"""Fail-open tail-latency comparison (plan.md criterion #6). Every stack
checks a new post's body against the profanity stub with a timeout and a
fail-open fallback. This measures what that fallback costs under load:
POST /posts p99 with the stub answering normally, then again with the stub
forced to stall 5s (past the 2s PROFANITY_TIMEOUT) so every write hits the
timeout + fallback path. Writes results/failopen.json.

Automated (unlike loadtest/run.sh) because it needs the stub's /control
toggle flipped mid-run and both processes owned by one script. Same
preconditions as startup_compare.py: `make setup` + `make build`. Needs
`hey` and a Go toolchain (for the stub).
"""
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

from stacks import ROOT, STACKS, stack_env, wait_for_200

TIMEOUT_S = 30
PROFANITY_PORT = 9099
BURST = "8s"
CONCURRENCY = "10"
STALL = "5s"  # > PROFANITY_TIMEOUT (2s), so every write times out and falls open


def free_port(port):
    """SIGKILL whatever is listening on `port` — clears orphans left by an
    earlier interrupted run so the fresh server binds the port we poll."""
    pids = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                          capture_output=True, text=True).stdout.split()
    for pid in pids:
        try:
            os.kill(int(pid), signal.SIGKILL)
        except (ProcessLookupError, ValueError):
            pass
    if pids:
        time.sleep(0.5)


def stop(proc):
    """Terminate a process and any children (go run spawns a compiled child)."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass


def control(state):
    urllib.request.urlopen(urllib.request.Request(
        f"http://localhost:{PROFANITY_PORT}/control",
        data=json.dumps(state).encode(), headers={"Content-Type": "application/json"},
    ), timeout=5).read()


def token(base):
    """Register a throwaway user and return its JWT. Registering rather than
    logging in as a seeded user keeps this independent of seed.sql's bcrypt
    hash (Ballerina's crypto:verifyBcrypt does not accept it)."""
    body = json.dumps({
        "username": f"failopen{int(time.time() * 1000)}",
        "email": f"failopen{int(time.time() * 1000)}@example.com",
        "password": "password12345",
    }).encode()
    req = urllib.request.Request(
        f"{base}/auth/register", data=body, headers={"Content-Type": "application/json"},
    )
    try:
        return json.loads(urllib.request.urlopen(req, timeout=10).read())["token"]
    except urllib.error.HTTPError as e:
        print(f"register failed {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
        raise


def hey_post(base, tok):
    out = subprocess.run(
        ["hey", "-z", BURST, "-c", CONCURRENCY, "-m", "POST",
         "-H", f"Authorization: Bearer {tok}", "-T", "application/json",
         "-d", '{"title":"fail-open load","body":"fail-open body"}',
         f"{base}/posts"],
        capture_output=True, text=True, check=True,
    ).stdout
    rps = re.search(r"Requests/sec:\s+([0-9.]+)", out)
    # hey only prints the "99%% in ..." line once it has enough samples; the
    # stalled runs are too sparse for that, so fall back to Slowest.
    p99 = re.search(r"99%% in ([0-9.]+) secs", out)
    slowest = re.search(r"Slowest:\s+([0-9.]+) secs", out)
    avg = re.search(r"Average:\s+([0-9.]+) secs", out)
    statuses = {c: int(n) for c, n in re.findall(r"\[(\d+)\]\s+(\d+) responses", out)}
    tail = p99 or slowest
    return {
        "rps": round(float(rps.group(1)), 1) if rps else None,
        "avg_ms": round(float(avg.group(1)) * 1000, 1) if avg else None,
        "p99_ms": round(float(p99.group(1)) * 1000, 1) if p99 else None,
        "tail_ms": round(float(tail.group(1)) * 1000, 1) if tail else None,
        "statuses": statuses,
    }


def main():
    free_port(PROFANITY_PORT)
    stub = subprocess.Popen(
        ["go", "run", "."], cwd=ROOT / "mock-profanity-api",
        env={**stack_env(0), "PORT": str(PROFANITY_PORT)},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    result = {}
    try:
        # stub has no GET health route; poll /control until `go run` is up
        for _ in range(60):
            try:
                control({})
                break
            except OSError:
                time.sleep(0.5)
        else:
            print("error: profanity stub never came up", file=sys.stderr)
            sys.exit(1)

        for stack, (subdir, port, cmd, artifact) in STACKS.items():
            cwd = ROOT / subdir
            if not (cwd / artifact).exists():
                print(f"error: {stack}: missing {artifact} — run `make build` first", file=sys.stderr)
                sys.exit(1)

            free_port(port)
            env = {**stack_env(port), "PROFANITY_URL": f"http://localhost:{PROFANITY_PORT}"}
            proc = subprocess.Popen(cmd, cwd=cwd, env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    start_new_session=True)
            base = f"http://localhost:{port}/api/v1"
            try:
                if wait_for_200(f"{base}/posts/1", time.perf_counter() + TIMEOUT_S) is None:
                    print(f"error: {stack}: no 200 from :{port}", file=sys.stderr)
                    sys.exit(1)
                tok = token(base)

                control({})
                normal = hey_post(base, tok)

                control({"delay": STALL})
                stalled = hey_post(base, tok)
                control({})
            finally:
                stop(proc)

            result[stack] = {"profanity_normal": normal, "profanity_stalled": stalled}
    finally:
        stop(stub)

    out_path = ROOT / "results" / "failopen.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {out_path}")
    for stack, m in result.items():
        n, s = m["profanity_normal"], m["profanity_stalled"]
        print(f"  {stack:10s} normal: {n['rps']:8.0f} rps, p99 {n['p99_ms']}ms   "
              f"stalled: {s['rps']:6.1f} rps, avg {s['avg_ms']:.0f}ms, tail {s['tail_ms']}ms")


if __name__ == "__main__":
    main()
