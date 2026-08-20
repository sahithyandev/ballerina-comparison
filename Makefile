STACKS := go ballerina python node bun rust

.PHONY: build build-go build-ballerina build-python build-node build-bun build-rust clean clean-db clean-all \
	env db test test-go test-ballerina test-python test-node test-bun test-rust \
	run-go run-ballerina run-python run-node run-bun run-rust run-mock check static build-stats

# Verify the toolchains each stack needs are on PATH, with versions.
check:
	@ok=1; \
	for c in go bal python3 node bun cargo sqlite3; do \
		if ! command -v $$c >/dev/null 2>&1; then echo "$$c: MISSING"; ok=0; continue; fi; \
		if [ "$$c" = go ]; then v=$$(go version); else v=$$($$c --version 2>&1 | head -1); fi; \
		echo "$$c: $$v"; \
	done; \
	[ $$ok -eq 1 ] || (echo "missing prerequisites above"; exit 1)

setup: env db

# Copy .env.example into every stack dir (skips ones that already have a .env).
env:
	@for s in $(STACKS); do \
		if [ -f $$s/.env ]; then echo "$$s: .env exists, skipping"; \
		else cp .env.example $$s/.env; echo "$$s: created .env"; fi; \
	done

# Create+seed blog.db in every stack dir from the shared schema/seed.
db:
	@for s in $(STACKS); do \
		sqlite3 $$s/blog.db < schema.sql && sqlite3 $$s/blog.db < seed.sql; \
		echo "$$s: db ready"; \
	done

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

clean-build:
	rm -rf go/bin ballerina/target python/.venv python/**/__pycache__ python/__pycache__ node/node_modules bun/node_modules rust/target

# Remove per-stack SQLite databases (leaves .env and installed deps alone).
clean-db:
	@for s in $(STACKS); do rm -f $$s/blog.db; done

clean: clean-build clean-db

# Run one stack in the foreground (each needs its own terminal / `make -j` run).
run-mock:
	cd mock-profanity-api && go run .
run-go:
	cd go && go run .
run-ballerina:
	cd ballerina && bal run .
run-python:
	cd python && .venv/bin/python main.py
run-node:
	cd node && node server.js
run-bun:
	cd bun && bun server.ts
run-rust:
	cd rust && cargo run --release

# Run each stack's test suite, same fail-open env vars as CLAUDE.md documents.
test: test-go test-ballerina test-python test-node test-bun test-rust

test-go:
	cd go && go test ./...
test-ballerina:
	cd ballerina && sqlite3 blog.db < ../schema.sql && \
	JWT_SECRET=test-secret PORT=9099 PROFANITY_URL=http://127.0.0.1:1 bal test
test-python:
	cd python && JWT_SECRET=test-secret PROFANITY_URL=http://127.0.0.1:1 .venv/bin/pytest
test-node:
	cd node && JWT_SECRET=test-secret PROFANITY_URL=http://127.0.0.1:1 npm test
test-bun:
	cd bun && JWT_SECRET=test-secret PROFANITY_URL=http://127.0.0.1:1 bun test
test-rust:
	cd rust && cargo test

# Static comparison (LOC/deps, not runtime) — writes results/static.json.
static:
	@python3 scripts/static_compare.py

# Build comparison (compile time / output size) — writes results/build.json.
# Run `make clean-build` first for cold-build numbers.
build-stats:
	@python3 scripts/build_compare.py
