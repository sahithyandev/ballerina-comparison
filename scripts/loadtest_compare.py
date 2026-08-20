#!/usr/bin/env python3
"""Load test comparison (plan.md criterion: directional request latency).
Parses the committed `loadtest/results/<stack>-{get,post}.txt` files (raw
`hey` output from `loadtest/run.sh`) and writes results/loadtest.json. Runs
offline, no servers needed — it re-derives the README's load-test table from
data already checked in rather than re-running the load test. To capture new
numbers, run `loadtest/run.sh` first, then re-run this script.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "loadtest/results"

STACKS = ["go", "ballerina", "python", "node", "bun", "rust"]
ENDPOINTS = {"get": "GET /posts/{id}", "post": "POST /posts"}


def parse(path):
    text = path.read_text()

    def secs(label):
        m = re.search(rf"{label}:\s+([0-9.]+) secs", text)
        return float(m.group(1)) if m else None

    def pct(p):
        m = re.search(rf"{p}%% in ([0-9.]+) secs", text)
        return round(float(m.group(1)) * 1000, 1) if m else None

    rps = re.search(r"Requests/sec:\s+([0-9.]+)", text)
    statuses = {code: int(n) for code, n in re.findall(r"\[(\d+)\]\s+(\d+) responses", text)}
    return {
        "rps": round(float(rps.group(1)), 1) if rps else None,
        "avg_ms": round(secs("Average") * 1000, 1) if secs("Average") is not None else None,
        "p99_ms": pct(99),
        "duration_s": secs("Total"),
        "statuses": statuses,
    }


def main():
    result = {}
    for stack in STACKS:
        endpoints = {}
        for suffix, name in ENDPOINTS.items():
            path = RESULTS_DIR / f"{stack}-{suffix}.txt"
            if not path.exists():
                continue
            endpoints[name] = parse(path)
        if endpoints:
            result[stack] = endpoints

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "loadtest.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {out_path}")
    for stack, endpoints in result.items():
        for name, m in endpoints.items():
            print(f"  {stack:10s} {name:16s} rps={m['rps']:8.1f} avg={m['avg_ms']:6.1f}ms p99={m['p99_ms']:6.1f}ms")


if __name__ == "__main__":
    main()
