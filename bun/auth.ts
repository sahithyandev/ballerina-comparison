// Password hashing (plan.md criterion #4). Mirrors go/internal/auth/auth.go
// and node/auth.js, but needs no bcrypt dependency at all — Bun.password is
// built into the runtime and supports bcrypt natively (verifies seed.sql's
// `$2a$` hashes unchanged). JWT issue/verify lives in app.ts via the
// idiomatic `@elysiajs/jwt` plugin instead of a standalone function here.

export function hashPassword(password: string): Promise<string> {
  return Bun.password.hash(password, { algorithm: 'bcrypt', cost: 10 });
}

export function checkPassword(hash: string, password: string): Promise<boolean> {
  return Bun.password.verify(password, hash);
}
