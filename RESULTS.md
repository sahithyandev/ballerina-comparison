# Ballerina vs Go — Results

Same blogging API (`openapi.yaml`, `schema.sql`), built twice. Numbers below
are from this machine, one run each — directional, not benchmark-grade (see
`plan.md`).

## Lines of code

| | Go | Ballerina |
|---|---|---|
| Hand-written | 948 | 826 |
| + generated (`api.gen.go` from OpenAPI) | 2048 | — (no codegen layer) |
| Tests | 300 (10 tests) | 138 (7 tests) |

Go's hand-written total looks smaller, but it leans on `oapi-codegen` to
generate 800 lines of request/response types + routing interface from
`openapi.yaml`. Ballerina has no equivalent codegen step — `types.bal` and
the resource signatures in `openapi_service.bal` are written by hand, which
is most of why Ballerina's request/response type code (`types.bal`, 131
lines) is comparable in size to what Go generates.

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

## Compile-time vs runtime error catching

- **Validation (#3)**: both catch structural errors (missing field, wrong
  type) at compile time via their respective type systems / generated
  bindings. Semantic validation (empty title, malformed email) is runtime
  code in both — neither language's type system expresses that.
- **External calls (#6)**: identical shape in both stacks — a typed
  client call wrapped in a timeout, with any error/timeout/non-200/bad body
  treated as "clean" and logged (fail-open), so the profanity stub being
  down never blocks a write. Go's version is `internal/profanity/profanity.go`
  (57 lines); Ballerina's is `profanity.bal` (21 lines) — smaller mostly
  because Ballerina's HTTP client + JSON binding requires less boilerplate
  per call than Go's manual `http.NewRequestWithContext` marshal/unmarshal.
- Neither stack catches a wrong profanity-API response *shape* at compile
  time — both discover a malformed JSON body from the stub only at runtime,
  and both treat that as fail-open too.

## Concurrency (`GET /posts/{id}` fan-out)

Both fan out three lookups (author, comments, comment-authors) and join:

- **Go**: goroutines + `golang.org/x/sync/errgroup`, results collected via
  shared vars closed over by each goroutine.
- **Ballerina**: named workers (`worker fetchAuthor`, etc.) inside the
  resource function, joined implicitly at function return / explicit `wait`.

Ballerina's worker syntax reads closer to sequential code (no explicit
channel or waitgroup wiring) at the cost of being a language-level construct
Go doesn't have — Go's goroutine + errgroup pattern is more verbose but is
the same idiom used for concurrency everywhere else in the language, not a
fan-out-specific feature.

## Startup / build

One cold `make clean && make build` run:

| | Go | Ballerina |
|---|---|---|
| Cold build time | 2s | 8s |
| Output size | 17M binary | 61M jar |
| Process startup (to first accepted request) | ~0.3s\* | ~1.4s\* |

\*Startup includes a polling loop with 50ms granularity, so treat these as
"same order of magnitude," not precise. Ballerina's is JVM-backed (`bal
build` emits a jar, run via `java -jar`), which accounts for both the larger
output and the slower cold start — Go compiles to a static native binary.

## Load test

`loadtest/run.sh`, `hey`, same machine, same DB, same fixture data (see
`loadtest/results/`):

| Stack | Endpoint | Req/s | Avg latency | p99 | Duration |
|---|---|---|---|---|---|
| Go | `GET /posts/{id}` | 4327 | 11.6ms | 23.6ms | 30s |
| Go | `POST /posts` | 4034 | 2.5ms | 7.4ms | 10s |
| Ballerina | `GET /posts/{id}` | 3479 | 14.4ms | 28.1ms | 30s |
| Ballerina | `POST /posts` | 1546 | 2.9ms | 9.5ms | 20s |

Go is ahead on both endpoints, most notably on the write path (`POST
/posts`, ~2.6x req/s). The read path (`GET /posts/{id}`, the concurrent
fan-out endpoint) is closer — Go ~24% ahead. One run, one machine — see
`plan.md`'s explicit disclaimer that this isn't JMH-grade rigor.

## Structured logging / config (#8, #9)

Both use their stdlib logging (`log/slog` in Go, `ballerina/log` in
Ballerina) with structured key-value fields, and both load all config
(`JWT_SECRET`, `DB_PATH`, `PORT`, `PROFANITY_URL`, etc.) from env vars at
startup with no framework — `internal/config/config.go` (53 lines) vs
`config.bal` (41 lines). No meaningful difference here; both languages'
standard tooling covers this criterion equally well.

## Error envelope / ownership checks (#4, #5)

Identical shape enforced in both: every error response is
`{"error": {"code", "message"}}`, and every post/comment write endpoint
checks the authenticated user against the resource's `author_id` before
allowing the write, returning 403 on mismatch. Go centralizes this in
`internal/httpx.Err`; Ballerina repeats the same record literal shape at
each error site in `openapi_service.bal` (no shared helper) — a case where
Go's package-private helper is directly reusable across handler files and
Ballerina's single-file service didn't need one for a codebase this size,
not a language-level gap.

## Where each stack wins

**Go**: faster on both benchmarked paths, especially writes; ~4x faster cold
build; smaller, dependency-free static binary; native SQLite and bcrypt
without leaving the language ecosystem.

**Ballerina**: worker-based concurrency reads more like straight-line code
than goroutine+errgroup wiring; less boilerplate per external HTTP call
(typed client + JSON binding built into the language); comparable structured
logging/config story with no extra ceremony.

**Cost of Ballerina's ergonomics wins**: both come from language-level HTTP/
JSON support that doesn't touch SQLite or password hashing — for those two,
Ballerina has to leave the language via Java interop, while Go reaches a
pure-Go SQLite driver and `golang.org/x/crypto/bcrypt` without leaving its
own ecosystem. That's the central tension this comparison surfaces: Ballerina
is more expressive where its language design anticipated the need (HTTP
services, JSON, concurrency) and weaker where it didn't (a mature package
ecosystem for things like SQLite drivers and bcrypt).

## Not covered

Containerization (`plan.md` criterion #11) is out of scope for this pass —
no Dockerfiles exist yet for either stack.
