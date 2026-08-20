.PHONY: build build-go build-ballerina build-python build-node build-bun build-rust clean

# Compile time / binary size (plan.md Comparison Metrics). Run `make clean`
# first for a cold-build number; a plain `make build` reuses each
# toolchain's incremental cache.
build: build-go build-ballerina build-python build-node build-bun build-rust

build-go:
	@mkdir -p go/bin
	@start=$$(date +%s); \
	(cd go && go build -o bin/blog-go .); \
	end=$$(date +%s); \
	size=$$(du -h go/bin/blog-go | cut -f1 | tr -d ' '); \
	echo "go:        $$((end-start))s, $$size"

build-ballerina:
	@start=$$(date +%s); \
	(cd ballerina && bal build >/dev/null); \
	end=$$(date +%s); \
	size=$$(du -h ballerina/target/bin/blog_ballerina.jar | cut -f1 | tr -d ' '); \
	echo "ballerina: $$((end-start))s, $$size"

# Python has no compile step, so "build" here means the closest analogue:
# create a venv and install deps, timed the same way.
build-python:
	@start=$$(date +%s); \
	(cd python && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt); \
	end=$$(date +%s); \
	size=$$(du -sh python/.venv | cut -f1 | tr -d ' '); \
	echo "python:    $$((end-start))s, $$size (venv, no binary)"

# Node has no compile step either — "build" means npm install, timed and
# sized the same way as Python's venv row.
build-node:
	@start=$$(date +%s); \
	(cd node && npm install --no-audit --no-fund -q); \
	end=$$(date +%s); \
	size=$$(du -sh node/node_modules | cut -f1 | tr -d ' '); \
	echo "node:      $$((end-start))s, $$size (node_modules, no binary)"

# Bun has no compile step either — "build" means bun install, timed and
# sized the same way as Node's node_modules row.
build-bun:
	@start=$$(date +%s); \
	(cd bun && bun install >/dev/null); \
	end=$$(date +%s); \
	size=$$(du -sh bun/node_modules | cut -f1 | tr -d ' '); \
	echo "bun:       $$((end-start))s, $$size (node_modules, no binary)"

build-rust:
	@start=$$(date +%s); \
	(cd rust && cargo build --release >/dev/null); \
	end=$$(date +%s); \
	size=$$(du -h rust/target/release/blog-rust | cut -f1 | tr -d ' '); \
	echo "rust:      $$((end-start))s, $$size binary"

clean:
	rm -rf go/bin ballerina/target python/.venv python/**/__pycache__ python/__pycache__ node/node_modules bun/node_modules rust/target
