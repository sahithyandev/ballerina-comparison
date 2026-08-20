.PHONY: build build-go build-ballerina clean

# Compile time / binary size (plan.md Comparison Metrics). Run `make clean`
# first for a cold-build number; a plain `make build` reuses each
# toolchain's incremental cache.
build: build-go build-ballerina

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

clean:
	rm -rf go/bin ballerina/target
