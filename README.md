# Ballerina vs Others (Backend API Comparison)

In this repository, I'm comparing the performance, code size, developer ergonomics, and behavior of Ballerina against five other backend stacks.

| Stack     | Framework | Version  |
| --------- | --------- | -------- |
| Ballerina | n/a       | 2201.13+ |
| Go        | n/a       | 1.21+    |
| Python    | FastAPI   | 3.11+    |
| Node.js   | Express   | 22+      |
| Bun       | Elysia    | 1.3+     |
| Rust      | axum      | 1.75+    |

Each one is included in their own directory. Other stacks may be added in the future. Run `make check` to verify the toolchains each stack needs are on PATH.

## What I Built

I (with the help of Claude Code) built the same backend service in all the stacks mentioned above. A blogging platform API with Users, Posts, and Comments.

Here are the common conventions used across all six.

### Domain

- `User`: id, username, email, password_hash
- `Post`: id, author_id, title, body, published, created_at
- `Comment`: id, post_id, author_id, body, created_at

### Conventions

- Base path: `/api/v1`
- Pagination: `?page=&limit=` (1-indexed, default limit 20)
- Passwords: bcrypt
- JWT: HS256, secret + expiry from env vars
- `DELETE /posts/{id}` cascades to comments via SQLite `ON DELETE CASCADE`
- Profanity check: local stub server (go-based) with a toggle to force slow/failing responses

### Endpoints

| Method   | Path                   | Auth             |
| -------- | ---------------------- | ---------------- |
| `POST`   | `/auth/register`       | n/a              |
| `POST`   | `/auth/login`          | n/a              |
| `GET`    | `/posts`               | n/a              |
| `GET`    | `/posts/{id}`          | n/a              |
| `POST`   | `/posts`               | JWT, author-only |
| `PUT`    | `/posts/{id}`          | JWT, author-only |
| `DELETE` | `/posts/{id}`          | JWT, author-only |
| `POST`   | `/posts/{id}/comments` | JWT              |
| `GET`    | `/posts/{id}/comments` | n/a              |

### Explicitly Avoided

- No containerization.
- Multiple worker threads or clusters.
- Multiple connection pooling for database connections.

## Technical Criteria

All stacks are evaluated against the same checklist:

1. **REST CRUD**, posts and comments
2. **Persistence**, SQLite (file-based, zero setup, shared schema)
3. **Input validation**, structured 400s (empty title, bad email, etc.)
4. **Auth**, JWT bearer auth, ownership checks on write endpoints
5. **Error handling**, consistent error envelope, no leaking stack traces
6. **External HTTP call**, profanity-check stub with timeout and graceful fallback
7. **Concurrency**, fan-out on `GET /posts/{id}` (goroutines/workers/asyncio/`Promise.all` in both Node and Bun/tokio in Rust)
8. **Structured logging**
9. **Config via env vars**
10. **Tests**, unit tests plus an integration test against the running service

## Comparison Metrics

For each criterion, the writeup captures:

- Lines of code / files needed
- Stdlib vs external dependency
- Compile-time vs runtime error catching
- Concurrency model (goroutines vs workers)
- Startup time, cold build time, Docker image size
- Directional request latency (simple load test, same hardware, same DB)

These are directional numbers, not rigorous benchmarks.

## Project Structure

```
ballerina-comparison/
├── ballerina/           # Ballerina implementation (bal openapi + kanushka/sqlite + jwt)
├── go/                  # Go implementation (oapi-codegen + chi + modernc.org/sqlite)
├── python/              # Python implementation (FastAPI + uvicorn + stdlib sqlite3)
├── node/                # Node.js implementation (Express + stdlib node:sqlite)
├── bun/                 # Bun implementation (Elysia + stdlib bun:sqlite, TypeScript)
├── rust/                # Rust implementation (axum + rusqlite + tokio)
├── mock-profanity-api/  # Stub server (Go, net/http, no deps)
├── openapi.yaml         # Shared OpenAPI spec (source of truth for every stack)
├── schema.sql           # Shared SQLite schema (users/posts/comments, cascade delete)
├── seed.sql             # Shared deterministic fixture data
├── .env.example         # Shared env var template (copy to .env in each stack dir)
├── plan.md              # Detailed build plan
├── CLAUDE.md            # Working conventions for this repo (e.g. commit style)
└── LICENSE              # MIT
```

