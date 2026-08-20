#!/usr/bin/env python3
"""Parse hey's text output for one stack's GET/POST runs and (re)write a row
in the shared results table. Called by run.sh after each run; not meant to
be invoked directly.
"""
import re
import sys


def parse(path):
    text = open(path).read()

    def grab(label):
        m = re.search(rf"{label}:\s+([0-9.]+) secs", text)
        return m.group(1) if m else "?"

    reqs_per_sec = re.search(r"Requests/sec:\s+([0-9.]+)", text)
    statuses = re.findall(r"\[(\d+)\]\s+(\d+) responses", text)
    return {
        "total": grab("Total"),
        "slowest": grab("Slowest"),
        "fastest": grab("Fastest"),
        "avg": grab("Average"),
        "rps": reqs_per_sec.group(1) if reqs_per_sec else "?",
        "statuses": ", ".join(f"{code}x{count}" for code, count in statuses),
    }


def row(label, endpoint, m):
    return (
        f"| {label} | {endpoint} | {m['rps']} | {m['avg']}s | {m['fastest']}s | "
        f"{m['slowest']}s | {m['total']}s | {m['statuses']} |"
    )


def main():
    label, get_path, post_path, summary_path = sys.argv[1:5]
    new_rows = [
        row(label, "GET /posts/{id}", parse(get_path)),
        row(label, "POST /posts", parse(post_path)),
    ]

    header = (
        "| Stack | Endpoint | Req/s | Avg | Fastest | Slowest | Total | Status codes |\n"
        "|---|---|---|---|---|---|---|---|\n"
    )

    try:
        existing = open(summary_path).read()
    except FileNotFoundError:
        existing = header

    lines = [l for l in existing.splitlines() if l.strip()]
    if not lines:
        lines = header.splitlines()

    # Drop any prior rows for this label so reruns replace, not duplicate.
    kept = [l for l in lines if not l.startswith(f"| {label} |")]
    kept.extend(new_rows)

    with open(summary_path, "w") as f:
        f.write("\n".join(kept) + "\n")


if __name__ == "__main__":
    main()
