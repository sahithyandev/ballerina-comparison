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
    blocks = re.findall(r"require \(([^)]*)\)", text)
    lines = [l for block in blocks for l in block.splitlines() if l.strip()]
    direct = sum(1 for l in lines if "// indirect" not in l)
    transitive = sum(1 for l in lines if "// indirect" in l)
    return direct, transitive


def ballerina_deps():
    # platform.*.dependency entries are direct Java interop deps (declared by hand).
    # Dependencies.toml is Ballerina-generated and lists the transitively pulled-in
    # ballerina/* stdlib packages (e.g. http pulls in auth, cache, crypto, ...).
    direct = len(
        re.findall(
            r"\[\[platform\.\w+\.dependency\]\]",
            (ROOT / "ballerina/Ballerina.toml").read_text(),
        )
    )
    transitive = len(
        re.findall(r"^\[\[package\]\]", (ROOT / "ballerina/Dependencies.toml").read_text(), re.M)
    )
    return direct, transitive


def python_deps():
    lines = (ROOT / "python/requirements.txt").read_text().splitlines()
    direct = sum(1 for l in lines if l.strip())
    return direct, None  # no lock file committed, transitive count unavailable


def node_deps():
    pkg = json.loads((ROOT / "node/package.json").read_text())
    direct = len(pkg.get("dependencies", {}))
    lock = json.loads((ROOT / "node/package-lock.json").read_text())
    total = sum(1 for p in lock.get("packages", {}) if p)  # skip "" (root package)
    return direct, total - direct


def bun_deps():
    pkg = json.loads((ROOT / "bun/package.json").read_text())
    direct = len(pkg.get("dependencies", {}))
    lock = (ROOT / "bun/bun.lock").read_text()
    total = len(re.findall(r'^\s*"[^"]+": \[', lock, re.M))
    return direct, total - direct


def rust_deps():
    text = (ROOT / "rust/Cargo.toml").read_text()
    block = re.search(r"\[dependencies\]\n(.*?)(?:\n\[|\Z)", text, re.S).group(1)
    direct = sum(1 for l in block.splitlines() if l.strip())
    total = len(re.findall(r"^name = ", (ROOT / "rust/Cargo.lock").read_text(), re.M))
    return direct, total - direct - 1  # -1 for the crate itself


DEPS = {
    "go": go_deps,
    "ballerina": ballerina_deps,
    "python": python_deps,
    "node": node_deps,
    "bun": bun_deps,
    "rust": rust_deps,
}


def main():
    result = {}
    for stack in SOURCES:
        lines, files = loc(stack)
        direct, transitive = DEPS[stack]()
        result[stack] = {
            "lines_of_code": lines,
            "files": files,
            "deps": {"direct": direct, "transitive": transitive},
        }

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "static.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {out_path}")
    for stack, m in result.items():
        trans = "n/a" if m["deps"]["transitive"] is None else m["deps"]["transitive"]
        print(
            f"  {stack:10s} lines_of_code={m['lines_of_code']:5d} files={m['files']:2d} "
            f"deps_direct={m['deps']['direct']:2d} deps_transitive={trans}"
        )


if __name__ == "__main__":
    main()
