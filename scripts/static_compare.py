#!/usr/bin/env python3
"""Static comparison (plan.md criterion: LOC / deps, not runtime latency).
Counts source LOC (excluding tests/generated code) and direct dependency
counts per stack, writes results/static.json. Invoked by `make static`.
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SOURCES = {
    "go": ("go", "*.go", lambda p: p.name.endswith("_test.go") or p.name == "api.gen.go"),
    "ballerina": ("ballerina", "*.bal", lambda p: "tests" in p.parts),
    "python": ("python", "*.py", lambda p: "tests" in p.parts),
    "node": ("node", "*.js", lambda p: "test" in p.parts),
    "bun": ("bun", "*.ts", lambda p: "test" in p.parts),
    "rust": ("rust/src", "*.rs", lambda p: False),
}


def loc(stack):
    subdir, pattern, exclude = SOURCES[stack]
    total, files = 0, 0
    for path in sorted((ROOT / subdir).rglob(pattern)):
        if exclude(path.relative_to(ROOT / subdir)):
            continue
        total += sum(1 for _ in path.open())
        files += 1
    return total, files


def go_deps():
    text = (ROOT / "go/go.mod").read_text()
    block = re.search(r"require \(([^)]*)\)", text).group(1)
    return sum(1 for l in block.splitlines() if l.strip() and "// indirect" not in l)


def ballerina_deps():
    text = (ROOT / "ballerina/Ballerina.toml").read_text()
    return len(re.findall(r"\[\[platform\.\w+\.dependency\]\]", text))


def python_deps():
    lines = (ROOT / "python/requirements.txt").read_text().splitlines()
    return sum(1 for l in lines if l.strip())


def package_json_deps(path):
    data = json.loads((ROOT / path).read_text())
    return len(data.get("dependencies", {}))


def rust_deps():
    text = (ROOT / "rust/Cargo.toml").read_text()
    block = re.search(r"\[dependencies\]\n(.*?)(?:\n\[|\Z)", text, re.S).group(1)
    return sum(1 for l in block.splitlines() if l.strip())


DEPS = {
    "go": go_deps,
    "ballerina": ballerina_deps,
    "python": python_deps,
    "node": lambda: package_json_deps("node/package.json"),
    "bun": lambda: package_json_deps("bun/package.json"),
    "rust": rust_deps,
}


def main():
    result = {}
    for stack in SOURCES:
        lines, files = loc(stack)
        result[stack] = {"loc": lines, "files": files, "deps": DEPS[stack]()}

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "static.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {out_path}")
    for stack, m in result.items():
        print(f"  {stack:10s} loc={m['loc']:5d} files={m['files']:2d} deps={m['deps']:2d}")


if __name__ == "__main__":
    main()
