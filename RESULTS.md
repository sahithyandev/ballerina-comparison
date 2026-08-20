# Ballerina vs Go vs Python — Results

Same blogging API (`openapi.yaml`, `schema.sql`), built three times. Numbers
below are from this machine, one run each — directional, not benchmark-grade
(see `plan.md`).

## Lines of code

| | Go | Ballerina | Python |
|---|---|---|---|
| Hand-written | 948 | 826 | 647 |
| + generated (`api.gen.go` from OpenAPI) | 2048 | — (no codegen layer) | — (no codegen layer) |
| Tests | 300 (10 tests) | 138 (7 tests) | 173 (11 tests) |

Go's hand-written total looks smaller, but it leans on `oapi-codegen` to
generate 800 lines of request/response types + routing interface from
`openapi.yaml`. Ballerina has no equivalent codegen step — `types.bal` and
the resource signatures in `openapi_service.bal` are written by hand, which
is most of why Ballerina's request/response type code (`types.bal`, 131
lines) is comparable in size to what Go generates. Python is the smallest
hand-written total of the three despite also having no codegen layer:
`store.py`'s stdlib `sqlite3` calls are the most compact of any stack's data
layer, and FastAPI/pydantic (`models.py`, 101 lines) cover request parsing,
validation dispatch, and response serialization in far less code than either
Go's generated types or Ballerina's hand-written records.

## Dependencies

**Go** (`go.mod`): 7 direct deps — chi (router), golang-jwt, golang.org/x/crypto
(bcrypt), golang.org/x/sync, modernc.org/sqlite (pure-Go, no CGO), plus
kin-openapi/oapi-codegen/runtime for the generated layer. 17 more pulled in
transitively.

**Ballerina** (`Ballerina.toml`): 0 Ballerina Central packages. Two *Java*
interop dependencies instead:
- `org.xerial:sqlite-jdbc` — Ballerina has no native SQLite connector;
  `java.jdbc` + this driver jar is the only route.
- `org.mindrot:jbcrypt` — `ballerina/crypto` has hash/hmac/AES but no
  bcrypt, and none exists on Central either. Password hashing only works via
  Java interop onto jBCrypt.

This is the sharpest ecosystem-maturity gap in the comparison: two
plan-mandated primitives (SQLite, bcrypt) that are stdlib-adjacent in Go
require dropping to the JVM in Ballerina.

