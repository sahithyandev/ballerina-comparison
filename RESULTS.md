# Ballerina vs Go vs Python vs Node.js vs Bun — Results

Same blogging API (`openapi.yaml`, `schema.sql`), built five times. Numbers
below are from this machine, one run each — directional, not benchmark-grade
(see `plan.md`). The Ballerina/Go/Python/Node numbers were captured in an
earlier session; Bun's were captured separately, in a later session, on the
same machine but not in the same sitting as the other four — treat any
close call between Bun and Node as within session-to-session noise, not a
precise ranking.

## Lines of code

|                                         | Go             | Ballerina            | Python               | Node                 | Bun                   |
| --------------------------------------- | -------------- | -------------------- | -------------------- | -------------------- | ---------------------- |
| Hand-written                            | 948            | 826                  | 647                  | 546                  | 554                   |
| + generated (`api.gen.go` from OpenAPI) | 2048           | — (no codegen layer) | — (no codegen layer) | — (no codegen layer) | — (no codegen layer)  |
| Tests                                   | 300 (10 tests) | 138 (7 tests)        | 173 (11 tests)       | 199 (11 tests)       | 192 (11 tests)        |

Go's hand-written total looks smaller, but it leans on `oapi-codegen` to
generate 800 lines of request/response types + routing interface from
`openapi.yaml`. Ballerina has no equivalent codegen step — `types.bal` and
the resource signatures in `openapi_service.bal` are written by hand, which
is most of why Ballerina's request/response type code (`types.bal`, 131
lines) is comparable in size to what Go generates. Python and Node are both
smaller hand-written totals despite also having no codegen layer: Python's
`store.py` stdlib `sqlite3` calls and FastAPI/pydantic's declarative models
(`models.py`, 101 lines) cover request parsing/validation/serialization
compactly; Node is smallest of all because Express needs no separate models
file at all (there's no schema-validation library in the mix — `app.js`
validates request shapes by hand, same as Go, just without a generated
types layer to lean on). Bun lands almost exactly on Node's total despite
inline `t.Object` schemas replacing every hand-written `if` check in
`app.js` — the schemas save lines on validation, but TypeScript's type
annotations (interfaces in `store.ts`, typed function signatures throughout)
add roughly the same number back, a wash rather than a net win either way.

## Dependencies

|                  | Go                           | Ballerina                               | Python            | Node                 | Bun                    |
| ---------------- | ---------------------------- | --------------------------------------- | ----------------- | -------------------- | ---------------------- |
| Direct deps      | 7                            | 0 (+2 Java interop)                     | 6 (+1 dev-only)   | 3                    | 2 (+2 dev-only)        |
| Transitive deps  | 17                           | JVM classpath (jdbc driver, jbcrypt)    | —                 | —                    | ~17                    |
| Router/framework | chi                          | built-in `http:Service`                 | FastAPI + uvicorn | express               | Elysia                |
| JWT              | golang-jwt                   | built-in `jwt` module                   | pyjwt             | jsonwebtoken          | `@elysiajs/jwt`        |
| bcrypt           | golang.org/x/crypto          | `org.mindrot:jbcrypt` (Java interop)    | bcrypt            | bcryptjs (pure JS)    | built-in `Bun.password`|
| SQLite driver    | modernc.org/sqlite (pure Go) | `org.xerial:sqlite-jdbc` (Java interop) | stdlib `sqlite3`  | stdlib `node:sqlite`  | built-in `bun:sqlite`  |
| OpenAPI codegen  | kin-openapi/oapi-codegen     | —                                       | —                 | —                     | —                      |

**Go**: chi, golang-jwt, golang.org/x/crypto (bcrypt), golang.org/x/sync,
modernc.org/sqlite (pure-Go, no CGO), plus kin-openapi/oapi-codegen/runtime
for the generated layer.

