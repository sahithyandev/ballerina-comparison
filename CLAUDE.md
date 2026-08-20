# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A head-to-head comparison of Ballerina, Go, Python, Node.js, and Bun: the
*same* blogging platform API (users/posts/comments, JWT auth, SQLite,
profanity-check external call, concurrent fan-out) is implemented five
times, once per stack, against one shared `openapi.yaml` contract and one
shared `schema.sql`. The goal is a comparison writeup (`RESULTS.md`), not a
production service — see `plan.md` for the full criteria list and
`README.md` for current status.

Any change to behavior (validation rules, error envelope shape, endpoints)
should generally be made in **all five** of `ballerina/`, `go/`, `python/`,
`node/`, and `bun/` to keep the comparison fair, unless the task is
explicitly about one stack only.

## Commands

**Run everything** (each in its own terminal):
```bash
cd mock-profanity-api && go run .        # stub server, port 9090
cd go && go run .                        # Go API, port 8080 (or PORT from .env)
cd ballerina && bal run .                # Ballerina API, alt port if run alongside Go
cd python && .venv/bin/python main.py    # Python API, port 8082 (or PORT from .env)
cd node && node server.js                # Node API, port 8083 (or PORT from .env)
cd bun && bun server.ts                  # Bun API, port 8084 (or PORT from .env)
```

**Go**
```bash
cd go && go build ./...
cd go && go test ./...
cd go && go vet ./...
```
`go/internal/api/api.gen.go` is generated from `../openapi.yaml` via
`oapi-codegen` (config: `go/oapi-codegen-config.yaml`) — do not hand-edit it;
regenerate instead when the OpenAPI spec changes.

**Ballerina**
```bash
cd ballerina && bal build
cd ballerina && bal run .
```
`ballerina/tests/service_test.bal` is an integration suite: `bal test` starts
the module's real listener + `dbClient` (config.bal reads env vars at module
init, same as `bal run`), so tests need the same setup plus a scratch DB and
an unreachable profanity URL so writes hit the fail-open path deterministically:
```bash
cd ballerina
sqlite3 blog.db < ../schema.sql   # tables must exist before dbClient connects
JWT_SECRET=test-secret PORT=9099 PROFANITY_URL=http://127.0.0.1:1 bal test
```
`@test:BeforeSuite` clears the users/posts/comments tables, so reruns start clean.

**Python**
```bash
cd python && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cd python && .venv/bin/python main.py   # run
cd python && JWT_SECRET=test-secret PROFANITY_URL=http://127.0.0.1:1 .venv/bin/pytest   # test
```
`python/tests/test_api.py` builds a fresh temp SQLite db from `../schema.sql`
per test (via a pytest fixture) and points `PROFANITY_URL` at nothing
listening, same fail-open trick as the Go/Ballerina suites — no separate
running service or scratch DB needed.

**Node**
```bash
cd node && npm install
cd node && npm start   # run
cd node && JWT_SECRET=test-secret PROFANITY_URL=http://127.0.0.1:1 npm test   # test
```
`node/test/api.test.js` uses the stdlib `node:test` runner (no jest/mocha
dependency) and the global `fetch` against a real server bound to an
ephemeral port, built from a temp SQLite db + `../schema.sql` — same
fail-open trick as the other three suites.

**Bun**
```bash
cd bun && bun install
cd bun && bun start   # run
cd bun && JWT_SECRET=test-secret PROFANITY_URL=http://127.0.0.1:1 bun test   # test
cd bun && bun x tsc --noEmit   # typecheck (optional static check; runtime needs no build step)
```
`bun/test/api.test.ts` uses the stdlib `bun:test` runner and the global
`fetch` against a real server bound to an ephemeral port, built from a temp
SQLite db + `../schema.sql` — same fail-open trick as the other four
suites. Bun auto-loads `.env` from the working directory, so no dotenv
dependency and no `--env-file` flag needed (unlike Node).

**DB setup** (each stack reads/writes its own `blog.db` from the same schema):
```bash
sqlite3 blog.db < ../schema.sql && sqlite3 blog.db < ../seed.sql
```

All five stacks require a `.env` (copied from `.env.example`) with
`JWT_SECRET` set — they fail to start without it. Same env var values are
used by all of them intentionally (see `.env.example`).

## Architecture

**Shared contract, independent implementations.** `openapi.yaml` and
`schema.sql` at the repo root are the single source of truth all five
stacks implement against; there is no shared code between `ballerina/`,
`go/`, `python/`, `node/`, `bun/`, and `mock-profanity-api/`.

**Go** (`go/`): chi router, handlers generated interface from
`api.gen.go` implemented in `internal/handlers/handlers.go`. Layout:
- `internal/api` — generated request/response types + chi server interface (do not edit)
- `internal/handlers` — endpoint logic, implements the generated interface
- `internal/store` — SQLite data access (`modernc.org/sqlite`, no CGO)
- `internal/auth` — JWT issue/verify (`golang-jwt/jwt`)
- `internal/profanity` — profanity-check client with timeout + fail-open fallback
- `internal/config`, `internal/httpx` — env config loading, shared error-envelope response helper