The comparison writeup lives in the [Results](#results) section below. See `plan.md` for the full order of work.

## Current Status

All endpoints from the table above are built and verified in all six
stacks. That's full post/comment CRUD, ownership checks on writes,
pagination, structured validation errors, and the profanity check with
timeout and graceful fallback when the stub is down. Each stack has a test
suite covering validation, auth, ownership checks, and the `GET
/posts/{id}` fan-out (see `CLAUDE.md` for how to run each). Load testing is
done, and the comparison writeup is below, in [Results](#results).
Containerization is still pending.

## Getting Started

1. Run `make setup` to copy the env template and create the SQLite file.
2. Install each stack's dependencies (Python venv, npm/bun installs):
   ```bash
   make build
   ```
3. Start the mock profanity-check server:
   ```bash
   make run-mock
   ```
4. Start any stack (or all six, on different `PORT`s, see `.env.example`),
   each in its own terminal:
   ```bash
   make run-go          # or run-ballerina, run-python, run-node, run-bun, run-rust
   ```
5. Smoke-test the vertical slice:
   ```bash
   curl -X POST localhost:8080/api/v1/auth/register \
     -H "Content-Type: application/json" \
     -d '{"username":"carol","email":"carol@example.com","password":"password123"}'

   curl localhost:8080/api/v1/posts/1
   ```

## Results

I ran all of this once each, on my MacBook Air M4. These are directional
numbers from a single load-test session per stack, not a rigorous
benchmark suite. Treat close calls (a few hundred req/s, a few ms) as
noise, not a ranking.

### The short version

Bun and Node win on raw throughput, by a wide margin. Their SQLite driver
runs on a single thread with no locking to coordinate, so there's nothing
to slow them down. Go and Rust win on build and startup time, since both
ship a static binary with nothing to warm up.

Python is the slowest stack here, full stop. Load test, startup, cold
build, all last place, and it has no compile-time checking either. Node
has the smallest codebase. Rust has the largest, but also the strongest
compile-time guarantees.

Ballerina writes the least code per endpoint of the six. It used to have
two ecosystem gaps in this comparison, now it's down to one. SQLite access
still goes through a JDBC wrapper, but bcrypt is native now, via
`ballerina/crypto`, so it needs Java interop for nothing anymore. The
tradeoff is JVM startup time (795ms against Go's 10ms) and the lowest
read-path throughput of the six.

If code size and dependency count matter to you, look at Node or
Ballerina. If speed is what you care about, Bun wins, no contest.

### Lines of code

|                        | Go  | Ballerina | Python | Node | Bun  | Rust |
| ---------------------- | --- | --------- | ------ | ---- | ---- | ---- |
| Hand-written           | 948 | 548       | 647    | 546  | 554  | 1039 |
| Generated from OpenAPI | 800 | 131       | none   | none | none | none |
| Tests                  | 300 | 138       | 173    | 199  | 192  | 265  |

(From `results/static.json`, via `make static`.)

Node is the smallest hand-written stack. Rust is the largest. Go and
Ballerina both generate part of their types from `openapi.yaml`, though
not the same amount. Go's `oapi-codegen` also builds a routing interface,
which is where its 800 generated lines come from. Ballerina's
`bal openapi` only generates the request/response record types, 131
lines. Rust's bigger total comes from hand-writing SQLite row-mappers and
DTO conversions, work that pydantic, TypeBox, and the generated
Go/Ballerina types just do for you.

### Dependencies

|                 | Go  | Ballerina | Python     | Node | Bun        | Rust |
| --------------- | --- | --------- | ---------- | ---- | ---------- | ---- |
| Direct deps     | 7   | 1         | 6 (+1 dev) | 3    | 2 (+2 dev) | 11   |
| Transitive deps | 17  | 34        | n/a        | 80   | 42         | 196  |

(From `results/static.json`, via `make static`. Ballerina's transitive
count is `ballerina/*` stdlib packages pulled in by Central, not a JVM
classpath dump. Python has no committed lock file, so its transitive count
stays n/a.)

Ballerina and Bun need the fewest direct dependencies, one and two.
SQLite and bcrypt are built-ins for both of them now, Ballerina via
`ballerina/crypto` and the `kanushka/sqlite` Central package, Bun via
`bun:sqlite` and `Bun.password`. Rust needs the most, 11 direct and 196
transitive. Its async runtime, HTTP client, TLS, and JSON are all separate
crates that other frameworks just bundle for you.

### Build and startup

|                          | Go           | Ballerina | Python     | Node              | Bun                | Rust        |
| ------------------------ | ------------ | --------- | ---------- | ----------------- | ------------------ | ----------- |
| Cold build/setup time    | 1.5s         | 6.2s      | 5.1s       | 0.4s              | 0.1s               | 42.0s       |
| Output size              | 17.5M binary | 64.0M jar | 41.6M venv | 2.8M node_modules | 39.3M node_modules | 7.7M binary |
| Startup to first request | 10ms\*       | 795ms\*   | 222ms\*    | 82ms\*            | 42ms\*             | 12ms\*      |

(`results/build.json` via `make build-stats`, `results/startup.json` via
`make startup-stats`. Build times delete each stack's build cache first, so
they're cold; toolchain package/registry caches stay warm.)

\*Startup polls every 10ms, so treat sub-20ms numbers (Go, Rust) as "at or
below this measurement's resolution," not exact. Re-running shows real
noise too. One repeat run, with background load still settling from a
build I'd just kicked off, pushed every stack's number up several times
over before it came back down to what's shown here.

Go and Rust start fastest, 10ms and 12ms, since both ship a static binary
with nothing to warm up. Rust's build is by far the slowest at 42s, mostly
spent compiling SQLite and TLS from source. But it produces the smallest
binary of any stack, 7.7M. Ballerina is the slowest to start, 795ms,
because `bal run` boots a JVM. That JVM cost is the real tradeoff for
choosing Ballerina now, not a dependency gap. SQLite and bcrypt are both
native as of the latest commit.

### Memory

Resident set size (RSS) of the server process, sampled once idle just
after startup, then again as its peak during a 10s / 50-concurrent `hey`
burst on `GET /posts/1`.

|                | Go   | Ballerina | Python | Node   | Bun   | Rust |
| -------------- | ---- | --------- | ------ | ------ | ----- | ---- |
| Idle RSS       | 22M  | 186M      | 63M    | 65M    | 48M   | 11M  |
| Under-load RSS | 34M  | 882M      | 73M    | 145M   | 96M   | 20M  |

(`results/memory.json` via `make memory-stats`. Main process only; none of
the six forks workers for this workload. Directional, single run.)

Rust and Go are the tightest, 11–22M idle and barely moving under load.
Ballerina is in a different weight class: a 186M idle JVM that balloons
past 880M under load, 25x Rust's peak, as the JVM trades memory for
throughput it doesn't get to use here. Node's heap grows the most in
relative terms among the JS runtimes (65M to 145M); Bun stays leaner on
both ends. Python barely moves because its single worker never has much
in flight.

### Load test

I ran these with `loadtest/run.sh` and `hey`, same machine, same DB, same
fixture data (see `loadtest/results/`), same duration per stack per
endpoint (30s for GET, 10s for POST). Go, Python, and Node were captured
in one sitting. Bun came in a later session, Rust in a third, Ballerina in
a fourth. So don't read too much into a close cross-session call, like Bun
vs Node or Rust vs Go/Node.

| Stack     | Endpoint          | Req/s | Avg latency | p99    |
| --------- | ----------------- | ----- | ----------- | ------ |
| Go        | `GET /posts/{id}` | 4327  | 11.6ms      | 23.6ms |
| Go        | `POST /posts`     | 4034  | 2.5ms       | 7.4ms  |
| Ballerina | `GET /posts/{id}` | 2698  | 18.5ms      | 29.3ms |
| Ballerina | `POST /posts`     | 3090  | 3.2ms       | 25.6ms |
| Python    | `GET /posts/{id}` | 1440  | 34.7ms      | 44.7ms |
| Python    | `POST /posts`     | 271   | 36.9ms      | 45.6ms |
| Node      | `GET /posts/{id}` | 7849  | 6.4ms       | 11.9ms |
| Node      | `POST /posts`     | 2946  | 3.4ms       | 7.4ms  |
| Bun       | `GET /posts/{id}` | 15274 | 3.3ms       | 6.3ms  |
| Bun       | `POST /posts`     | 3267  | 3.1ms       | 6.6ms  |
| Rust      | `GET /posts/{id}` | 6612  | 7.6ms       | 15.5ms |
| Rust      | `POST /posts`     | 3993  | 2.5ms       | 3.8ms  |

Bun wins reads by a wide margin, 15274 req/s, roughly double Node's and
triple Go's. It's within reach of Go on writes too. Node and Bun run the
identical fan-out code over a synchronous, lock-free SQLite driver on a
single thread. There's nothing to coordinate, so nothing slows them down.

Go, Ballerina, and Rust all dispatch that same fan-out onto multiple
threads, then serialize on the database anyway, whether that's a
connection pool capped at one or an explicit mutex. On a workload this
small, that coordination is pure overhead. Python is the slowest stack on
both routes, especially writes at 271 req/s. A single uvicorn worker
serializes every SQLite call behind a lock, and it shows.

### Type checks, error shapes, and the concurrency illusion

Go, Ballerina, and Rust reject a malformed request body before handler
code even runs, thanks to generated types or `serde`. Python, Node, and
Bun only catch the same errors once a request actually hits them. Bun's
TypeScript layer adds an optional compile-time check (`bun x tsc
--noEmit`), but nothing enforces it at runtime.

All six return the same `{"error": {"code", "message"}}` envelope on
every error response. There's one documented exception. Elysia validates
Bun's request body against its schema before the handler-level auth check
runs, so a request that's both unauthenticated and malformed returns `400
validation_failed` instead of the `401 unauthorized` the other five
return for the same request. Every single-condition case still matches
across all six stacks. Only that simultaneous double-failure edge
differs.

All six fan out three lookups (author, comments, comment authors) on
`GET /posts/{id}` and join the results. Goroutines in Go, named workers in
Ballerina, `asyncio.gather` in Python, `Promise.all` in Node and Bun,
`tokio::join!` in Rust. Go and Ballerina are the only two where that
fan-out is actually parallel end to end, a pooled connection with no
single lock serializing access. Python, Node, Bun, and Rust each either
run on one thread or serialize behind a lock once the dispatched threads
reach SQLite. Their "concurrency" is real at the dispatch level, but not
at the execution level.

And it doesn't obviously pay off either way. The two stacks with genuine
parallel execution, Go and Ballerina, get outrun on this exact route by
Node's and Bun's single-threaded, lock-free version.

### Where each one earns its keep

**Go** is the fastest and cheapest to build. Native SQLite and bcrypt, no
interop needed. It's one of two stacks, with Ballerina, where the fan-out
is actually parallel against the database. The tradeoff is verbosity, the
most of any compiled stack for the safety it buys.

**Ballerina** writes the least boilerplate per endpoint. Built-in HTTP and
JSON binding, worker-based concurrency that reads like straight-line
code, and SQLite plus bcrypt both native now (`kanushka/sqlite`,
`ballerina/crypto`). The cost is JVM startup, 795ms, the slowest of the
six, and the lowest read-path throughput in the load test.

**Python** needs the least code for a working API. FastAPI and pydantic
cover parsing, validation, and serialization for free, and there's no
build step at all. It's also the slowest stack on every load-test number,
from a single worker serializing every SQLite call behind a lock.

**Node** has the smallest codebase overall, and it's the only stack
besides Bun with a fully native SQLite-plus-bcrypt story, at just three
direct dependencies. Second-fastest on reads. No compile-time checking of
any kind though.

**Bun** is the fastest stack under load by a wide margin, roughly double
Node's throughput on identical application code. That traces to
JavaScriptCore and Elysia's router, not anything in the code itself. Same
lack of compile-time enforcement as Node, plus one documented ordering
quirk where schema validation runs ahead of the auth check.

**Rust** ships the smallest binary of the six, and starts within a few ms
of Go. It also has the strongest compile-time guarantees, a missing error
branch is a compile error, not a runtime accident. The build is the
slowest of all, 42s, and on this specific small fan-out it loses the
read-path load test to Node and Bun despite genuinely parallel thread
dispatch. The shared-connection mutex serializes the real work
regardless.
