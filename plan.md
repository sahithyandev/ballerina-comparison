# Ballerina vs Go — Comparison Plan

## Goal
Build the *same* backend service in Ballerina and Go, then compare them on
code, ergonomics, and behavior — not benchmarks alone.

## Languages / stacks to compare
- **Ballerina** (the subject)
- **Go** (net/http + stdlib, or chi) — closest "cloud-native" competitor
- **Python** (FastAPI + uvicorn) — dynamic-typed, no-codegen reference point
- **Node.js** (Express) — event-loop/single-threaded reference point

## The sample backend: a blogging platform API
A small but recognizable domain — gives every technical checkbox below a
natural reason to exist instead of feeling bolted on.

**Domain**: Users, Posts, Comments
- `User`: id, username, email, password_hash
- `Post`: id, author_id, title, body, published, created_at
- `Comment`: id, post_id, author_id, body, created_at

**Conventions**
- Base path: `/api/v1`
- Pagination: `?page=&limit=` (1-indexed, default limit 20)
- Password hashing: bcrypt
- JWT: HS256, secret + expiry from env vars, same values used by both stacks
- `DELETE /posts/{id}` cascades to its comments (enforced via SQLite `ON
  DELETE CASCADE` in `schema.sql`, not app code)
- Profanity check: a small local stub server (not a real third-party API) —
  lets us force slow/failing responses on demand for deterministic
  timeout/fallback testing in both stacks

**Endpoints**
- `POST /auth/register`, `POST /auth/login` → JWT
- `GET /posts` (paginated, filter by `published`)
- `GET /posts/{id}` → post + author + comments (each comment with its own
  author) — fetched concurrently, join point for the concurrency criterion
- `POST /posts`, `PUT /posts/{id}`, `DELETE /posts/{id}` — auth required,
  author-only
- `POST /posts/{id}/comments` — auth required
- `GET /posts/{id}/comments`

**Technical criteria this exercises** (same list either way, now with a home):
1. **REST CRUD** — posts and comments
2. **Persistence** — SQLite (file-based, zero setup, same schema for both stacks)
3. **Input validation** — structured 400s (empty title, bad email, etc.)
4. **Auth** — JWT bearer auth, ownership checks on write endpoints
5. **Error handling** — consistent error envelope, no stack traces leaking
6. **External HTTP call** — check new post/comment body against the mock
   profanity-check stub server, with timeout + graceful fallback if it's down
7. **Concurrency** — `GET /posts/{id}` fans out author + comments + comment
   authors concurrently and joins them (Ballerina workers vs Go goroutines)
8. **Structured logging**
9. **Config via env vars**
10. **Tests** — unit test for validation logic, one integration test hitting
    the running service
11. **Containerization** — a Dockerfile for each stack, same base pattern

## What "comparison" means concretely
For each of the 11 items above, capture:
- Lines of code / files needed
- What's stdlib vs required a dependency
- Compile-time vs runtime error catching (esp. for #3 validation, #6 external calls)
- How concurrency is expressed (goroutines vs async/await vs Ballerina workers)
- Startup time, cold build time, Docker image size
- Rough request latency under a simple load test (`hey` or `autocannon`), same
  hardware, same DB — directional numbers, not a rigorous benchmark, say so
  explicitly in the writeup

## Deliverables
- `/ballerina`, `/go`, `/python`, `/node` — one folder per stack, same blog API contract
  (share one OpenAPI spec as the source of truth), each with its own
  `blog.db` SQLite file (or a `schema.sql` used to (re)create it)
- `/mock-profanity-api` — one tiny stub server (any language, doesn't need to
  match the compared stacks) with a toggle/header to force slow or failing
  responses, reused by both stacks
- `RESULTS.md` — the actual comparison writeup: table of LOC/deps/latency +
  narrative per criterion + an honest "where each language wins" section
- A load-test script (`hey` or `autocannon`) reused across both services,
  fixed scenario: `GET /posts/{id}` (the fan-out endpoint) at a fixed
  concurrency/duration (e.g. 50 concurrent for 30s), plus one write-path run
  against `POST /posts`

## Order of work
1. Write the OpenAPI spec + shared `schema.sql` for SQLite
2. Build the mock profanity-check stub server
3. Build Ballerina version first (it's the subject — get its idioms right)
4. Build Go version against the same schema/spec
5. Run identical load test script against each
6. Fill in RESULTS.md

## Explicitly out of scope
- Kubernetes/deployment orchestration comparison
- Exhaustive perf benchmarking (JMH-grade rigor) — directional only
- Frontend/UI
- Any DB other than SQLite for now
