# Ballerina vs Others (Backend API Comparison)

In this repository, I am comparing the performance, code size, developer ergonomics, and behavior of Ballerina against other backend stacks. Namely:

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

Here are the common conventions used endpoints across all stacks:

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
stacks: full post/comment CRUD, ownership checks on writes, pagination,
structured validation errors, and the profanity check with timeout and
graceful fallback when the stub is down. Each stack has a test suite
covering validation, auth, ownership checks, and the `GET /posts/{id}`
fan-out (see `CLAUDE.md` for how to run each). Load testing is done and the
comparison writeup is below, in [Results](#results). Containerization is still pending.

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

These results are from one run each, on my personal machine (MacBook Air M4).

### Lines of code

|                        | Go  | Ballerina | Python | Node | Bun  | Rust |
| ---------------------- | --- | --------- | ------ | ---- | ---- | ---- |
| Hand-written           | 948 | 697       | 647    | 546  | 554  | 1039 |
| Generated from OpenAPI | 800 | none      | none   | none | none | none |
| Tests                  | 300 | 138       | 173    | 199  | 192  | 265  |

(From `results/static.json`, via `make static`.)

Go's hand-written number looks small. But `oapi-codegen` generates 800
lines of request/response types and routing interface from
`openapi.yaml` on top of it. Ballerina has no codegen step at all, so
`types.bal` is written by hand — a chunk of what Go gets for free.

Python and Node both come in smaller despite also having no codegen layer.
Python's stdlib `sqlite3` calls plus FastAPI/pydantic's declarative models
cover parsing, validation, and serialization in very little code. Node is
the smallest of all, because Express needs no models file at all. There's
no schema library in the mix, so `app.js` validates request shapes by hand
(same as Go, just without a generated types layer underneath it).

Bun lands almost exactly on Node's total. Its inline `t.Object` schemas
replace every hand-written `if` check, saving lines on validation, but
TypeScript's type annotations add roughly the same number back. A wash,
not a net win.

Rust is the largest hand-written total of the six, though still smaller
than Go's hand-written-plus-generated total (948 + 800 = 1748). `store.rs`
hand-writes a row-mapper per table
(rusqlite has nothing like pydantic's or TypeBox's derive layer), `app.rs`
hand-writes both the wire DTOs and their conversions from store types
(axum has no equivalent to FastAPI's response-model serialization), and
every store call gets wrapped in an explicit `spawn_blocking` call. None
of the dynamic stacks pay that cost. It's Rust's ownership/async model
showing up as boilerplate instead of runtime risk.

### Dependencies

|                 | Go  | Ballerina           | Python     | Node | Bun        | Rust |
| --------------- | --- | ------------------- | ---------- | ---- | ---------- | ---- |
| Direct deps     | 7   | 1 (+1 Java interop) | 6 (+1 dev) | 3    | 2 (+2 dev) | 11   |
| Transitive deps | 17  | 35                  | n/a        | 80   | 42         | 196  |

(From `results/static.json`, via `make static`. Ballerina's transitive
count is `ballerina/*` stdlib packages pulled in by Central, not a JVM
classpath dump. Python has no committed lock file, so its transitive
count stays n/a.)

#### Go

chi, golang-jwt, golang.org/x/crypto (bcrypt), golang.org/x/sync,
modernc.org/sqlite (pure Go, no CGO), plus kin-openapi/oapi-codegen for
the generated layer.

#### Ballerina

One Ballerina Central package, `kanushka/sqlite` (itself a thin wrapper
over `java.jdbc` + `org.xerial:sqlite-jdbc` under the hood — SQLite
access on Ballerina still bottoms out on the JVM, just packaged for
Central instead of hand-rolled). bcrypt still has no route through
Central or `ballerina/crypto` (hash/hmac/AES only), so `org.mindrot:jbcrypt`
via Java interop remains the only option — the sharper of the two
ecosystem gaps now that SQLite has a Central package.

#### Python

fastapi, uvicorn, pydantic, pyjwt, bcrypt, httpx. (`pytest` is dev-only,
kept separate so it doesn't inflate the runtime count.) SQLite needs
nothing beyond the stdlib `sqlite3` module, and bcrypt is one `pip
install` away. Both of the primitives that push Ballerina into Java
interop are trivial here.

#### Node

express, jsonwebtoken, bcryptjs (pure JS, no native compile step).
SQLite needs nothing beyond the stdlib `node:sqlite` module. The
smallest direct-dependency count of any stack besides Bun.

#### Bun

elysia, `@elysiajs/jwt`. Two direct runtime deps, the smallest of any
stack (plus `typescript` and `@types/bun`, dev-only). SQLite and bcrypt
need nothing beyond `bun:sqlite` and `Bun.password`, both built into the
runtime. Neither of Ballerina's two Java-interop primitives costs Bun
so much as a `pip install`.

#### Rust

axum, tokio, serde/serde_json, rusqlite (bundled feature, compiles
SQLite's C source straight into the binary), jsonwebtoken, bcrypt,
reqwest, tracing/tracing-subscriber, futures. 11 direct deps, the most
of any stack. Also the deepest transitive tree, 196 crates, mostly
pulled in by axum/tokio/reqwest's async stack and reqwest's TLS.
Neither SQLite nor bcrypt is a problem here — both compile straight
into the binary. But the crate ecosystem is granular: async runtime,
HTTP client, TLS, and JSON are all separate crates that other
frameworks bundle for you. So a comparable feature set costs more
direct dependencies than Go, even though nothing here is an interop
boundary the way Ballerina's Java calls are.

### Compile-time vs runtime error catching

Go, Ballerina, and Rust catch structural errors (missing field, wrong
type) at compile time, through their type systems or generated bindings.
Rust's `#[derive(Deserialize)]` structs are the strictest of the three.
`serde_json` rejects an unparseable body as a typed `JsonRejection`
before any handler code runs, the same guarantee Go's generated types
give without needing a codegen step.

Python's pydantic models, Node's hand-written checks, and Bun's
`t.Object` schemas all catch the same errors only at runtime, on each
request. No compile step is load-bearing for any of the three, so a typo
in a field name is invisible until a request (or a test) actually
exercises it. Bun sits in an interesting middle spot. TypeScript gives it
an optional compile-time check (`bun x tsc --noEmit`) that Python and
Node lack entirely, but nothing enforces it at runtime. The `t.Object`
schema and the TypeScript type it infers can drift apart, and only the
schema's runtime check actually gates a request.

Semantic validation (empty title, malformed email) is runtime code in
all six, no type system expresses that. Rust's
`req.title.trim().is_empty()` is exactly as much a runtime check as Go's
`strings.TrimSpace`.

For external calls, all six stacks look the same. A typed client call
wrapped in a timeout, with any error, timeout, non-200, or bad body
treated as clean and logged (fail-open), so the profanity stub being
down never blocks a write. Line counts for the client itself are Go 57
lines, Ballerina 21, Python 34, Node 43, Bun 37, Rust 63 (the longest).
Node's and Bun's both use the global `fetch` plus `AbortSignal.timeout`,
built into the runtime, so neither needs an HTTP client dependency at
all, same story as Python's `httpx` minus the extra package. Rust needs
`reqwest` since it has no built-in HTTP client, and its extra length
comes from explicit `CheckRequest`/`CheckResponse` structs plus `match`
arms where the other five just use exceptions or error returns.

None of the six stacks catches a malformed profanity-API response shape
at compile time. All six discover it only at runtime and treat it as
fail-open too.

### Concurrency (`GET /posts/{id}` fan-out)

All six fan out three lookups (author, comments, comment authors) and
join the results:

|                                   | Go                    | Ballerina         | Python                                            | Node                             | Bun                              | Rust                                                                  |
| --------------------------------- | --------------------- | ----------------- | ------------------------------------------------- | -------------------------------- | -------------------------------- | --------------------------------------------------------------------- |
| Mechanism                         | goroutines + errgroup | named workers     | `asyncio.gather`                                  | `Promise.all`                    | `Promise.all`                    | `tokio::join!` / `join_all`                                           |
| DB underneath                     | pooled `*sql.DB`      | pooled JDBC       | sync sqlite3 via `to_thread`                      | sync `node:sqlite`               | sync `bun:sqlite`                | sync rusqlite via `spawn_blocking`, one `Connection` behind a `Mutex` |
| Actually parallel against the DB? | yes                   | yes (JVM threads) | no, thread-pool dispatch serialized behind a lock | no, single JS thread, sequential | no, single JS thread, sequential | no, real OS threads, but serialized behind the mutex                  |

Go uses goroutines plus `golang.org/x/sync/errgroup`, with results
collected via shared vars each goroutine closes over. Ballerina's named
workers read close to sequential code, joined implicitly at function
return or an explicit `wait`.

Python's `asyncio.gather` wraps the sync `sqlite3` store in
`asyncio.to_thread`. There's no async SQLite driver in play, so the
"concurrency" here is thread-pool parallelism dressed in async/await
syntax, not a single-threaded event loop overlapping I/O the way
`asyncio.gather` normally implies.

Node's and Bun's `Promise.all` both wrap a synchronous SQLite store, no
thread pool and no real overlap either, the calls run back to back on
the single JS thread. Of the five it's the most honest about not
actually parallelizing the DB calls, it just doesn't pretend to via
async/await syntax the way Python's version does. Bun's fan-out is
line-for-line the same code as Node's, the concurrency model doesn't
change at all when the runtime underneath does, which is exactly what
makes the load-test numbers below informative.

Rust's `get_post` wraps each store call in `spawn_blocking`, so the
author lookup and comments lookup genuinely run on separate OS threads,
joined via `tokio::join!`, and `attach_authors` fans out one
`spawn_blocking` task per comment via `join_all`, closer in spirit to
Go's goroutines than to Python's thread-pool dressing. But `store::Db` is
a single `rusqlite::Connection` behind a `std::sync::Mutex` (the same
single-writer constraint as Go's `SetMaxOpenConns(1)`, just made
explicit since rusqlite has no pool of its own), so those threads still
queue up one at a time to actually touch SQLite. Genuinely parallel
dispatch, serialized execution. A middle point between Go's pooled
connection (also nominally capped at one, but genuinely parallel in
practice) and Python's honestly-labeled thread-pool-behind-a-lock story.

Go's goroutine and errgroup pattern is the most verbose of the
straightforwardly-concurrent options, but it's the same idiom used for
concurrency everywhere else in the language, not a fan-out-specific
feature, and it's the only one of the six actually running the three
lookups in parallel against the database driver without a mutex in the
way. Rust's version is the most verbose of all six, `call_db` plus
explicit `Result` plumbing around every `spawn_blocking`, but it's the
only one using genuine OS-thread concurrency for the dispatch and being
honest in code, via the mutex, about where that concurrency stops
mattering.

### Startup and build

|                          | Go           | Ballerina | Python     | Node              | Bun                | Rust        |
| ------------------------ | ------------ | --------- | ---------- | ----------------- | ------------------ | ----------- |
| Cold build/setup time    | 1.2s         | 6.7s      | 4.5s       | 0.4s              | <0.1s              | 29.5s       |
| Output size              | 17.5M binary | 64.1M jar | 41.6M venv | 2.8M node_modules | 39.3M node_modules | 7.7M binary |
| Startup to first request | 10ms\*       | 822ms\*   | 209ms\*    | 79ms\*            | 39ms\*             | 14ms\*      |

(`results/build.json` via `make build-stats`, `results/startup.json` via
`make startup-stats`. Build times delete each stack's build cache first, so
they're cold; toolchain package/registry caches stay warm.)

\*Startup polls every 10ms, so treat sub-20ms numbers (Go, Rust) as "at or
below this measurement's resolution," not exact. Re-running shows some
noise, especially on Ballerina and Python (JVM/uvicorn import time) — the
Ballerina number above ranged 800ms–1070ms across runs.

Ballerina is JVM-backed (`bal build` emits a jar, run via `java -jar`),
which explains both the larger output and the slower cold start. Go
compiles to a static native binary.

Python has no build step at all. "Cold build" here is really `pip
install` populating a venv, and "output size" is that venv's size, not a
deployable artifact. Startup is dominated by uvicorn and FastAPI import
time — slower than every stack but Ballerina, despite never touching a
bytecode-compiled runtime.

Node has no build step either, "cold build" is `npm install` populating
`node_modules`, but its tiny dependency count (3 direct packages) makes
both install time and startup among the fastest of any stack.

Bun has no build step, "cold build" is `bun install`, well under a
second even though `bun/node_modules` (39M) is nearly 14x Node's,
almost entirely `jose` pulled in transitively by `@elysiajs/jwt`. Bun's
installer is simply that fast, and its startup comes in about 2x
quicker than Node's in this run.

Rust is the clear outlier on build time. `cargo build --release` (with
Cargo's registry cache warm but `rust/target` removed first) takes
~30s, about 20x Go's, almost entirely LLVM optimizing ~196 transitive
crates. The dependency-tree cost from the earlier table showing up
directly as compile time.

The payoff is a 7.7M static binary, smaller than Go's 17.5M and the
smallest compiled artifact of any stack, and startup within a few ms of
Go's at this measurement's 10ms polling resolution — both near the
floor of what this method can distinguish. No JIT warmup, no bytecode loading,
no runtime import graph to walk. Note that `cargo build` without
`--release` is sub-second once dependencies are compiled once, the same
incremental story as Go. The ~30s number is specifically the optimizing
release build that the load-test and production numbers use.

### Load test

`loadtest/run.sh`, `hey`, same machine, same DB, same fixture data (see
`loadtest/results/`), same duration for every stack on a given endpoint
(30s GET, 10s POST). Go/Python/Node were captured in one sitting,
Bun in a later session, Rust in a third, Ballerina in a fourth (its
first POST capture accidentally ran 20s instead of 10s — recaptured for
duration parity with the rest). Same machine, but not guaranteed
identical background load across sessions, so don't over-read a close
cross-session call (Bun vs Node, Rust vs Go/Node):

| Stack     | Endpoint          | Req/s | Avg latency | p99    | Duration |
| --------- | ----------------- | ----- | ----------- | ------ | -------- |
| Go        | `GET /posts/{id}` | 4327  | 11.6ms      | 23.6ms | 30s      |
| Go        | `POST /posts`     | 4034  | 2.5ms       | 7.4ms  | 10s      |
| Ballerina | `GET /posts/{id}` | 2698  | 18.5ms      | 29.3ms | 30s      |
| Ballerina | `POST /posts`     | 3090  | 3.2ms       | 25.6ms | 10s      |
| Python    | `GET /posts/{id}` | 1440  | 34.7ms      | 44.7ms | 30s      |
| Python    | `POST /posts`     | 271   | 36.9ms      | 45.6ms | 10s      |
| Node      | `GET /posts/{id}` | 7849  | 6.4ms       | 11.9ms | 30s      |
| Node      | `POST /posts`     | 2946  | 3.4ms       | 7.4ms  | 10s      |
| Bun       | `GET /posts/{id}` | 15274 | 3.3ms       | 6.3ms  | 30s      |
| Bun       | `POST /posts`     | 3267  | 3.1ms       | 6.6ms  | 10s      |
| Rust      | `GET /posts/{id}` | 6612  | 7.6ms       | 15.5ms | 30s      |
| Rust      | `POST /posts`     | 3993  | 2.5ms       | 3.8ms  | 10s      |

Node beats Go, Ballerina, and Python on the read path (about 1.8x Go's
req/s), though on writes it now lands behind Go, Rust, Bun, and
Ballerina — Node's single-threaded write path pays a fixed per-request
cost that a fan-out-free write doesn't let it avoid. The read-path win
is the flip side of the concurrency finding above. `node:sqlite`'s
`DatabaseSync` is
synchronous and needs no lock or connection-pool ceremony, there's only
ever one JS thread touching it, and V8's JIT plus Express's thin routing
layer keep per-request overhead low. The same single-threaded model that
made the fan-out "not really concurrent" pays off here by avoiding any
cross-thread coordination cost.

Bun goes further. About 1.9x Node's read-path req/s (15274 vs 7849) and
within reach of Go on writes (3267 vs 4034), running the identical
fan-out code as Node over `Promise.all` and a synchronous SQLite driver.
Since the concurrency model and application code are unchanged between
the two, the gap traces to what's underneath, JavaScriptCore vs V8,
Bun's own HTTP server vs Node's, and Elysia's radix-tree router vs
Express's linear middleware chain. This was the whole reason to add Bun
to the comparison, it isolates how much of Node's single-threaded win
was really about the event-loop model (which Bun keeps) versus V8 and
Express specifically (which Bun replaces). On this measurement, roughly
half the gap between Go and Node's original numbers closes again just
by swapping out those two layers, while the model that makes `GET
/posts/{id}` "not really concurrent" stays exactly the same in both.

Python sits at the other end. `uvicorn` here runs a single worker
process whose event loop dispatches SQLite calls into a bounded thread
pool one at a time behind a lock (mirroring the `SetMaxOpenConns(1)`
constraint Go/Node/Bun share in spirit), so Python's write path in
particular is serialized in a way none of the others are. A
multi-worker uvicorn deployment would likely close some of that gap,
but that's a different, not-yet-measured configuration.

Rust lands between Go and Node on the read path (6612 req/s, faster
than Go's 4327 but well behind Node's 7849 and further still behind
Bun's 15274) while essentially matching Go on writes (3993 vs 4034).
That read-path result is the concurrency finding above showing up
directly. `GET /posts/{id}`'s fan-out dispatches real OS threads via
`spawn_blocking`, but every one of them queues on the same
mutex-guarded connection, and the `spawn_blocking` handoff itself costs
more per request than Node's or Bun's zero-coordination single-threaded
call chain. For a fan-out this small (2-3 lookups per request), the
thread-dispatch overhead outweighs what little the real parallelism
buys back.

The write path tells a different story. `POST /posts` only touches the
database once, so there's no fan-out overhead to pay, and axum's
routing plus a compiled, no-GC request path essentially ties Go, the
two closest-architected stacks in the comparison land within 1% of each
other once the fan-out's thread-handoff tax is gone. The lesson isn't
that Rust is slow, it's that this specific single-connection-behind-a-
mutex fan-out shape is a bad fit for thread-per-lookup dispatch. A
connection pool (rusqlite has none built in, unlike Go's `database/sql`)
or reusing one thread for both lookups would likely close most of this
gap, but that's a different, not-yet-measured configuration, same
caveat as Python's multi-worker uvicorn note above.

### Structured logging and config

|                  | Go                         | Ballerina       | Python            | Node                                      | Bun                                  | Rust                        |
| ---------------- | -------------------------- | --------------- | ----------------- | ----------------------------------------- | ------------------------------------ | --------------------------- |
| Logging          | `log/slog`                 | `ballerina/log` | stdlib `logging`  | `console.log` + hand-rolled JSON          | `console.log` + hand-rolled JSON     | `tracing` (JSON)            |
| Level filtering  | yes, stdlib                | yes, stdlib     | yes, stdlib       | no, no logging library                    | no, no logging library               | yes, crate, not stdlib      |
| Config lines     | 53                         | 41              | 44                | 30                                        | 37                                   | 55                          |
| Duration parsing | stdlib                     | stdlib          | hand-rolled regex | hand-rolled regex                         | hand-rolled regex                    | hand-rolled, no regex crate |
| `.env` loading   | none, shell/CI provides it | none            | none              | none, vars must already be in the process | automatic, Bun loads `.env` from cwd | none, shell/CI provides it  |

All six load config (`JWT_SECRET`, `DB_PATH`, `PORT`, `PROFANITY_URL`,
etc.) from env vars at startup with no framework. No meaningful
difference here, every stack's standard tooling (or, for Rust, its de
facto ecosystem standard) covers this equally well.

One wrinkle. Go and Ballerina parse env-var durations via their stdlib
duration parsers. Neither Python's, Node's, Bun's, nor Rust's stdlib has
an equivalent, so all four hand-roll the same small parser to keep
`.env.example`'s values shared across all six stacks. Rust's skips even
the regex crate Node and Bun reach for, splitting the numeric prefix
from the unit suffix with a plain `str::split_at`, pulling in a whole
regex engine for one duration string felt like the wrong trade for a
systems language.

Node's and Bun's logging are the least polished of the six.
`console.log(JSON.stringify(...))` gets the same structured-field shape
as the others with zero setup, but there's no actual logging library
doing level filtering or output streams the way `log/slog` or Python's
`logging` module do out of the box.

Rust's `tracing` crate is the closest of the non-stdlib options to Go's
`log/slog` in capability, structured fields, levels, a pluggable
subscriber, but like Bun's `@elysiajs/jwt` or Node's `bcryptjs` it's a
crate dependency, not part of Rust's standard library.

Bun is the only stack that reads `.env` on its own. The other five
either rely on the shell/CI to export the variables first, or in Node's
case need an explicit `--env-file` flag. Forgetting that step is the
most common way to hit `config error: JWT_SECRET is required` when
starting Node or Rust by hand.

### Error envelope and ownership checks

Every error response is `{"error": {"code", "message"}}` in all six
stacks, and every post/comment write checks the authenticated user
against the resource's `author_id` before allowing the write, returning
403 on mismatch, with one documented exception in Bun noted below.

|                 | Go                               | Ballerina                        | Python                              | Node                                | Bun                                               | Rust                                    |
| --------------- | -------------------------------- | -------------------------------- | ----------------------------------- | ----------------------------------- | ------------------------------------------------- | --------------------------------------- |
| Error rendering | centralized `internal/httpx.Err` | repeated record literal per site | `ApiError(HTTPException)` + handler | `sendErr` helper + error middleware | centralized `onError` hook + inline `status(...)` | centralized `AppError` + `IntoResponse` |

Go centralizes error rendering in `internal/httpx.Err`. Ballerina
repeats the same record literal shape at each error site in
`openapi_service.bal`, no shared helper. Python raises a small
`ApiError(HTTPException)` subclass with one exception handler that
renders the shared envelope, plus a second handler that remaps
FastAPI's default 422 validation-error shape into the same envelope, a
FastAPI-specific wrinkle none of the other stacks need since none has a
framework-level validation layer of its own to override.

Node centralizes error rendering in a small `sendErr` helper plus an
Express error-handling middleware that catches malformed-JSON body-parse
errors and 500s, similar in spirit to Go's helper but using Express's
trailing `(err, req, res, next)` convention instead of a plain function
call at each site.

Bun centralizes the same three framework-level cases (bad JSON,
unmatched route, uncaught exception) in one `onError` hook keyed on
Elysia's `code`, closer to Go's single-helper story than Python's
two-handler one, while ownership and profanity checks call a `status`
helper inline per site, same shape as Go and Node's early returns. One
real behavioral wrinkle. Elysia validates the request body against its
`t.Object` schema before running any handler code, so a request that's
both unauthenticated and carries an invalid body returns `400
validation_failed` from Bun instead of the `401 unauthorized` the other
four return for the same request. A side effect of schema-first
validation racing ahead of a handler-level auth check, not a missing
check. Every single-condition case matches the other four stacks; only
the simultaneous double-failure edge differs.

Rust centralizes error rendering the most tightly of the six. `AppError`
in `httpx.rs` is a single struct (status, code, message) with one
`IntoResponse` impl that renders the shared envelope, and every handler
returns `Result<Response, AppError>`, so the `?` operator propagates a
mapped error straight out of a handler the same way an early `return`
does in Go. The type system, not convention, enforces that every
fallible path either handles its failure or surfaces it as a
well-formed envelope. There's no way to forget the error branch and 500
with a stack trace by accident the way an unguarded exception could in
Python or Node. No ordering wrinkle like Bun's either, axum runs the
JSON body extractor and the handler as one async function body, so
`require_auth` always executes (and can 401) before the body is even
unwrapped, matching the other four's ordering, not Bun's.

### Where each stack wins

#### Go

Fastest on the write path. About 4x faster cold build than Ballerina. A
smaller, dependency-free static binary. Native SQLite and bcrypt
without leaving the language ecosystem. The only stack whose fan-out
concurrency is genuinely parallel against the DB driver.

#### Ballerina

Worker-based concurrency reads more like straight-line code than
goroutine and errgroup wiring. Less boilerplate per external HTTP call,
a typed client with JSON binding built into the language. Comparable
structured logging and config with no extra ceremony.

#### Python

Smallest hand-written codebase among the non-Node stacks, no codegen
and no compile step at all. SQLite and bcrypt are both trivially
available, stdlib and one `pip install` respectively, exactly the gap
that forces Ballerina to Java interop. Pydantic gives declarative
validation with the least boilerplate per endpoint.

The cost is the weakest runtime story of the six. Slowest on both
load-test paths by a wide margin (mostly from the sync-SQLite-behind-
a-lock constraint colliding with a single-process uvicorn), and, along
with Node, one of two stacks with zero compile-time checking.

#### Node

Smallest hand-written codebase overall. Fewest direct dependencies (3)
of any stack outside Bun, and one of only two stacks where the SQLite
dependency is a zero-install stdlib module. Fast cold build and
startup. Fast on the read path of the load test; on writes it trails
Go, Rust, Bun, and Ballerina.

Its cost mirrors Python's on rigor, no compile-time checking, and its
fan-out concurrency is the least "real" alongside Bun's. A
single-threaded event loop means the three lookups in `GET
/posts/{id}` never actually overlap, they just don't block each other.

#### Bun

Fastest stack in the load test by a wide margin on both paths, about
1.9x Node's read-path req/s and within reach of Go on writes, running
the identical `Promise.all`-over-synchronous-SQLite fan-out code as
Node, so the gap is attributable to JavaScriptCore, Bun's own HTTP
server, and Elysia's router rather than any application-level
difference. Fewest direct runtime dependencies of any stack (2). The
only stack where both SQLite and bcrypt are zero-install built-ins,
closing the exact ecosystem gap that forces Ballerina to Java interop.
`.env` auto-loading needs no flag or dependency, unlike the other four.

The cost is the same as Node's on rigor plus one documented ordering
quirk. Schema validation runs ahead of the handler-level auth check, so
a doubly-invalid request surfaces `validation_failed` instead of
`unauthorized`, and it inherits Node's "least real" fan-out concurrency
for the same single-threaded reason.

#### Rust

Smallest compiled artifact of any stack (7.7M binary, vs Go's 17.5M),
and startup within a few ms of Go's at this measurement's 10ms
resolution. Ties Go on the
write-path load test (3993 vs 4034 req/s) despite genuinely parallel
OS-thread dispatch rather than Go's goroutines. Strongest compile-time
guarantees alongside Go, `serde`-typed request bodies and an
`AppError`-typed `Result` on every handler mean a missing
error-envelope branch is a compile error, not a runtime accident.
SQLite and bcrypt both compile straight into the binary with zero
interop, closing Ballerina's exact ecosystem gap the same way Bun's
built-ins do, just via crates instead of a bundled runtime.

The cost is the most dependency-heavy build of the six (11 direct,
196 transitive) and by far the slowest cold build (~30s, ~20x Go's).
Rust's granular crate ecosystem and LLVM optimization pay for
themselves at startup and runtime, not at compile time. It's also the
one stack where the load test complicates the "real concurrency wins"
story Go tells. `GET /posts/{id}`'s thread-per-lookup dispatch loses to
Node's and Bun's zero-coordination single JS thread on this workload
(6612 req/s vs 7849/15274), because the fan-out is too small for
thread-handoff overhead to pay for itself, and because, like Go, Rust's
single-connection-behind-a-mutex store still serializes the actual
SQLite access regardless of how many threads dispatch to it.

#### The cost of Ballerina's ergonomics wins

They come from language-level HTTP and JSON support that doesn't touch SQLite or
password hashing. For those two, Ballerina has to leave the language via
Java interop, while the other five all reach a native (or, for Bun,
fully built-in) SQLite driver and bcrypt binding without leaving their
own ecosystem. Ballerina is more expressive where its language design
anticipated the need (HTTP services, JSON, concurrency) and weaker where
it didn't (a mature package ecosystem for things like SQLite drivers and
bcrypt).

Python, Node, and Bun sit at the opposite end from Go and Rust on rigor,
no compile-time checking that's actually enforced at runtime, Bun's
optional `tsc` check included, but still avoid Ballerina's ecosystem gap
entirely. Bun sharpens both findings the Node row already pointed at. A
single-threaded runtime with a synchronous DB driver can outrun a
genuinely concurrent one on this workload simply by having nothing to
coordinate, and swapping out just the runtime and framework underneath
identical application code closes roughly half the remaining gap to Go.
Most of what looked like "Node's model wins" turns out to also be "V8
and Express cost something Bun's JavaScriptCore and Elysia don't."

Rust adds a third data point to that same finding. Even a stack with
real multi-threaded dispatch and no GC can still lose the read-path load
test to a single-threaded one, because this particular fan-out is small
enough, and the shared-connection mutex narrow enough, that coordination
overhead outweighs the parallelism it buys. Compiled and multi-threaded
isn't automatically fastest once a workload's bottleneck is a single
mutex either way.
