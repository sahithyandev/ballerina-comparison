.PHONY: build build-go build-ballerina build-python clean

# Compile time / binary size (plan.md Comparison Metrics). Run `make clean`
# first for a cold-build number; a plain `make build` reuses each
# toolchain's incremental cache.
build: build-go build-ballerina build-python

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

clean:
	rm -rf go/bin ballerina/target python/.venv python/**/__pycache__ python/__pycache__
