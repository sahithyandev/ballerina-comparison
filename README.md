# Ballerina vs Others (Backend API Comparison)

In this repository, I am comparing the performance, code size, developer ergonomics, and behavior of Ballerina against other backend stacks. Namely:

<!--TODO: convert this to a table with versions-->
- Ballerinaa
- Go
- Python with FastAPI
- Node.js with Express
- Bun with Elysia
- Rust axum

Each one is included in their own directory. Other stacks may be added in the future.

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
| `POST`   | `/auth/register`       | —                |
| `POST`   | `/auth/login`          | —                |
| `GET`    | `/posts`               | —                |
| `GET`    | `/posts/{id}`          | —                |
| `POST`   | `/posts`               | JWT, author-only |
| `PUT`    | `/posts/{id}`          | JWT, author-only |
| `DELETE` | `/posts/{id}`          | JWT, author-only |
| `POST`   | `/posts/{id}/comments` | JWT              |
| `GET`    | `/posts/{id}/comments` | —                |

## Technical Criteria

All stacks are evaluated against the same checklist:

1. **REST CRUD** — posts and comments
2. **Persistence** — SQLite (file-based, zero setup, shared schema)
3. **Input validation** — structured 400s (empty title, bad email, etc.)
4. **Auth** — JWT bearer auth, ownership checks on write endpoints
5. **Error handling** — consistent error envelope, no leaking stack traces
6. **External HTTP call** — profanity-check stub with timeout + graceful fallback
7. **Concurrency** — fan-out on `GET /posts/{id}` (goroutines/workers/asyncio/`Promise.all` in both Node and Bun/tokio in Rust)
8. **Structured logging**
9. **Config via env vars**
10. **Tests** — unit tests + integration test against the running service
11. **Containerization** — Dockerfile for each stack

## Comparison Metrics

For each criterion, the writeup captures:

- Lines of code / files needed
- Stdlib vs external dependency
- Compile-time vs runtime error catching
- Concurrency model (goroutines vs workers)
- Startup time, cold build time, Docker image size
- Directional request latency (simple load test, same hardware, same DB)

> These are directional numbers, not rigorous benchmarks.

## Project Structure

```
ballerina-comparison/
├── ballerina/           # Ballerina implementation (bal openapi + java.jdbc + jwt)
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

`RESULTS.md` — the comparison writeup — see `plan.md` for the full order of work.

## Current Status

All endpoints from the table above are built and verified in all six
stacks: full post/comment CRUD, ownership checks on writes, pagination,
structured validation errors, and the profanity check with timeout +
graceful fallback when the stub is down. Each stack has a test suite
covering validation, auth, ownership checks, and the `GET /posts/{id}`
fan-out (see `CLAUDE.md` for how to run each). Load testing is done and the
comparison writeup is in `RESULTS.md`. Containerization is still pending.

## Getting Started

**Prerequisites**: Ballerina 2201.13+, Go 1.21+, Python 3.11+, Node 22+,
Bun 1.3+, Rust 1.75+, `sqlite3`, Docker (optional)

1. Copy the env template into every stack dir and fill in a real
   `JWT_SECRET` (required — every stack fails to start without it):
   ```bash
   make env
   ```
2. Create each stack's SQLite file from the shared schema + seed data:
   ```bash
   make db
   ```
3. Install each stack's dependencies (Python venv, npm/bun installs):
   ```bash
   make build
   ```
4. Start the mock profanity-check server:
   ```bash
   make run-mock
   ```
5. Start any stack (or all six, on different `PORT`s — see `.env.example`),
   each in its own terminal:
   ```bash
   make run-go          # or run-ballerina, run-python, run-node, run-bun, run-rust
   ```
6. Smoke-test the vertical slice:
   ```bash
   curl -X POST localhost:8080/api/v1/auth/register \
     -H "Content-Type: application/json" \
     -d '{"username":"carol","email":"carol@example.com","password":"password123"}'

   curl localhost:8080/api/v1/posts/1
   ```