**Python** (`requirements.txt`): 6 direct packages — fastapi, uvicorn,
pydantic, pyjwt, bcrypt, httpx (`pytest` is dev-only, kept in
`requirements-dev.txt` so it doesn't inflate the runtime count). SQLite needs
nothing beyond the `sqlite3` stdlib module, and bcrypt is one `pip install`
away — both of the primitives that force Ballerina to Java interop are
trivially available here, same as in Go.

## Compile-time vs runtime error catching

- **Validation (#3)**: Go and Ballerina catch structural errors (missing
  field, wrong type) at compile time via their type systems / generated
  bindings; Python's pydantic models catch the same structural errors, but
  only at *runtime*, on each request — there is no compile step at all, so a
  typo in a field name or type is invisible until it's exercised by a
  request (or a test). Semantic validation (empty title, malformed email) is
  runtime code in all three — no type system here expresses that.
- **External calls (#6)**: same shape in all three stacks — a typed client
  call wrapped in a timeout, with any error/timeout/non-200/bad body treated
  as "clean" and logged (fail-open), so the profanity stub being down never
  blocks a write. Go's version is `internal/profanity/profanity.go`
  (57 lines); Ballerina's is `profanity.bal` (21 lines); Python's is
  `profanity.py` (34 lines) — `httpx.AsyncClient` cuts the manual
  marshal/unmarshal Go needs but still needs explicit `try`/`except` framing
  Ballerina's client call doesn't.
- None of the three stacks catches a wrong profanity-API response *shape* at
  compile time — all three discover a malformed JSON body from the stub only
  at runtime, and all three treat that as fail-open too.

## Concurrency (`GET /posts/{id}` fan-out)

All three fan out three lookups (author, comments, comment-authors) and join:

- **Go**: goroutines + `golang.org/x/sync/errgroup`, results collected via
  shared vars closed over by each goroutine.
- **Ballerina**: named workers (`worker fetchAuthor`, etc.) inside the
  resource function, joined implicitly at function return / explicit `wait`.
- **Python**: `asyncio.gather` over `asyncio.to_thread`-wrapped calls into
  the sync `sqlite3` store — there's no async SQLite driver in play, so the
  "concurrency" here is really thread-pool parallelism dressed in `async`/
  `await` syntax, not a single-threaded event loop doing I/O-bound overlap
  the way `asyncio.gather` normally implies.

Ballerina's worker syntax reads closer to sequential code (no explicit
channel or waitgroup wiring) at the cost of being a language-level construct
Go doesn't have. Python's `asyncio.gather` reads the most concise of the
three, but that concision is slightly misleading here — it's standing in for
thread-pool dispatch, not real async I/O, because of the sync SQLite
dependency. Go's goroutine + errgroup pattern is more verbose but is the same
idiom used for concurrency everywhere else in the language, not a
fan-out-specific feature.

## Startup / build

One cold `make clean && make build` run:

| | Go | Ballerina | Python |
|---|---|---|---|
| Cold build/setup time | 2s | 8s | 5s |
| Output size | 17M binary | 61M jar | 45M (venv, no binary) |
| Process startup (to first accepted request) | ~0.3s\* | ~1.4s\* | ~1.6s\* |

\*Startup includes a polling loop with 50ms granularity, so treat these as
"same order of magnitude," not precise. Ballerina's is JVM-backed (`bal
build` emits a jar, run via `java -jar`), which accounts for both the larger
output and the slower cold start — Go compiles to a static native binary.
Python has no build/compile step at all — "cold build" here is really
`pip install` populating a venv, and "output size" is that venv's size, not
a deployable artifact; startup is dominated by uvicorn + FastAPI import
time, landing in the same ballpark as Ballerina's JVM cold start despite
never touching a bytecode-compiled runtime.

## Load test

`loadtest/run.sh`, `hey`, same machine, same DB, same fixture data (see
`loadtest/results/`):

| Stack | Endpoint | Req/s | Avg latency | p99 | Duration |
|---|---|---|---|---|---|
| Go | `GET /posts/{id}` | 4327 | 11.6ms | 23.6ms | 30s |
| Go | `POST /posts` | 4034 | 2.5ms | 7.4ms | 10s |
| Ballerina | `GET /posts/{id}` | 3479 | 14.4ms | 28.1ms | 30s |
| Ballerina | `POST /posts` | 1546 | 2.9ms | 9.5ms | 20s |
| Python | `GET /posts/{id}` | 1440 | 34.7ms | 44.7ms | 30s |
| Python | `POST /posts` | 271 | 36.9ms | 45.6ms | 10s |

Go is ahead on both endpoints, most notably on the write path (`POST
/posts`, ~2.6x Ballerina's req/s, ~15x Python's). The read path
(`GET /posts/{id}`, the concurrent fan-out endpoint) narrows the Go/Ballerina
gap to ~24% but not Python's — Python trails both by roughly 2.4x–3x on
reads and by an order of magnitude on writes. This tracks the concurrency
model above: Go and Ballerina genuinely parallelize across OS threads under
`hey`'s concurrent load, while `uvicorn` here runs a single worker process
whose event loop dispatches SQLite calls into a bounded thread pool one at a
time behind a lock (mirroring the `SetMaxOpenConns(1)` constraint the other
stacks share) — so Python's write path in particular is serialized in a way
the other two aren't. A multi-worker uvicorn deployment would likely close
some of this gap, but that's a different, not-yet-measured configuration.
One run, one machine — see `plan.md`'s explicit disclaimer that this isn't
JMH-grade rigor.

## Structured logging / config (#8, #9)

All three use stdlib-adjacent logging (`log/slog` in Go, `ballerina/log` in
Ballerina, `logging` in Python) with structured key-value fields, and all
three load config (`JWT_SECRET`, `DB_PATH`, `PORT`, `PROFANITY_URL`, etc.)
from env vars at startup with no framework — `internal/config/config.go`
(53 lines), `config.bal` (41 lines), `config.py` (44 lines). No meaningful
difference here; all three languages' standard tooling covers this
criterion equally well. One wrinkle: Go and Ballerina parse env-var
durations (`24h`, `2s`) via their stdlib duration parsers; Python's stdlib
has no equivalent, so `config.py` hand-rolls a small regex-based parser to
keep `.env.example`'s values shared verbatim across all three stacks.

## Error envelope / ownership checks (#4, #5)

Identical shape enforced in all three: every error response is
`{"error": {"code", "message"}}`, and every post/comment write endpoint
checks the authenticated user against the resource's `author_id` before
allowing the write, returning 403 on mismatch. Go centralizes this in
`internal/httpx.Err`; Ballerina repeats the same record literal shape at
each error site in `openapi_service.bal` (no shared helper); Python raises a
small `ApiError(HTTPException)` subclass with a single exception handler
that renders the shared envelope, plus a second handler that remaps
FastAPI's default 422 validation-error shape into the same envelope — a
FastAPI-specific wrinkle neither of the other stacks needs, since neither
has a framework-level validation layer of its own to override.

## Where each stack wins

**Go**: faster on both benchmarked paths, especially writes; ~4x faster cold
build; smaller, dependency-free static binary; native SQLite and bcrypt
without leaving the language ecosystem.

**Ballerina**: worker-based concurrency reads more like straight-line code
than goroutine+errgroup wiring; less boilerplate per external HTTP call
(typed client + JSON binding built into the language); comparable structured
logging/config story with no extra ceremony.

**Python**: smallest hand-written codebase of the three, no codegen and no
compile step at all; SQLite and bcrypt both trivially available (stdlib and
one `pip install`, respectively) — the exact gap that forces Ballerina to
Java interop; pydantic gives declarative validation with the least
boilerplate per endpoint. Its cost is the weakest runtime story of the
three: slowest on both load-test paths by a wide margin (mostly from the
sync-SQLite-behind-a-lock constraint colliding with a single-process
`uvicorn`), and the only stack with zero compile-time checking of any kind.

**Cost of Ballerina's ergonomics wins**: both come from language-level HTTP/
JSON support that doesn't touch SQLite or password hashing — for those two,
Ballerina has to leave the language via Java interop, while Go and Python
both reach a native/pure-language SQLite driver and bcrypt binding without
leaving their own ecosystems. That's the central tension this comparison
surfaces: Ballerina is more expressive where its language design anticipated
the need (HTTP services, JSON, concurrency) and weaker where it didn't (a
mature package ecosystem for things like SQLite drivers and bcrypt) — while
Python sits at the opposite end from Go on rigor (no compile-time checking
anywhere) but still avoids Ballerina's ecosystem gap entirely.

## Not covered

Containerization (`plan.md` criterion #11) is out of scope for this pass —
no Dockerfiles exist yet for any of the three stacks. A multi-worker uvicorn
configuration for Python (`--workers N`) was also not benchmarked; the load
test above reflects a single worker process only.
