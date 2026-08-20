// Express app, mounted at /api/v1 — mirrors go/internal/handlers/handlers.go
// endpoint-for-endpoint. No generated layer, no schema validation library:
// request shape is checked by hand, same as Go.
'use strict';

const express = require('express');

const auth = require('./auth');
const { NotFound } = require('./store');

function buildApp({ store, profanity, jwtSecret, jwtExpirySeconds }) {
  const app = express();
  app.use(express.json());

  app.use((req, res, next) => {
    console.log(JSON.stringify({ level: 'info', method: req.method, path: req.path }));
    next();
  });

  function errBody(code, message) {
    return { error: { code, message } };
  }

  function sendErr(res, status, code, message) {
    res.status(status).json(errBody(code, message));
  }

  function toApiUser(u) {
    return { id: u.id, username: u.username, email: u.email, created_at: u.created_at };
  }

  function toApiPost(p) {
    return {
      id: p.id,
      author_id: p.author_id,
      title: p.title,
      body: p.body,
      published: p.published,
      created_at: p.created_at,
    };
  }

  function requireAuth(req, res, next) {
    const header = req.get('Authorization') || '';
    const prefix = 'Bearer ';
    if (!header.startsWith(prefix)) {
      return sendErr(res, 401, 'unauthorized', 'missing bearer token');
    }
    try {
      req.userId = auth.parseToken(jwtSecret, header.slice(prefix.length));
    } catch {
      return sendErr(res, 401, 'unauthorized', 'invalid or expired token');
    }
    next();
  }

  async function attachAuthors(comments) {
    const authors = await Promise.all(comments.map((c) => store.getUserById(c.author_id)));
    return comments.map((c, i) => ({
      id: c.id,
      post_id: c.post_id,
      author_id: c.author_id,
      body: c.body,
      created_at: c.created_at,
      author: toApiUser(authors[i]),
    }));
  }

  // Wraps an async handler so a rejected promise reaches Express's error
  // pipeline instead of crashing the process.
  const h = (fn) => (req, res, next) => fn(req, res, next).catch(next);

  // --- POST /auth/register ---
  app.post(
    '/api/v1/auth/register',
    h(async (req, res) => {
      const { username, email, password } = req.body || {};
      if (!username || typeof username !== 'string' || username.length < 3 ||
          !password || typeof password !== 'string' || password.length < 8 ||
          !email) {
        return sendErr(res, 400, 'validation_failed',
          'username (>=3 chars), password (>=8 chars) and email are required');
      }

      const passwordHash = auth.hashPassword(password);
      let u;
      try {
        u = store.createUser(username, email, passwordHash);
      } catch {
        return sendErr(res, 409, 'user_exists', 'username or email already registered');
      }

      const token = auth.issueToken(jwtSecret, jwtExpirySeconds, u.id);
      res.status(201).json({ token, user: toApiUser(u) });
    }),
  );

  // --- POST /auth/login ---
  app.post(
    '/api/v1/auth/login',
    h(async (req, res) => {
      const { email, password } = req.body || {};
      let u;
      try {
        u = store.getUserByEmail(email);
      } catch (err) {
        if (err instanceof NotFound) {
          return sendErr(res, 401, 'invalid_credentials', 'email or password is incorrect');
        }
        throw err;
      }
      if (!auth.checkPassword(u.password_hash, password)) {
        return sendErr(res, 401, 'invalid_credentials', 'email or password is incorrect');
      }

      const token = auth.issueToken(jwtSecret, jwtExpirySeconds, u.id);
      res.json({ token, user: toApiUser(u) });
    }),
  );

  // --- GET /posts ---
  app.get(
    '/api/v1/posts',
    h(async (req, res) => {
      const page = req.query.page !== undefined ? Number(req.query.page) : 1;
      const limit = req.query.limit !== undefined ? Number(req.query.limit) : 20;
      const published = req.query.published !== undefined ? req.query.published === 'true' : null;

      if (!Number.isInteger(page) || page < 1 || !Number.isInteger(limit) || limit < 1 || limit > 100) {
        return sendErr(res, 400, 'validation_failed', 'page must be >=1, limit must be 1-100');
      }

      const [posts, total] = store.listPosts(published, limit, (page - 1) * limit);
      res.json({ posts: posts.map(toApiPost), page, limit, total });
    }),
  );

  // --- POST /posts ---
  app.post(
    '/api/v1/posts',
    requireAuth,
    h(async (req, res) => {
      const { title, body, published } = req.body || {};
      if (!title || !title.trim() || !body || !body.trim()) {
        return sendErr(res, 400, 'validation_failed', 'title and body are required');
      }
      if (!(await profanity.isClean(`${title} ${body}`))) {
        return sendErr(res, 400, 'validation_failed', 'content contains profanity');
      }

      const p = store.createPost(req.userId, title, body, Boolean(published));
      res.status(201).json(toApiPost(p));
    }),
  );

  // --- PUT /posts/{id} ---
  app.put(
    '/api/v1/posts/:id',
    requireAuth,
    h(async (req, res) => {
      const id = Number(req.params.id);
      let post;
      try {
        post = store.getPost(id);
      } catch (err) {
        if (err instanceof NotFound) return sendErr(res, 404, 'not_found', 'post not found');
        throw err;
      }
      if (post.author_id !== req.userId) {
        return sendErr(res, 403, 'forbidden', 'only the author can modify this post');
      }

      const { title, body, published } = req.body || {};
      if (title !== undefined && title !== null && !title.trim()) {
        return sendErr(res, 400, 'validation_failed', 'title cannot be empty');
      }
      if (body !== undefined && body !== null && !body.trim()) {
        return sendErr(res, 400, 'validation_failed', 'body cannot be empty');
      }

      const checkTitle = title ?? post.title;
      const checkBody = body ?? post.body;
      if (!(await profanity.isClean(`${checkTitle} ${checkBody}`))) {
        return sendErr(res, 400, 'validation_failed', 'content contains profanity');
      }

      const updated = store.updatePost(id, { title, body, published });
      res.json(toApiPost(updated));
    }),
  );

  // --- DELETE /posts/{id} ---
  app.delete(
    '/api/v1/posts/:id',
    requireAuth,
    h(async (req, res) => {
      const id = Number(req.params.id);
      let post;
      try {
        post = store.getPost(id);
      } catch (err) {
        if (err instanceof NotFound) return sendErr(res, 404, 'not_found', 'post not found');
        throw err;
      }
      if (post.author_id !== req.userId) {
        return sendErr(res, 403, 'forbidden', 'only the author can delete this post');
      }

      store.deletePost(id);
      res.status(204).end();
    }),
  );

  // --- GET /posts/{id}/comments ---
  app.get(
    '/api/v1/posts/:id/comments',
    h(async (req, res) => {
      const id = Number(req.params.id);
      try {
        store.getPost(id);
      } catch (err) {
        if (err instanceof NotFound) return sendErr(res, 404, 'not_found', 'post not found');
        throw err;
      }

      const page = req.query.page !== undefined ? Number(req.query.page) : 1;
      const limit = req.query.limit !== undefined ? Number(req.query.limit) : 20;
      if (!Number.isInteger(page) || page < 1 || !Number.isInteger(limit) || limit < 1 || limit > 100) {
        return sendErr(res, 400, 'validation_failed', 'page must be >=1, limit must be 1-100');
      }

      const [comments, total] = store.listCommentsPage(id, limit, (page - 1) * limit);
      const withAuthors = await attachAuthors(comments);
      res.json({ comments: withAuthors, page, limit, total });
    }),
  );

  // --- POST /posts/{id}/comments ---
  app.post(
    '/api/v1/posts/:id/comments',
    requireAuth,
    h(async (req, res) => {
      const id = Number(req.params.id);
      try {
        store.getPost(id);
      } catch (err) {
        if (err instanceof NotFound) return sendErr(res, 404, 'not_found', 'post not found');
        throw err;
      }

      const { body } = req.body || {};
      if (!body || !body.trim()) {
        return sendErr(res, 400, 'validation_failed', 'body is required');
      }
      if (!(await profanity.isClean(body))) {
        return sendErr(res, 400, 'validation_failed', 'content contains profanity');
      }

      const c = store.createComment(id, req.userId, body);
      res.status(201).json({
        id: c.id, post_id: c.post_id, author_id: c.author_id, body: c.body, created_at: c.created_at,
      });
    }),
  );

  // --- GET /posts/{id} ---
  //
  // Fan-out join point (plan.md criterion #7): fetches the post's author and
  // its comments concurrently via Promise.all, then each comment's author
  // concurrently too — the goroutines/workers-vs-event-loop comparison point.
  app.get(
    '/api/v1/posts/:id',
    h(async (req, res) => {
      const id = Number(req.params.id);
      let post;
      try {
        post = store.getPost(id);
      } catch (err) {
        if (err instanceof NotFound) return sendErr(res, 404, 'not_found', 'post not found');
        throw err;
      }

      const [author, comments] = await Promise.all([
        store.getUserById(post.author_id),
        store.listCommentsByPost(post.id),
      ]);
      const apiComments = await attachAuthors(comments);

      res.json({ ...toApiPost(post), author: toApiUser(author), comments: apiComments });
    }),
  );

  app.use((req, res) => sendErr(res, 404, 'not_found', 'resource not found'));

  // eslint-disable-next-line no-unused-vars
  app.use((err, req, res, next) => {
    if (err instanceof SyntaxError && 'body' in err) {
      return sendErr(res, 400, 'invalid_body', 'request body is not valid JSON');
    }
    console.error('unhandled error:', err);
    sendErr(res, 500, 'internal_error', 'internal server error');
  });

  return app;
}

module.exports = { buildApp };
