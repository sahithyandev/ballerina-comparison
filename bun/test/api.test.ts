// Integration suite against a temp SQLite db built from schema.sql, with an
// unreachable profanity URL so the fail-open fallback (plan.md criterion
// #6) is exercised on every write — same trick as the other four suites.
// Uses bun:test (stdlib runner) and the global fetch against a real
// listening server — no supertest/jest dependency needed.
import { describe, test, expect, beforeAll, afterAll } from 'bun:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { Store } from '../store';
import { Checker } from '../profanity';
import { buildApp } from '../app';

let server: ReturnType<ReturnType<typeof buildApp>['listen']>;
let baseUrl: string;

beforeAll(() => {
  const dbPath = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'blog-bun-test-')), 'test.db');
  const schema = fs.readFileSync(path.join(__dirname, '..', '..', 'schema.sql'), 'utf8');
  const store = new Store(dbPath);
  store.db.exec(schema);

  const profanity = new Checker('http://127.0.0.1:1', 200); // nothing listens -> fails open
  const app = buildApp({ store, profanity, jwtSecret: 'test-secret', jwtExpirySeconds: 3600 });

  server = app.listen(0);
  baseUrl = `http://127.0.0.1:${server.server!.port}/api/v1`;
});

afterAll(() => {
  server.stop(true);
});

let userCounter = 0;
async function register(overrides: Record<string, unknown> = {}) {
  userCounter += 1;
  const body = {
    username: `user${userCounter}`,
    email: `user${userCounter}@example.com`,
    password: 'password123',
    ...overrides,
  };
  return fetch(`${baseUrl}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

describe('bun blog api', () => {
  test('register validation rejects short username/password', async () => {
    const resp = await register({ username: 'ab', password: 'short' });
    expect(resp.status).toBe(400);
    const json = await resp.json() as any;
    expect(json.error.code).toBe('validation_failed');
  });

  test('register then login succeeds', async () => {
    const resp = await register({ username: 'alice1', email: 'alice1@example.com' });
    expect(resp.status).toBe(201);
    const body = await resp.json() as any;
    expect(body.user.username).toBe('alice1');
    expect(body.token).toBeTruthy();

    const login = await fetch(`${baseUrl}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'alice1@example.com', password: 'password123' }),
    });
    expect(login.status).toBe(200);
    expect((await login.json() as any).token).toBeTruthy();
  });

  test('duplicate register is rejected', async () => {
    await register({ username: 'dup1', email: 'dup1@example.com' });
    const resp = await register({ username: 'dup1b', email: 'dup1@example.com' });
    expect(resp.status).toBe(409);
    expect((await resp.json() as any).error.code).toBe('user_exists');
  });

  test('login with wrong password is rejected', async () => {
    await register({ username: 'wrongpw', email: 'wrongpw@example.com' });
    const resp = await fetch(`${baseUrl}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'wrongpw@example.com', password: 'nope-nope-nope' }),
    });
    expect(resp.status).toBe(401);
    expect((await resp.json() as any).error.code).toBe('invalid_credentials');
  });

  test('creating a post requires auth', async () => {
    const resp = await fetch(`${baseUrl}/posts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 't', body: 'b' }),
    });
    expect(resp.status).toBe(401);
  });

  test('post CRUD and GET /posts/{id} fan-out', async () => {
    const reg = await register({ username: 'fanout', email: 'fanout@example.com' });
    const { token } = await reg.json() as any;
    const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };

    const created = await fetch(`${baseUrl}/posts`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ title: 'Hello', body: 'World', published: true }),
    });
    expect(created.status).toBe(201);
    const post = await created.json() as any;

    const comment = await fetch(`${baseUrl}/posts/${post.id}/comments`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ body: 'nice post' }),
    });
    expect(comment.status).toBe(201);

    const detail = await (await fetch(`${baseUrl}/posts/${post.id}`)).json() as any;
    expect(detail.author.username).toBe('fanout');
    expect(detail.comments.length).toBe(1);
    expect(detail.comments[0].author.username).toBe('fanout');
  });

  test('ownership check returns 403 for non-authors', async () => {
    const a = await (await register({ username: 'owner', email: 'owner@example.com' })).json() as any;
    const b = await (await register({ username: 'intruder', email: 'intruder@example.com' })).json() as any;

    const post = await (
      await fetch(`${baseUrl}/posts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${a.token}` },
        body: JSON.stringify({ title: 't', body: 'b' }),
      })
    ).json() as any;

    const resp = await fetch(`${baseUrl}/posts/${post.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${b.token}` },
      body: JSON.stringify({ title: 'hijacked' }),
    });
    expect(resp.status).toBe(403);
    expect((await resp.json() as any).error.code).toBe('forbidden');
  });

  test('missing post returns 404', async () => {
    const reg = await (await register({ username: 'notfound', email: 'notfound@example.com' })).json() as any;
    const resp = await fetch(`${baseUrl}/posts/999999`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${reg.token}` },
    });
    expect(resp.status).toBe(404);
    expect((await resp.json() as any).error.code).toBe('not_found');
  });

  test('deleting a post cascades its comments', async () => {
    const reg = await (await register({ username: 'cascade', email: 'cascade@example.com' })).json() as any;
    const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${reg.token}` };

    const post = await (
      await fetch(`${baseUrl}/posts`, { method: 'POST', headers, body: JSON.stringify({ title: 't', body: 'b' }) })
    ).json() as any;
    await fetch(`${baseUrl}/posts/${post.id}/comments`, { method: 'POST', headers, body: JSON.stringify({ body: 'c1' }) });

    const del = await fetch(`${baseUrl}/posts/${post.id}`, { method: 'DELETE', headers });
    expect(del.status).toBe(204);

    const comments = await fetch(`${baseUrl}/posts/${post.id}/comments`);
    expect(comments.status).toBe(404);
  });

  test('pagination bounds are enforced', async () => {
    expect((await fetch(`${baseUrl}/posts?page=0`)).status).toBe(400);
    expect((await fetch(`${baseUrl}/posts?limit=101`)).status).toBe(400);
    const ok = await fetch(`${baseUrl}/posts?page=1&limit=20`);
    expect(ok.status).toBe(200);
    expect((await ok.json() as any).page).toBe(1);
  });

  test('profanity check fails open when the stub is unreachable', async () => {
    const reg = await (await register({ username: 'failopen', email: 'failopen@example.com' })).json() as any;
    const resp = await fetch(`${baseUrl}/posts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${reg.token}` },
      body: JSON.stringify({ title: 't', body: 'b' }),
    });
    expect(resp.status).toBe(201);
  });
});