**Ballerina** (`ballerina/`): single-package service, no generated code layer.
- `openapi_service.bal` — the HTTP service and all endpoint resources
- `db.bal` — SQLite access via `java.jdbc` (no native Ballerina SQLite connector)
- `auth.bal` — JWT handling
- `profanity.bal` — profanity-check client call
- `types.bal` — request/response/record types
- `config.bal` — env var config loading
- bcrypt is unavailable natively in Ballerina (`ballerina/crypto` has no
  bcrypt, none on Central either) — `db.bal`/`auth.bal` reach it via Java
  interop onto `org.mindrot:jbcrypt` (declared in `Ballerina.toml`). This is
  a deliberate comparison data point, not a workaround to "fix".

**Python** (`python/`): flat module layout, no generated code layer — mirrors
the Go package split 1:1 rather than Ballerina's single-file style.
- `main.py` — FastAPI app, mounted at `/api/v1`, all endpoint routes
- `store.py` — SQLite access via stdlib `sqlite3`
- `auth.py` — JWT issue/verify (`pyjwt`) + password hashing (`bcrypt`)
- `profanity.py` — profanity-check client (`httpx`) with timeout + fail-open fallback
- `models.py` — pydantic request/response models, hand-written to match `openapi.yaml`
- `config.py` — env var config loading
- FastAPI derives its own OpenAPI doc from `models.py`/`main.py` — the
  contract direction is inverted from Go's spec-to-code `oapi-codegen`
  (code-to-spec here instead), a deliberate comparison data point.

**Node** (`node/`): flat module layout, no generated code layer, same 1:1
package split as Python.
- `app.js` — builds the Express app + all endpoint routes (exported, not run)
- `server.js` — entry point: loads config, opens the store, starts listening
- `store.js` — SQLite access via the stdlib `node:sqlite` module (`DatabaseSync`,
  experimental as of Node 22+, but needs no native npm dependency)
- `auth.js` — JWT issue/verify (`jsonwebtoken`) + password hashing (`bcryptjs`)
- `profanity.js` — profanity-check client using the global `fetch` +
  `AbortSignal.timeout`, with timeout + fail-open fallback
- `config.js` — env var config loading
- `node:sqlite`'s `DatabaseSync` is synchronous, so unlike Go/Python there's
  no connection pool or lock needed to avoid concurrent-writer races — a
  deliberate comparison data point on Node's single-threaded execution model.

**Bun** (`bun/`): flat module layout, same 1:1 package split as Node, in
TypeScript instead of JavaScript.
- `app.ts` — builds the Elysia app + all endpoint routes (exported, not run)
- `server.ts` — entry point: loads config, opens the store, starts listening
- `store.ts` — SQLite access via the built-in `bun:sqlite` module (`Database`,
  stable, no npm dependency)
- `auth.ts` — password hashing via the built-in `Bun.password` (bcrypt, no
  npm dependency); JWT issue/verify via the `@elysiajs/jwt` plugin, wired
  into `app.ts` rather than a standalone function
- `profanity.ts` — profanity-check client using the global `fetch` +
  `AbortSignal.timeout`, same as `node/profanity.js`
- `config.ts` — env var config loading; Bun auto-loads `.env` from the
  working directory, so unlike the other four stacks no explicit dotenv
  dependency or `--env-file` flag is needed
- Request validation is expressed as Elysia `t.Object` (TypeBox) schemas per
  route instead of hand-written `if` checks — declarative, closer to
  Python's pydantic than to Node's manual checks, and Bun's headline
  ergonomics difference from Node in this comparison
- `bun:sqlite` and `Bun.password` mean Bun is the only stack needing zero
  dependency for *either* SQLite or bcrypt — the same two primitives that
  force Ballerina into Java interop

**All five stacks implement the same behavioral contract**: consistent JSON error
envelope on all error responses, ownership checks on post/comment writes,
`GET /posts/{id}` fans out author + comments + comment-authors concurrently
(goroutines in Go, workers in Ballerina, `asyncio.gather` in Python,
`Promise.all` in Node and Bun) and joins the results, and the profanity check
on post/comment bodies has a timeout with fail-open fallback if the stub is
unreachable — see `README.md`'s Technical Criteria table for the full list.
One documented divergence: Bun's schema validation runs before its
handler-level auth check, so a request that is simultaneously unauthenticated
*and* has an invalid body returns `400 validation_failed` there instead of
the `401 unauthorized` the other four return — a side effect of Elysia's
validate-before-beforeHandle lifecycle, not a contract bug. Every
single-condition case (auth-only, body-only) matches across all five.

**mock-profanity-api** (`mock-profanity-api/`): dependency-free `net/http`
stub, not part of the comparison itself — supports forcing slow/failing
responses to exercise the timeout/fallback path deterministically in all
five stacks.

## Commit messages

This project does not use Conventional Commits (no `feat:`, `fix:`, `chore:` prefixes).
Write plain, lowercase-first-word commit messages, e.g. `add shared OpenAPI contract`
instead of `feat: add shared OpenAPI contract`.

Keep messages simple — a short summary line, plus body lines only when the "why"
isn't obvious from the diff.

Each commit should be self-contained: one logical change per commit, buildable and
coherent on its own, not a partial step that only makes sense combined with a later
commit.