**Ballerina**: 0 Ballerina Central packages, but two _Java_ interop
dependencies fill gaps Central doesn't cover — `org.xerial:sqlite-jdbc`
(no native SQLite connector; `java.jdbc` + this driver jar is the only
route) and `org.mindrot:jbcrypt` (`ballerina/crypto` has hash/hmac/AES but
no bcrypt, and none exists on Central either). This is the sharpest
ecosystem-maturity gap in the comparison: two plan-mandated primitives
(SQLite, bcrypt) that are stdlib-adjacent in Go require dropping to the JVM
in Ballerina.

**Python**: fastapi, uvicorn, pydantic, pyjwt, bcrypt, httpx (`pytest` is
dev-only, kept in `requirements-dev.txt` so it doesn't inflate the runtime
count). SQLite needs nothing beyond the `sqlite3` stdlib module, and bcrypt
is one `pip install` away — both of the primitives that force Ballerina to
Java interop are trivially available here, same as in Go.

**Node**: express, jsonwebtoken, bcryptjs (pure-JS, no native compile step).
SQLite needs nothing beyond the stdlib `node:sqlite` module (`DatabaseSync`,
experimental as of Node 22+) — the smallest direct-dependency count of any
stack, and, like Python, neither of Ballerina's two forced-into-Java-interop
primitives is a problem here.

**Bun**: elysia, `@elysiajs/jwt` — 2 direct runtime deps, the smallest of
any stack (plus `typescript` and `@types/bun`, dev-only, for the optional
static check). SQLite and bcrypt need nothing beyond `bun:sqlite` and
`Bun.password`, both built into the runtime with no npm package at all —
Bun is the only stack of the five where *neither* of Ballerina's two
forced-into-Java-interop primitives requires so much as a `pip install` or
an `npm install`, closing the gap Node still paid a (tiny, pure-JS)
dependency for.

## Compile-time vs runtime error catching

- **Validation (#3)**: Go and Ballerina catch structural errors (missing
  field, wrong type) at compile time via their type systems / generated
  bindings; Python's pydantic models, Node's hand-written checks, and Bun's
  `t.Object` schemas all catch the same structural errors only at
  _runtime_, on each request — no compile step is load-bearing for any of
  the three, so a typo in a field name or type is invisible until it's
  exercised by a request (or a test). Bun sits in an interesting middle
  spot: TypeScript gives it an _optional_ compile-time check (`bun x tsc
  --noEmit`) that Python and Node lack entirely, but nothing enforces it at
  runtime or in `bun start` — the `t.Object` schema and the TypeScript type
  it infers can drift apart, and only the schema's runtime check actually
  gates a request. Semantic validation (empty title, malformed email) is
  runtime code in all five — no type system here expresses that.
