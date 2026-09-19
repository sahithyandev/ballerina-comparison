#!/usr/bin/env python3
"""Static comparison (plan.md criterion: LOC / deps, not runtime latency).
Counts source/test/generated LOC and direct+dev+transitive dependency
counts per stack, writes results/static.json. Invoked by `make static`.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# is_test(p) / is_generated(p): p is the file path relative to subdir.
SOURCES = {
    "go": ("go", "*.go", lambda p: p.name.endswith("_test.go"), lambda p: p.name == "api.gen.go"),
    "ballerina": ("ballerina", "*.bal", lambda p: "tests" in p.parts, lambda p: p.name == "types.bal"),
    "python": ("python", "*.py", lambda p: "tests" in p.parts, lambda p: False),
    "node": ("node", "*.js", lambda p: "test" in p.parts, lambda p: False),
    "bun": ("bun", "*.ts", lambda p: "test" in p.parts, lambda p: False),
    "rust": ("rust/src", "*.rs", lambda p: False, lambda p: False),
    "java": ("java/src", "*.java", lambda p: "test" in p.parts, lambda p: "gen" in p.parts),
}
# rust's test suite lives in rust/tests, a sibling of rust/src, so it isn't
# reachable via SOURCES' single subdir. Handled as a special case in loc().
RUST_TESTS_DIR = "rust/tests"

# Dependency/build-artifact dirs to skip when walking a stack's source tree.
SKIP_DIRS = {"node_modules", ".venv", "target", "bin", "build", ".gradle"}

# Files quoted individually in the README's prose per stack.
COMPONENT_FILES = {
    "go": {"profanity": "go/internal/profanity/profanity.go", "config": "go/internal/config/config.go"},
    "ballerina": {"profanity": "ballerina/profanity.bal", "config": "ballerina/config.bal"},
    "python": {"profanity": "python/profanity.py", "config": "python/config.py"},
    "node": {"profanity": "node/profanity.js", "config": "node/config.js"},
    "bun": {"profanity": "bun/profanity.ts", "config": "bun/config.ts"},
    "rust": {"profanity": "rust/src/profanity.rs", "config": "rust/src/config.rs"},
    "java": {"profanity": "java/src/main/java/blog/Profanity.java", "config": "java/src/main/java/blog/Config.java"},
}


def count(path):
    return sum(1 for _ in path.open())


def loc(stack):
    subdir, pattern, is_test, is_generated = SOURCES[stack]
    hand, test, generated, files = 0, 0, 0, 0
    for path in sorted((ROOT / subdir).rglob(pattern)):
        rel = path.relative_to(ROOT / subdir)
        if SKIP_DIRS & set(rel.parts):
            continue
        n = count(path)
        if is_generated(rel):
            generated += n
        elif is_test(rel):
            test += n
            files += 1
        else:
            hand += n
            files += 1
    if stack == "rust":
        for path in sorted((ROOT / RUST_TESTS_DIR).rglob("*.rs")):
            test += count(path)
            files += 1
    return hand, test, generated, files


def component_lines(stack):
    return {name: count(ROOT / rel) for name, rel in COMPONENT_FILES[stack].items()}


def go_deps():
    text = (ROOT / "go/go.mod").read_text()
    blocks = re.findall(r"require \(([^)]*)\)", text)
    lines = [l for block in blocks for l in block.splitlines() if l.strip()]
    direct = sum(1 for l in lines if "// indirect" not in l)
    transitive = sum(1 for l in lines if "// indirect" in l)
    return direct, transitive, None


def ballerina_deps():
    # "Direct" = non-stdlib Ballerina Central packages actually imported in source
    # (kanushka/sqlite). platform.*.dependency entries are the Java-interop side
    # deps (jbcrypt), reported separately as `java_interop`, same split as the
    # README's "1 (+1 Java interop)" cell. Dependencies.toml is Ballerina-generated
    # and lists every resolved package (kanushka/sqlite plus the ballerina/*
    # stdlib packages it and ballerina/http pull in transitively).
    imports = set()
    for path in (ROOT / "ballerina").glob("*.bal"):
        imports.update(re.findall(r"^import\s+(\w+)/\w+", path.read_text(), re.M))
    direct = sum(1 for org in imports if org != "ballerina")
    java_interop = len(
        re.findall(
            r"\[\[platform\.\w+\.dependency\]\]",
            (ROOT / "ballerina/Ballerina.toml").read_text(),
        )
    )
    total_resolved = len(
        re.findall(r"^\[\[package\]\]", (ROOT / "ballerina/Dependencies.toml").read_text(), re.M)
    )
    transitive = total_resolved - direct
    return direct, transitive, java_interop


def python_deps():
    lines = (ROOT / "python/requirements.txt").read_text().splitlines()
    direct = sum(1 for l in lines if l.strip())
    dev_lines = (ROOT / "python/requirements-dev.txt").read_text().splitlines()
    dev = sum(1 for l in dev_lines if l.strip() and not l.startswith("-r "))
    return direct, None, dev  # no lock file committed, transitive count unavailable


def node_deps():
    pkg = json.loads((ROOT / "node/package.json").read_text())
    direct = len(pkg.get("dependencies", {}))
    dev = len(pkg.get("devDependencies", {})) or None
    lock = json.loads((ROOT / "node/package-lock.json").read_text())
    total = sum(1 for p in lock.get("packages", {}) if p)  # skip "" (root package)
    return direct, total - direct, dev


def bun_deps():
    pkg = json.loads((ROOT / "bun/package.json").read_text())
    direct = len(pkg.get("dependencies", {}))
    dev = len(pkg.get("devDependencies", {})) or None
    lock = (ROOT / "bun/bun.lock").read_text()
    total = len(re.findall(r'^\s*"[^"]+": \[', lock, re.M))
    return direct, total - direct, dev


def rust_deps():
    text = (ROOT / "rust/Cargo.toml").read_text()
    block = re.search(r"\[dependencies\]\n(.*?)(?:\n\[|\Z)", text, re.S).group(1)
    direct = sum(1 for l in block.splitlines() if l.strip())
    total = len(re.findall(r"^name = ", (ROOT / "rust/Cargo.lock").read_text(), re.M))
    return direct, total - direct - 1, None  # -1 for the crate itself


def java_deps():
    # Direct = implementation() lines in build.gradle.kts; dev = test deps.
    # No lock file committed (Gradle doesn't lock by default), so transitive
    # count stays n/a, same as Python.
    text = (ROOT / "java/build.gradle.kts").read_text()
    block = re.search(r"dependencies \{(.*?)\n\}", text, re.S).group(1)
    direct = len(re.findall(r"^\s*implementation\(", block, re.M))
    dev = len(re.findall(r"^\s*test\w+\(", block, re.M))
    return direct, None, dev


DEPS = {
    "go": go_deps,
    "ballerina": ballerina_deps,
    "python": python_deps,
    "node": node_deps,
    "bun": bun_deps,
    "rust": rust_deps,
    "java": java_deps,
}
# name of the deps() 3rd return value, per stack (differs in kind, not just value).
DEPS_EXTRA_LABEL = {
    "go": None,
    "ballerina": "java_interop",
    "python": "dev",
    "node": "dev",
    "bun": "dev",
    "rust": None,
    "java": "dev",
}


def main():
    result = {}
    for stack in SOURCES:
        hand, test, generated, files = loc(stack)
        direct, transitive, extra = DEPS[stack]()
        deps = {"direct": direct, "transitive": transitive}
        label = DEPS_EXTRA_LABEL[stack]
        if label:
            deps[label] = extra
        result[stack] = {
            "lines_of_code": hand,
            "test_lines": test,
            "generated_lines": generated or None,
            "files": files,
            "deps": deps,
            "component_lines": component_lines(stack),
        }

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "static.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {out_path}")
    for stack, m in result.items():
        trans = "n/a" if m["deps"]["transitive"] is None else m["deps"]["transitive"]
        print(
            f"  {stack:10s} lines_of_code={m['lines_of_code']:5d} test_lines={m['test_lines']:5d} "
            f"files={m['files']:2d} deps_direct={m['deps']['direct']:2d} deps_transitive={trans}"
        )


if __name__ == "__main__":
    main()
