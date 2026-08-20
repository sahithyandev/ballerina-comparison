// Elysia app, mounted at /api/v1 — mirrors node/app.js endpoint-for-endpoint.
// Structural validation (required fields, string lengths, pagination
// bounds) is expressed as Elysia `t.Object` schemas per route instead of
// hand-written `if` checks — the idiomatic Elysia way, and this stack's
// data point for "declarative runtime validation" alongside Python's
// pydantic. Ownership checks and the profanity call stay hand-written,
// since no schema expresses either.
import { Elysia, t, status } from 'elysia';
import { jwt } from '@elysiajs/jwt';

import * as auth from './auth';
import { Store, NotFound, type Post, type Comment, type User } from './store';
import { Checker } from './profanity';

export interface AppDeps {
  store: Store;
  profanity: Checker;
  jwtSecret: string;
  jwtExpirySeconds: number;
}

function errBody(code: string, message: string) {
  return { error: { code, message } };
}

function toApiUser(u: User) {
  return { id: u.id, username: u.username, email: u.email, created_at: u.created_at };
}

function toApiPost(p: Post) {
  return {
    id: p.id,
    author_id: p.author_id,
    title: p.title,
    body: p.body,
    published: p.published,
    created_at: p.created_at,
  };
}

export function buildApp({ store, profanity, jwtSecret, jwtExpirySeconds }: AppDeps) {
  const paginationQuery = t.Object({
    page: t.Optional(t.Numeric({ minimum: 1, error: 'page must be >=1' })),
    limit: t.Optional(t.Numeric({ minimum: 1, maximum: 100, error: 'limit must be 1-100' })),
  });

  const app = new Elysia({ prefix: '/api/v1' })
    .use(jwt({ name: 'jwt', secret: jwtSecret, alg: 'HS256' }))
    .onRequest(({ request }) => {
      console.log(JSON.stringify({ level: 'info', method: request.method, path: new URL(request.url).pathname }));
    })
    // Every request gets a resolved (possibly null) userId, computed once
    // from the bearer token — protected handlers just check it's set.
    .derive({ as: 'global' }, async ({ headers, jwt }) => {
      const authHeader = headers.authorization || '';
      const prefix = 'Bearer ';
      if (!authHeader.startsWith(prefix)) return { userId: null as number | null };
      const claims = await jwt.verify(authHeader.slice(prefix.length));
      if (!claims || typeof claims.user_id !== 'number') return { userId: null as number | null };
      return { userId: claims.user_id as number };
    })
    .onError(({ code, error, set }) => {
      switch (code) {
        case 'VALIDATION':
          set.status = 400;
          return errBody('validation_failed', error.message);
        case 'PARSE':
          set.status = 400;
          return errBody('invalid_body', 'request body is not valid JSON');
        case 'NOT_FOUND':
          set.status = 404;
          return errBody('not_found', 'resource not found');
        default:
          console.error('unhandled error:', error);
          set.status = 500;
          return errBody('internal_error', 'internal server error');
      }
    })

    // --- POST /auth/register ---
    .post(
      '/auth/register',
      async ({ body, jwt, set }) => {
        const passwordHash = await auth.hashPassword(body.password);
        let u;
        try {
          u = store.createUser(body.username, body.email, passwordHash);
        } catch {
          return status(409, errBody('user_exists', 'username or email already registered'));
        }
        const token = await jwt.sign({ user_id: u.id, exp: `${jwtExpirySeconds}s` });
        set.status = 201;
        return { token, user: toApiUser(u) };
      },
      {
        body: t.Object({
          username: t.String({ minLength: 3, error: 'username (>=3 chars) is required' }),
          email: t.String({ format: 'email', error: 'a valid email is required' }),
          password: t.String({ minLength: 8, error: 'password (>=8 chars) is required' }),
        }),
      },
    )

    // --- POST /auth/login ---
    .post(
      '/auth/login',
      async ({ body, jwt, set }) => {
        let u;
        try {
          u = store.getUserByEmail(body.email);
        } catch (err) {
          if (err instanceof NotFound) {
            return status(401, errBody('invalid_credentials', 'email or password is incorrect'));
          }
          throw err;
        }
        if (!(await auth.checkPassword(u.password_hash, body.password))) {
          return status(401, errBody('invalid_credentials', 'email or password is incorrect'));
        }
        const token = await jwt.sign({ user_id: u.id, exp: `${jwtExpirySeconds}s` });
        return { token, user: toApiUser(u) };
      },
      {
        body: t.Object({
          email: t.String(),
          password: t.String(),
        }),
      },
    )

    // --- GET /posts ---
    .get(
      '/posts',
      ({ query }) => {
        const page = query.page ?? 1;
        const limit = query.limit ?? 20;
        const published = query.published !== undefined ? query.published : null;
        const [posts, total] = store.listPosts(published, limit, (page - 1) * limit);
        return { posts: posts.map(toApiPost), page, limit, total };
      },
      {
        query: t.Object({
          page: t.Optional(t.Numeric({ minimum: 1, error: 'page must be >=1' })),
          limit: t.Optional(t.Numeric({ minimum: 1, maximum: 100, error: 'limit must be 1-100' })),
          published: t.Optional(t.Boolean()),
        }),
      },
    )

    // --- POST /posts ---
    .post(
      '/posts',
      async ({ body, userId, set }) => {
        if (userId === null) return status(401, errBody('unauthorized', 'missing bearer token'));
        if (!(await profanity.isClean(`${body.title} ${body.body}`))) {
          return status(400, errBody('validation_failed', 'content contains profanity'));
        }
        const p = store.createPost(userId, body.title, body.body, Boolean(body.published));
        set.status = 201;
        return toApiPost(p);
      },
      {
        body: t.Object({
          title: t.String({ minLength: 1, error: 'title and body are required' }),
          body: t.String({ minLength: 1, error: 'title and body are required' }),
          published: t.Optional(t.Boolean()),
        }),
      },
    )

    // --- PUT /posts/:id ---
    .put(
      '/posts/:id',
      async ({ params, body, userId }) => {
        if (userId === null) return status(401, errBody('unauthorized', 'missing bearer token'));
        const id = Number(params.id);
        let post: Post;
        try {
          post = store.getPost(id);
        } catch (err) {
          if (err instanceof NotFound) return status(404, errBody('not_found', 'post not found'));
          throw err;
        }
        if (post.author_id !== userId) {
          return status(403, errBody('forbidden', 'only the author can modify this post'));
        }

        const checkTitle = body.title ?? post.title;
        const checkBody = body.body ?? post.body;
        if (!(await profanity.isClean(`${checkTitle} ${checkBody}`))) {
          return status(400, errBody('validation_failed', 'content contains profanity'));
        }

        const updated = store.updatePost(id, body);
        return toApiPost(updated);
      },
      {
        body: t.Object({
          title: t.Optional(t.String({ minLength: 1, error: 'title cannot be empty' })),
          body: t.Optional(t.String({ minLength: 1, error: 'body cannot be empty' })),
          published: t.Optional(t.Boolean()),
        }),
      },
    )

    // --- DELETE /posts/:id ---
    .delete('/posts/:id', ({ params, userId }) => {
      if (userId === null) return status(401, errBody('unauthorized', 'missing bearer token'));
      const id = Number(params.id);
      let post: Post;
      try {
        post = store.getPost(id);
      } catch (err) {
        if (err instanceof NotFound) return status(404, errBody('not_found', 'post not found'));
        throw err;
      }
      if (post.author_id !== userId) {
        return status(403, errBody('forbidden', 'only the author can delete this post'));
      }
      store.deletePost(id);
      return new Response(null, { status: 204 });
    })

    // --- GET /posts/:id/comments ---
    .get(
      '/posts/:id/comments',
      async ({ params, query }) => {
        const id = Number(params.id);
        try {
          store.getPost(id);
        } catch (err) {
          if (err instanceof NotFound) return status(404, errBody('not_found', 'post not found'));
          throw err;
        }
        const page = query.page ?? 1;
        const limit = query.limit ?? 20;
        const [comments, total] = store.listCommentsPage(id, limit, (page - 1) * limit);
        const withAuthors = await attachAuthors(store, comments);
        return { comments: withAuthors, page, limit, total };
      },
      { query: paginationQuery },
    )

    // --- POST /posts/:id/comments ---
    .post(
      '/posts/:id/comments',
      async ({ params, body, userId }) => {
        if (userId === null) return status(401, errBody('unauthorized', 'missing bearer token'));
        const id = Number(params.id);
        try {
          store.getPost(id);
        } catch (err) {
          if (err instanceof NotFound) return status(404, errBody('not_found', 'post not found'));
          throw err;
        }
        if (!(await profanity.isClean(body.body))) {
          return status(400, errBody('validation_failed', 'content contains profanity'));
        }
        const c = store.createComment(id, userId, body.body);
        return status(201, {
          id: c.id, post_id: c.post_id, author_id: c.author_id, body: c.body, created_at: c.created_at,
        });
      },
      {
        body: t.Object({
          body: t.String({ minLength: 1, error: 'body is required' }),
        }),
      },
    )

    // --- GET /posts/:id ---
    //
    // Fan-out join point (plan.md criterion #7): fetches the post's author
    // and its comments concurrently via Promise.all, then each comment's
    // author concurrently too. Unlike Express, Elysia's radix router
    // doesn't care about registration order relative to
    // /posts/:id/comments — no ordering workaround needed here.
    .get('/posts/:id', async ({ params }) => {
      const id = Number(params.id);
      let post: Post;
      try {
        post = store.getPost(id);
      } catch (err) {
        if (err instanceof NotFound) return status(404, errBody('not_found', 'post not found'));
        throw err;
      }

      const [author, comments] = await Promise.all([
        store.getUserById(post.author_id),
        store.listCommentsByPost(post.id),
      ]);
      const apiComments = await attachAuthors(store, comments);

      return { ...toApiPost(post), author: toApiUser(author), comments: apiComments };
    });

  return app;
}

async function attachAuthors(store: Store, comments: Comment[]) {
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