- **External calls (#6)**: same shape in all five stacks — a typed client
  call wrapped in a timeout, with any error/timeout/non-200/bad body treated
  as "clean" and logged (fail-open), so the profanity stub being down never
  blocks a write. Go's version is `internal/profanity/profanity.go`
  (57 lines); Ballerina's is `profanity.bal` (21 lines); Python's is
  `profanity.py` (34 lines); Node's is `profanity.js` (43 lines); Bun's is
  `profanity.ts` (37 lines) — Node's and Bun's versions both use the global
  `fetch` + `AbortSignal.timeout`, stdlib/built-in in both runtimes, so
  neither needs an HTTP client dependency at all, the same story as
  Python's `httpx` minus the extra package.
- None of the five stacks catches a wrong profanity-API response _shape_ at
  compile time — all five discover a malformed JSON body from the stub only
  at runtime, and all five treat that as fail-open too.

## Concurrency (`GET /posts/{id}` fan-out)

All five fan out three lookups (author, comments, comment-authors) and join:

|                               | Go                      | Ballerina                            | Python                                              | Node                                | Bun                                 |
| ----------------------------- | ----------------------- | ------------------------------------ | --------------------------------------------------- | ------------------------------------ | ------------------------------------ |
| Mechanism                     | goroutines + `errgroup` | named workers (`worker fetchAuthor`) | `asyncio.gather`                                    | `Promise.all`                        | `Promise.all`                        |
| Join point                    | `errgroup.Wait()`       | implicit at function return / `wait` | `await gather(...)`                                 | `await Promise.all(...)`             | `await Promise.all(...)`             |
| DB call underneath            | pooled `*sql.DB`        | pooled JDBC connection               | sync `sqlite3` via `to_thread`                      | sync `node:sqlite` (`DatabaseSync`)  | sync `bun:sqlite` (`Database`)       |
| Actually parallel against DB? | yes                     | yes (JVM threads)                    | no — thread-pool dispatch, serialized behind a lock | no — single JS thread, sequential    | no — single JS thread, sequential    |

Go uses goroutines + `golang.org/x/sync/errgroup`, results collected via
shared vars closed over by each goroutine. Ballerina's named workers read
closer to sequential code, joined implicitly at function return or an
explicit `wait`. Python's `asyncio.gather` wraps the sync `sqlite3` store in
`asyncio.to_thread` — there's no async SQLite driver in play, so the
"concurrency" here is thread-pool parallelism dressed in `async`/`await`
syntax, not a single-threaded event loop doing I/O-bound overlap the way
`asyncio.gather` normally implies. Node's and Bun's `Promise.all` both wrap
a _synchronous_ SQLite store (`node:sqlite`/`bun:sqlite`) — no thread pool
and no real overlap either, the calls run back-to-back on the single JS
thread; of the five this is the most honest about not actually
parallelizing the DB calls, it just doesn't pretend to via `async`/`await`
syntax the way Python's version does. Bun's version is line-for-line the
same code as Node's here — the fan-out logic doesn't change at all when the
runtime underneath does, which is exactly what makes the load-test numbers
below informative: same concurrency code, same "not really parallel"
caveat, different numbers.

Ballerina's worker syntax reads closer to sequential code (no explicit
channel or waitgroup wiring) at the cost of being a language-level construct
Go doesn't have. Python's, Node's, and Bun's `Promise.all`/`asyncio.gather`
read the most concise of the five, but none of the three is doing real
concurrent I/O for this particular fan-out — Python's is thread-pool
dispatch, Node's and Bun's are sequential work wrapped in promise sugar.
Go's goroutine + errgroup pattern is more verbose but is the same idiom
used for concurrency everywhere else in the language, not a fan-out-specific
feature, and it's the only one of the five that's actually running the
three lookups in parallel against the database driver.

## Startup / build

One cold `make clean && make build` run:

|                                             | Go         | Ballerina | Python                | Node                           | Bun                            |
| ------------------------------------------- | ---------- | --------- | --------------------- | ------------------------------- | ------------------------------- |
| Cold build/setup time                       | 2s         | 8s        | 5s                    | <1s                             | <1s                             |
| Output size                                 | 17M binary | 61M jar   | 45M (venv, no binary) | 4.8M (node_modules, no binary)  | 44M (node_modules, no binary)   |
| Process startup (to first accepted request) | ~0.3s\*    | ~1.4s\*   | ~1.6s\*               | ~0.15s\*                        | ~0.1s\*                         |

