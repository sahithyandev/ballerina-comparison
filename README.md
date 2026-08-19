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
├── ballerina/          # Ballerina implementation
├── go/                 # Go implementation
├── mock-profanity-api/ # Stub server (any language)
├── openapi/            # Shared OpenAPI spec (source of truth)
├── loadtest/           # Reusable load-test script
├── RESULTS.md          # Comparison writeup
├── plan.md             # Detailed build plan
└── LICENSE             # MIT
```

## Getting Started

**Prerequisites**: Ballerina, Go 1.21+, Docker (optional)

1. Run the shared OpenAPI spec and `schema.sql` to set up both stacks
2. Start the mock profanity-check server:
   ```bash
   cd mock-profanity-api && npm install && npm start
   ```
3. Start either stack (or both):
   ```bash
   # Ballerina
   cd ballerina && bal run

   # Go
   cd go && go run .
   ```
4. Run load tests:
   ```bash
   cd loadtest && ./run.sh
   ```

## License

MIT
