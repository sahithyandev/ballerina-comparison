// Integration suite against a temp SQLite db built from schema.sql, with an
// unreachable profanity URL so the fail-open fallback (plan.md criterion
// #6) is exercised on every write — same trick as the Go/Python/Ballerina
// suites. Uses node:test + node:assert (stdlib) and the global fetch
// against a real listening server — no supertest/jest dependency needed.
'use strict';

const assert = require('node:assert/strict');
const { test, before, after, beforeEach } = require('node:test');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { Store } = require('../store');
const { Checker } = require('../profanity');
const { buildApp } = require('../app');

let server;
let baseUrl;
let dbPath;

before(() => {
  dbPath = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'blog-node-test-')), 'test.db');
  const schema = fs.readFileSync(path.join(__dirname, '..', '..', 'schema.sql'), 'utf8');
  const store = new Store(dbPath);
  store.db.exec(schema);

  const profanity = new Checker('http://127.0.0.1:1', 200); // nothing listens -> fails open
  const app = buildApp({ store, profanity, jwtSecret: 'test-secret', jwtExpirySeconds: 3600 });

  return new Promise((resolve) => {
    server = app.listen(0, () => {
      baseUrl = `http://127.0.0.1:${server.address().port}/api/v1`;
      resolve();
    });
  });
});

after(() => {
  return new Promise((resolve) => server.close(resolve));
});

let userCounter = 0;
async function register(overrides = {}) {
  userCounter += 1;
  const body = {
    username: `user${userCounter}`,
    email: `user${userCounter}@example.com`,
    password: 'password123',
    ...overrides,
  };
  const resp = await fetch(`${baseUrl}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return resp;
}

test('register validation rejects short username/password', async () => {
  const resp = await register({ username: 'ab', password: 'short' });
  assert.equal(resp.status, 400);
  const json = await resp.json();
  assert.equal(json.error.code, 'validation_failed');
});

test('register then login succeeds', async () => {
  const resp = await register({ username: 'alice1', email: 'alice1@example.com' });
  assert.equal(resp.status, 201);
  const body = await resp.json();
  assert.equal(body.user.username, 'alice1');
  assert.ok(body.token);

  const login = await fetch(`${baseUrl}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'alice1@example.com', password: 'password123' }),
  });
  assert.equal(login.status, 200);
  assert.ok((await login.json()).token);
});

test('duplicate register is rejected', async () => {
  await register({ username: 'dup1', email: 'dup1@example.com' });
  const resp = await register({ username: 'dup1b', email: 'dup1@example.com' });
  assert.equal(resp.status, 409);
  assert.equal((await resp.json()).error.code, 'user_exists');
});

test('login with wrong password is rejected', async () => {
  await register({ username: 'wrongpw', email: 'wrongpw@example.com' });
  const resp = await fetch(`${baseUrl}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'wrongpw@example.com', password: 'nope-nope-nope' }),
  });
  assert.equal(resp.status, 401);
  assert.equal((await resp.json()).error.code, 'invalid_credentials');
});

test('creating a post requires auth', async () => {
  const resp = await fetch(`${baseUrl}/posts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 't', body: 'b' }),
  });
  assert.equal(resp.status, 401);
});

test('post CRUD and GET /posts/{id} fan-out', async () => {
  const reg = await register({ username: 'fanout', email: 'fanout@example.com' });
  const { token } = await reg.json();
  const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };

  const created = await fetch(`${baseUrl}/posts`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ title: 'Hello', body: 'World', published: true }),
  });
  assert.equal(created.status, 201);
  const post = await created.json();

  const comment = await fetch(`${baseUrl}/posts/${post.id}/comments`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ body: 'nice post' }),
  });
  assert.equal(comment.status, 201);

  const detail = await (await fetch(`${baseUrl}/posts/${post.id}`)).json();
  assert.equal(detail.author.username, 'fanout');
  assert.equal(detail.comments.length, 1);
  assert.equal(detail.comments[0].author.username, 'fanout');
});

test('ownership check returns 403 for non-authors', async () => {
  const a = await (await register({ username: 'owner', email: 'owner@example.com' })).json();
  const b = await (await register({ username: 'intruder', email: 'intruder@example.com' })).json();

  const post = await (
    await fetch(`${baseUrl}/posts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${a.token}` },
      body: JSON.stringify({ title: 't', body: 'b' }),
    })
  ).json();

  const resp = await fetch(`${baseUrl}/posts/${post.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${b.token}` },
    body: JSON.stringify({ title: 'hijacked' }),
  });
  assert.equal(resp.status, 403);
  assert.equal((await resp.json()).error.code, 'forbidden');
});

test('missing post returns 404', async () => {
  const reg = await (await register({ username: 'notfound', email: 'notfound@example.com' })).json();
  const resp = await fetch(`${baseUrl}/posts/999999`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${reg.token}` },
  });
  assert.equal(resp.status, 404);
  assert.equal((await resp.json()).error.code, 'not_found');
});

test('deleting a post cascades its comments', async () => {
  const reg = await (await register({ username: 'cascade', email: 'cascade@example.com' })).json();
  const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${reg.token}` };

  const post = await (
    await fetch(`${baseUrl}/posts`, { method: 'POST', headers, body: JSON.stringify({ title: 't', body: 'b' }) })
  ).json();
  await fetch(`${baseUrl}/posts/${post.id}/comments`, { method: 'POST', headers, body: JSON.stringify({ body: 'c1' }) });

  const del = await fetch(`${baseUrl}/posts/${post.id}`, { method: 'DELETE', headers });
  assert.equal(del.status, 204);

  const comments = await fetch(`${baseUrl}/posts/${post.id}/comments`);
  assert.equal(comments.status, 404);
});

test('pagination bounds are enforced', async () => {
  assert.equal((await fetch(`${baseUrl}/posts?page=0`)).status, 400);
  assert.equal((await fetch(`${baseUrl}/posts?limit=101`)).status, 400);
  const ok = await fetch(`${baseUrl}/posts?page=1&limit=20`);
  assert.equal(ok.status, 200);
  assert.equal((await ok.json()).page, 1);
});

test('profanity check fails open when the stub is unreachable', async () => {
  const reg = await (await register({ username: 'failopen', email: 'failopen@example.com' })).json();
  const resp = await fetch(`${baseUrl}/posts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${reg.token}` },
    body: JSON.stringify({ title: 't', body: 'b' }),
  });
  assert.equal(resp.status, 201);
});
