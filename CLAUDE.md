# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A head-to-head comparison of Ballerina vs Go: the *same* blogging platform API
(users/posts/comments, JWT auth, SQLite, profanity-check external call,
concurrent fan-out) is implemented twice, once per stack, against one shared
`openapi.yaml` contract and one shared `schema.sql`. The goal is a comparison
writeup (`RESULTS.md`, not yet written), not a production service — see
`plan.md` for the full criteria list and `README.md` for current status.

Any change to behavior (validation rules, error envelope shape, endpoints)
should generally be made in **both** `ballerina/` and `go/` to keep the
comparison fair, unless the task is explicitly about one stack only.

## Commands

**Run everything** (three processes, each in its own terminal):
```bash
cd mock-profanity-api && go run .        # stub server, port 9090
cd go && go run .                        # Go API, port 8080 (or PORT from .env)
cd ballerina && bal run .                # Ballerina API, alt port if run alongside Go
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
cd ballerina && bal test
cd ballerina && bal run .
```
`ballerina/tests/service_test.bal` currently only has the scaffolded sample
tests from `bal new` (greeting service) — not real tests for this API yet.

**DB setup** (both stacks read/write their own `blog.db` from the same schema):
```bash
sqlite3 blog.db < ../schema.sql && sqlite3 blog.db < ../seed.sql
```

Both stacks require a `.env` (copied from `.env.example`) with `JWT_SECRET`
set — they fail to start without it. Same env var values are used by both
stacks intentionally (see `.env.example`).

## Architecture

**Shared contract, independent implementations.** `openapi.yaml` and
`schema.sql` at the repo root are the single source of truth both stacks
implement against; there is no shared code between `ballerina/`, `go/`, and
`mock-profanity-api/`.

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

**Both stacks implement the same behavioral contract**: consistent JSON error
envelope on all error responses, ownership checks on post/comment writes,
`GET /posts/{id}` fans out author + comments + comment-authors concurrently
(goroutines in Go, workers in Ballerina) and joins the results, and the
profanity check on post/comment bodies has a timeout with fail-open fallback
if the stub is unreachable — see `README.md`'s Technical Criteria table for
the full list.

**mock-profanity-api** (`mock-profanity-api/`): dependency-free `net/http`
stub, not part of the comparison itself — supports forcing slow/failing
responses to exercise the timeout/fallback path deterministically in both
stacks.

## Commit messages

This project does not use Conventional Commits (no `feat:`, `fix:`, `chore:` prefixes).
Write plain, lowercase-first-word commit messages, e.g. `add shared OpenAPI contract`
instead of `feat: add shared OpenAPI contract`.

Keep messages simple — a short summary line, plus body lines only when the "why"
isn't obvious from the diff.

Each commit should be self-contained: one logical change per commit, buildable and
coherent on its own, not a partial step that only makes sense combined with a later
commit.
