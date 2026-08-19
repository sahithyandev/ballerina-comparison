# Ballerina vs Go — Backend API Comparison

Build the *same* backend service in Ballerina and Go, then compare them on
code, ergonomics, and behavior — not benchmarks alone.

## The Sample Backend

A blogging platform API with Users, Posts, and Comments. Small but
recognizable — every technical checkbox gets a natural reason to exist.

**Domain**
- `User`: id, username, email, password_hash
- `Post`: id, author_id, title, body, published, created_at
- `Comment`: id, post_id, author_id, body, created_at

**Conventions**
- Base path: `/api/v1`
- Pagination: `?page=&limit=` (1-indexed, default limit 20)
- Passwords: bcrypt
- JWT: HS256, secret + expiry from env vars (same values both stacks)
- `DELETE /posts/{id}` cascades to comments via SQLite `ON DELETE CASCADE`
- Profanity check: local stub server with a toggle to force slow/failing responses

## Endpoints

| Method | Path | Auth |
|--------|------|------|
| `POST` | `/auth/register` | — |
| `POST` | `/auth/login` | — |
| `GET` | `/posts` | — |
| `GET` | `/posts/{id}` | — |
| `POST` | `/posts` | JWT, author-only |
| `PUT` | `/posts/{id}` | JWT, author-only |
| `DELETE` | `/posts/{id}` | JWT, author-only |
| `POST` | `/posts/{id}/comments` | JWT |
| `GET` | `/posts/{id}/comments` | — |

## Technical Criteria

Both stacks are evaluated against the same checklist:

1. **REST CRUD** — posts and comments
2. **Persistence** — SQLite (file-based, zero setup, shared schema)
3. **Input validation** — structured 400s (empty title, bad email, etc.)
4. **Auth** — JWT bearer auth, ownership checks on write endpoints
5. **Error handling** — consistent error envelope, no leaking stack traces
6. **External HTTP call** — profanity-check stub with timeout + graceful fallback
7. **Concurrency** — fan-out on `GET /posts/{id}` (Ballerina workers vs Go goroutines)
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
├── mock-profanity-api/  # Stub server (Go, net/http, no deps)
├── openapi.yaml         # Shared OpenAPI spec (source of truth for both stacks)
├── schema.sql           # Shared SQLite schema (users/posts/comments, cascade delete)
├── seed.sql             # Shared deterministic fixture data
├── .env.example         # Shared env var template (copy to .env in each stack dir)
├── plan.md              # Detailed build plan
├── CLAUDE.md            # Working conventions for this repo (e.g. commit style)
└── LICENSE              # MIT
```

`RESULTS.md` (comparison writeup) and a load-test script land once both stacks
are feature-complete — see `plan.md` for the full order of work.

## Current Status

All endpoints from the table above are built and verified in both stacks:
full post/comment CRUD, ownership checks on writes, pagination, structured
validation errors, and the profanity check with timeout + graceful fallback
when the stub is down. Tests, containerization, and the load-test writeup
(steps 5-8 of `plan.md`) are still pending.

## Getting Started

**Prerequisites**: Ballerina 2201.13+, Go 1.21+, `sqlite3`, Docker (optional)

1. Copy the env template and fill in a real `JWT_SECRET` (required — both
   stacks fail to start without it):
   ```bash
   cp .env.example ballerina/.env   # or go/.env
   ```
2. Create each stack's SQLite file from the shared schema + seed data:
   ```bash
   cd go && sqlite3 blog.db < ../schema.sql && sqlite3 blog.db < ../seed.sql
   cd ballerina && sqlite3 blog.db < ../schema.sql && sqlite3 blog.db < ../seed.sql
   ```
3. Start the mock profanity-check server:
   ```bash
   cd mock-profanity-api && go run .
   ```
4. Start either stack (or both, on different `PORT`s — see `.env.example`):
   ```bash
   # Go
   cd go && go run .

   # Ballerina
   cd ballerina && bal run .
   ```
5. Smoke-test the vertical slice:
   ```bash
   curl -X POST localhost:8080/api/v1/auth/register \
     -H "Content-Type: application/json" \
     -d '{"username":"carol","email":"carol@example.com","password":"password123"}'

   curl localhost:8080/api/v1/posts/1
   ```

## License

MIT