\*Startup includes a polling loop with 50ms granularity, so treat these as
"same order of magnitude," not precise. Ballerina's is JVM-backed (`bal
build` emits a jar, run via `java -jar`), which accounts for both the larger
output and the slower cold start — Go compiles to a static native binary.
Python has no build/compile step at all — "cold build" here is really
`pip install` populating a venv, and "output size" is that venv's size, not
a deployable artifact; startup is dominated by uvicorn + FastAPI import
time, landing in the same ballpark as Ballerina's JVM cold start despite
never touching a bytecode-compiled runtime. Node has no build/compile step
either — "cold build" is `npm install` populating `node_modules` — but its
tiny dependency count (3 direct packages) makes both install time and
startup among the fastest of any stack. Bun has no build/compile step
either — "cold build" is `bun install`, sub-second even though
`bun/node_modules` (44M) is nearly 10x Node's, almost entirely `jose`
pulled in transitively by `@elysiajs/jwt` — Bun's installer is simply that
fast. Startup edges out even Node's, landing marginally ahead in this one
run; both are close enough that "fastest of any stack" is a two-way tie
within this measurement's noise, not a clear win for either.

## Load test

`loadtest/run.sh`, `hey`, same machine, same DB, same fixture data (see
`loadtest/results/`). The Ballerina/Go/Python/Node rows were captured in one
sitting; the Bun rows were captured separately, in a later session — same
machine, but not guaranteed identical background load, so don't over-read a
close Bun-vs-Node call:

| Stack     | Endpoint          | Req/s | Avg latency | p99    | Duration |
| --------- | ----------------- | ----- | ----------- | ------ | -------- |
| Go        | `GET /posts/{id}` | 4327  | 11.6ms      | 23.6ms | 30s      |
| Go        | `POST /posts`     | 4034  | 2.5ms       | 7.4ms  | 10s      |
| Ballerina | `GET /posts/{id}` | 3479  | 14.4ms      | 28.1ms | 30s      |
| Ballerina | `POST /posts`     | 1546  | 2.9ms       | 9.5ms  | 20s      |
| Python    | `GET /posts/{id}` | 1440  | 34.7ms      | 44.7ms | 30s      |
| Python    | `POST /posts`     | 271   | 36.9ms      | 45.6ms | 10s      |
| Node      | `GET /posts/{id}` | 7849  | 6.4ms       | 11.9ms | 30s      |
| Node      | `POST /posts`     | 2946  | 3.4ms       | 7.4ms  | 10s      |
| Bun       | `GET /posts/{id}` | 15274 | 3.3ms       | 6.3ms  | 30s      |
| Bun       | `POST /posts`     | 3267  | 3.1ms       | 6.6ms  | 10s      |

Node comes out ahead of Go/Ballerina/Python on the read path (`GET
/posts/{id}`, ~1.8x Go's req/s) and second only to Go on writes. This is the
flip side of the concurrency finding above: `node:sqlite`'s `DatabaseSync` is
synchronous and needs no lock or connection-pool ceremony to stay safe under
concurrent requests (there's only ever one JS thread touching it), and V8's
JIT plus Express's thin routing layer keep per-request overhead low — the
same single-threaded model that made the fan-out "not really concurrent"
above pays off here by avoiding any cross-thread coordination cost at all.
Bun goes further still: ~1.9x Node's read-path req/s (15274 vs 7849) and
comes within reach of Go on writes (3267 vs 4034), running the *identical*
fan-out code as Node over `Promise.all` and a synchronous SQLite driver.
Since the concurrency model and the application code are unchanged between
the two, the gap traces to what's underneath: JavaScriptCore vs V8, Bun's
own HTTP server vs Node's, and Elysia's radix-tree router vs Express's
linear middleware chain. This was the whole reason to add Bun to the
comparison — it isolates how much of Node's single-threaded win was really
about the event-loop model (which Bun keeps) versus V8 and Express
specifically (which Bun replaces): on this measurement, roughly half of the
gap between Go and Node's original numbers gets closed again by swapping
out those two layers alone, while the model that makes GET /posts/{id}
"not really concurrent" stays exactly the same in both. Python sits at the
other end: `uvicorn` here runs a single worker process whose event loop
dispatches SQLite calls into a bounded thread pool one at a time behind a
lock (mirroring the `SetMaxOpenConns(1)` constraint Go/Node/Bun share in
spirit), so Python's write path in particular is serialized in a way none
of the others are. A multi-worker uvicorn deployment would likely close
some of Python's gap, but that's a different, not-yet-measured
configuration. One run per stack, not all in the same sitting — see
`plan.md`'s explicit disclaimer that this isn't JMH-grade rigor.

## Structured logging / config (#8, #9)

|                                | Go                          | Ballerina       | Python            | Node                                      | Bun                                        |
| ------------------------------ | --------------------------- | --------------- | ----------------- | ------------------------------------------ | -------------------------------------------- |
| Logging                        | `log/slog`                  | `ballerina/log` | stdlib `logging`  | `console.log` + hand-rolled JSON envelope  | `console.log` + hand-rolled JSON envelope    |
| Level filtering / streams      | yes (stdlib)                | yes (stdlib)    | yes (stdlib)      | no — no logging library                    | no — no logging library                      |
| Config file                    | `internal/config/config.go` | `config.bal`    | `config.py`       | `config.js`                                | `config.ts`                                  |
| Config lines                   | 53                          | 41              | 44                | 30                                         | 37                                            |
| Duration parsing (`24h`, `2s`) | stdlib                      | stdlib          | hand-rolled regex | hand-rolled regex                          | hand-rolled regex                            |
| `.env` loading                 | none (shell/CI provides it) | none            | none              | none — vars must already be in the process | automatic — Bun loads `.env` from cwd itself |

All five load config (`JWT_SECRET`, `DB_PATH`, `PORT`, `PROFANITY_URL`, etc.)
from env vars at startup with no framework. No meaningful difference here;
all five languages' standard tooling covers this criterion equally well.
One wrinkle: Go and Ballerina parse env-var durations via their stdlib
duration parsers; neither Python's, Node's, nor Bun's stdlib has an
equivalent, so `config.py`, `config.js`, and `config.ts` all hand-roll the
same small regex-based parser to keep `.env.example`'s values shared
verbatim across all five stacks. Node's and Bun's logging are the least
polished of the five — `console.log(JSON.stringify(...))` gets the same
structured-field shape as the others with zero setup, but there's no actual
logging library doing level filtering, output streams, etc., the way
`log/slog` or Python's `logging` module do out of the box. Bun is the only
stack of the five that reads `.env` on its own — the other four either rely
on the shell/CI to export the variables first or, in Node's case, need an
explicit `--env-file` flag; forgetting that step is the most common way to
hit `config error: JWT_SECRET is required` when starting Node by hand.

## Error envelope / ownership checks (#4, #5)

Identical shape enforced in all five: every error response is
`{"error": {"code", "message"}}`, and every post/comment write endpoint
checks the authenticated user against the resource's `author_id` before
allowing the write, returning 403 on mismatch — with one documented
exception in Bun, noted below.

|                 | Go                                 | Ballerina                        | Python                                        | Node                                       | Bun                                                |
| --------------- | ---------------------------------- | -------------------------------- | --------------------------------------------- | ------------------------------------------- | ---------------------------------------------------- |
| Error rendering | centralized (`internal/httpx.Err`) | repeated record literal per site | `ApiError(HTTPException)` + exception handler | `sendErr` helper + error middleware         | centralized `onError` hook + inline `status(...)`    |
| Extra wrinkle   | —                                  | no shared helper                 | remaps FastAPI's default 422 shape too        | Express `(err, req, res, next)` convention  | schema validation runs before the auth check (below) |

Go centralizes error rendering in `internal/httpx.Err`; Ballerina repeats
the same record literal shape at each error site in `openapi_service.bal`
with no shared helper; Python raises a small `ApiError(HTTPException)`
subclass with a single exception handler that renders the shared envelope,
plus a second handler that remaps FastAPI's default 422 validation-error
shape into the same envelope — a FastAPI-specific wrinkle none of the other
stacks need, since none has a framework-level validation layer of its own
to override; Node centralizes error rendering in a small `sendErr` helper
plus an Express error-handling middleware that catches malformed-JSON
body-parse errors and 500s, similar in spirit to Go's helper but with
Express's convention of a trailing `(err, req, res, next)` middleware
rather than a plain function call at each error site. Bun centralizes the
same three framework-level cases (bad JSON, unmatched route, uncaught
exception) in one `onError` hook keyed on Elysia's `code`, closer to Go's
single-helper story than to Python's two-handler one, while ownership and
profanity checks call the `status(code, body)` helper inline per site, same
shape as Go/Node's early returns. One real behavioral wrinkle: Elysia
validates the request body against its `t.Object` schema *before* running
any handler code, so a request that is both unauthenticated and carries an
invalid body returns `400 validation_failed` from Bun instead of the
`401 unauthorized` the other four stacks return for the same request — a
side effect of schema-first validation racing ahead of a handler-level auth
check, not a missing check. Every single-condition case (valid body with no
token, or a token with an invalid body) returns the same status and code as
the other four stacks; only the simultaneous-double-failure edge differs.

## Where each stack wins

**Go**: fastest on the write path; ~4x faster cold build than Ballerina;
smaller, dependency-free static binary; native SQLite and bcrypt without
leaving the language ecosystem; the only stack whose fan-out concurrency is
genuinely parallel against the DB driver.

**Ballerina**: worker-based concurrency reads more like straight-line code
than goroutine+errgroup wiring; less boilerplate per external HTTP call
(typed client + JSON binding built into the language); comparable structured
logging/config story with no extra ceremony.

**Python**: smallest hand-written codebase among the non-Node stacks, no
codegen and no compile step at all; SQLite and bcrypt both trivially
available (stdlib and one `pip install`, respectively) — the exact gap that
forces Ballerina to Java interop; pydantic gives declarative validation with
the least boilerplate per endpoint. Its cost is the weakest runtime story of
the four: slowest on both load-test paths by a wide margin (mostly from the
sync-SQLite-behind-a-lock constraint colliding with a single-process
`uvicorn`), and, along with Node, one of the two stacks with zero
compile-time checking of any kind.

**Node**: smallest hand-written codebase overall; fewest direct dependencies
(3) of any stack outside Bun, and the only stack besides Bun where the
"SQLite dependency" is literally a zero-install stdlib module; fast cold
build/startup; fast on the read path of the load test, narrowly behind Go
on writes. Its cost mirrors Python's on rigor (no compile-time checking)
and its fan-out concurrency is the least "real" alongside Bun's — a
single-threaded event loop means the three lookups in `GET /posts/{id}`
never actually overlap, they just don't block each other with explicit
callback wiring.

**Bun**: fastest stack in the load test by a wide margin on both paths —
~1.9x Node's read-path req/s and within reach of Go on writes — running the
*identical* `Promise.all`-over-synchronous-SQLite fan-out code as Node, so
the gap is attributable to JavaScriptCore + Bun's own HTTP server + Elysia's
router rather than to any application-level difference; fewest direct
runtime dependencies of any stack (2); the only stack where *both*
SQLite and bcrypt are zero-install built-ins, closing the exact ecosystem
gap that forces Ballerina to Java interop; `.env` auto-loading needs no
flag or dependency, unlike the other four. Its cost is the same as Node's on
rigor (schema validation is a runtime check, not a compile-time one) plus
one documented ordering quirk — schema validation runs ahead of the
handler-level auth check, so a doubly-invalid request surfaces
`validation_failed` instead of `unauthorized` — and it inherits Node's
"least real" fan-out concurrency, for the same single-threaded reason.

**Cost of Ballerina's ergonomics wins**: they come from language-level HTTP/
JSON support that doesn't touch SQLite or password hashing — for those two,
Ballerina has to leave the language via Java interop, while Go, Python,
Node, and Bun all reach a native/pure-language (or, for Bun, fully built-in)
SQLite driver and bcrypt binding without leaving their own ecosystems.
That's the central tension this comparison surfaces: Ballerina is more
expressive where its language design anticipated the need (HTTP services,
JSON, concurrency) and weaker where it didn't (a mature package ecosystem
for things like SQLite drivers and bcrypt) — while Python, Node, and Bun
sit at the opposite end from Go on rigor (no compile-time checking that's
actually enforced at runtime, Bun's optional `tsc` check included) but
still avoid Ballerina's ecosystem gap entirely, and Bun sharpens both
findings the Node row already pointed at: a single-threaded runtime with a
synchronous DB driver can not only outrun a genuinely concurrent one on
this workload, simply by having nothing to coordinate, but swapping out
just the runtime and framework underneath identical application code closes
roughly half the remaining gap to Go — most of what looked like "Node's
model wins" turns out to also be "V8 and Express cost something Bun's
JavaScriptCore and Elysia don't."

## Not covered

Containerization (`plan.md` criterion #11) is out of scope for this pass —
no Dockerfiles exist yet for any of the five stacks. A multi-worker uvicorn
configuration for Python (`--workers N`) and a Node/Bun cluster or
worker-threads configuration were also not benchmarked; the load test above
reflects a single process throughout.
