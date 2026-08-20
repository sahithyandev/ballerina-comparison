#!/usr/bin/env python3
"""Build comparison (plan.md criterion: compile time / binary size).
Runs each stack's build/install step, times it, measures output size, and
writes results/build.json. Invoked by `make build-stats`.
"""
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def dir_size(path):
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


# (cwd, build command, output path, is_dir, note)
BUILDS = {
    "go": ("go", ["go", "build", "-o", "bin/blog-go", "."], "bin/blog-go", False, None),
    "ballerina": ("ballerina", ["bal", "build"], "target/bin/blog_ballerina.jar", False, None),
    "python": (
        "python",
        ["bash", "-c", "python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt"],
        ".venv",
        True,
        "venv, no binary",
    ),
    "node": (
        "node",
        ["npm", "install", "--no-audit", "--no-fund", "-q"],
        "node_modules",
        True,
        "node_modules, no binary",
    ),
    "bun": ("bun", ["bun", "install"], "node_modules", True, "node_modules, no binary"),
    "rust": (
        "rust",
        ["cargo", "build", "--release"],
        "target/release/blog-rust",
        False,
        None,
    ),
}


def main():
    result = {}
    for stack, (subdir, cmd, out, is_dir, note) in BUILDS.items():
        cwd = ROOT / subdir
        start = time.perf_counter()
        subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elapsed = time.perf_counter() - start

        out_path = cwd / out
        size = dir_size(out_path) if is_dir else out_path.stat().st_size

        result[stack] = {"build_seconds": round(elapsed, 2), "output_bytes": size}
        if note:
            result[stack]["note"] = note

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "build.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {out_path}")
    for stack, m in result.items():
        mb = m["output_bytes"] / 1_000_000
        extra = f" ({m['note']})" if "note" in m else ""
        print(f"  {stack:10s} build_seconds={m['build_seconds']:6.2f} output={mb:7.2f}MB{extra}")


if __name__ == "__main__":
    main()
