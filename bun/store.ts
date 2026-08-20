// SQLite data access via bun:sqlite (built into the runtime, no npm
// dependency needed) — mirrors go/internal/store/store.go's SQL verbatim,
// same shape as node/store.js (node:sqlite maps 1:1 onto bun:sqlite here).
import { Database } from 'bun:sqlite';

export class NotFound extends Error {}

export interface User {
  id: number;
  username: string;
  email: string;
  password_hash: string;
  created_at: string;
}

export interface Post {
  id: number;
  author_id: number;
  title: string;
  body: string;
  published: boolean;
  created_at: string;
}

export interface Comment {
  id: number;
  post_id: number;
  author_id: number;
  body: string;
  created_at: string;
}

export class Store {
  db: Database;

  constructor(dbPath: string) {
    this.db = new Database(dbPath);
    // Mandatory — SQLite defaults this off, which would silently defeat
    // schema.sql's ON DELETE CASCADE.
    this.db.exec('PRAGMA foreign_keys = ON');
  }

  createUser(username: string, email: string, passwordHash: string): User {
    const { lastInsertRowid } = this.db
      .query('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)')
      .run(username, email, passwordHash);
    return this.getUserById(Number(lastInsertRowid));
  }

  getUserById(id: number): User {
    const row = this.db
      .query<User, [number]>('SELECT id, username, email, password_hash, created_at FROM users WHERE id = ?')
      .get(id);
    if (!row) throw new NotFound();
    return row;
  }

  getUserByEmail(email: string): User {
    const row = this.db
      .query<User, [string]>('SELECT id, username, email, password_hash, created_at FROM users WHERE email = ?')
      .get(email);
    if (!row) throw new NotFound();
    return row;
  }

  getPost(id: number): Post {
    const row = this.db
      .query<any, [number]>('SELECT id, author_id, title, body, published, created_at FROM posts WHERE id = ?')
      .get(id);
    if (!row) throw new NotFound();
    return { ...row, published: Boolean(row.published) };
  }

  listCommentsByPost(postId: number): Comment[] {
    return this.db
      .query<Comment, [number]>('SELECT id, post_id, author_id, body, created_at FROM comments WHERE post_id = ? ORDER BY id')
      .all(postId);
  }

  listCommentsPage(postId: number, limit: number, offset: number): [Comment[], number] {
    const comments = this.db
      .query<Comment, [number, number, number]>(
        'SELECT id, post_id, author_id, body, created_at FROM comments WHERE post_id = ? ORDER BY id LIMIT ? OFFSET ?',
      )
      .all(postId, limit, offset);
    const { total } = this.db
      .query<{ total: number }, [number]>('SELECT count(*) AS total FROM comments WHERE post_id = ?')
      .get(postId)!;
    return [comments, total];
  }

  createComment(postId: number, authorId: number, body: string): Comment {
    const { lastInsertRowid } = this.db
      .query('INSERT INTO comments (post_id, author_id, body) VALUES (?, ?, ?)')
      .run(postId, authorId, body);
    return this.db
      .query<Comment, [number]>('SELECT id, post_id, author_id, body, created_at FROM comments WHERE id = ?')
      .get(Number(lastInsertRowid))!;
  }

  listPosts(published: boolean | null, limit: number, offset: number): [Post[], number] {
    let query = 'SELECT id, author_id, title, body, published, created_at FROM posts';
    let countQuery = 'SELECT count(*) AS total FROM posts';
    const args: (number | string)[] = [];
    if (published !== null) {
      query += ' WHERE published = ?';
      countQuery += ' WHERE published = ?';
      args.push(published ? 1 : 0);
    }
    query += ' ORDER BY id LIMIT ? OFFSET ?';

    const rows = this.db.query<any, any[]>(query).all(...args, limit, offset);
    const { total } = this.db.query<{ total: number }, any[]>(countQuery).get(...args)!;
    return [rows.map((r) => ({ ...r, published: Boolean(r.published) })), total];
  }

  createPost(authorId: number, title: string, body: string, published: boolean): Post {
    const { lastInsertRowid } = this.db
      .query('INSERT INTO posts (author_id, title, body, published) VALUES (?, ?, ?, ?)')
      .run(authorId, title, body, published ? 1 : 0);
    return this.getPost(Number(lastInsertRowid));
  }

  updatePost(id: number, patch: { title?: string; body?: string; published?: boolean }): Post {
    const current = this.getPost(id);
    const newTitle = patch.title ?? current.title;
    const newBody = patch.body ?? current.body;
    const newPublished = patch.published ?? current.published;
    this.db
      .query('UPDATE posts SET title = ?, body = ?, published = ? WHERE id = ?')
      .run(newTitle, newBody, newPublished ? 1 : 0, id);
    return this.getPost(id);
  }

  deletePost(id: number): void {
    this.db.query('DELETE FROM posts WHERE id = ?').run(id);
  }
}
