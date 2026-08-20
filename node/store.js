// SQLite data access via node:sqlite (stable-ish as of Node 22+, no native
// npm dependency needed — mirrors go/internal/store/store.go's SQL verbatim.
'use strict';

const { DatabaseSync } = require('node:sqlite');

class NotFound extends Error {}

class Store {
  constructor(dbPath) {
    this.db = new DatabaseSync(dbPath);
    // Mandatory — SQLite defaults this off, which would silently defeat
    // schema.sql's ON DELETE CASCADE.
    this.db.exec('PRAGMA foreign_keys = ON');
  }

  createUser(username, email, passwordHash) {
    const { lastInsertRowid } = this.db
      .prepare('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)')
      .run(username, email, passwordHash);
    return this.getUserById(Number(lastInsertRowid));
  }

  getUserById(id) {
    const row = this.db
      .prepare('SELECT id, username, email, password_hash, created_at FROM users WHERE id = ?')
      .get(id);
    if (!row) throw new NotFound();
    return row;
  }

  getUserByEmail(email) {
    const row = this.db
      .prepare('SELECT id, username, email, password_hash, created_at FROM users WHERE email = ?')
      .get(email);
    if (!row) throw new NotFound();
    return row;
  }

  getPost(id) {
    const row = this.db
      .prepare('SELECT id, author_id, title, body, published, created_at FROM posts WHERE id = ?')
      .get(id);
    if (!row) throw new NotFound();
    return { ...row, published: Boolean(row.published) };
  }

  listCommentsByPost(postId) {
    return this.db
      .prepare('SELECT id, post_id, author_id, body, created_at FROM comments WHERE post_id = ? ORDER BY id')
      .all(postId);
  }

  listCommentsPage(postId, limit, offset) {
    const comments = this.db
      .prepare(
        'SELECT id, post_id, author_id, body, created_at FROM comments WHERE post_id = ? ORDER BY id LIMIT ? OFFSET ?',
      )
      .all(postId, limit, offset);
    const { total } = this.db
      .prepare('SELECT count(*) AS total FROM comments WHERE post_id = ?')
      .get(postId);
    return [comments, total];
  }

  createComment(postId, authorId, body) {
    const { lastInsertRowid } = this.db
      .prepare('INSERT INTO comments (post_id, author_id, body) VALUES (?, ?, ?)')
      .run(postId, authorId, body);
    return this.db
      .prepare('SELECT id, post_id, author_id, body, created_at FROM comments WHERE id = ?')
      .get(Number(lastInsertRowid));
  }

  listPosts(published, limit, offset) {
    let query = 'SELECT id, author_id, title, body, published, created_at FROM posts';
    let countQuery = 'SELECT count(*) AS total FROM posts';
    const args = [];
    if (published !== null && published !== undefined) {
      query += ' WHERE published = ?';
      countQuery += ' WHERE published = ?';
      args.push(published ? 1 : 0);
    }
    query += ' ORDER BY id LIMIT ? OFFSET ?';

    const rows = this.db.prepare(query).all(...args, limit, offset);
    const { total } = this.db.prepare(countQuery).get(...args);
    return [rows.map((r) => ({ ...r, published: Boolean(r.published) })), total];
  }

  createPost(authorId, title, body, published) {
    const { lastInsertRowid } = this.db
      .prepare('INSERT INTO posts (author_id, title, body, published) VALUES (?, ?, ?, ?)')
      .run(authorId, title, body, published ? 1 : 0);
    return this.getPost(Number(lastInsertRowid));
  }

  updatePost(id, { title, body, published }) {
    const current = this.getPost(id);
    const newTitle = title ?? current.title;
    const newBody = body ?? current.body;
    const newPublished = published ?? current.published;
    this.db
      .prepare('UPDATE posts SET title = ?, body = ?, published = ? WHERE id = ?')
      .run(newTitle, newBody, newPublished ? 1 : 0, id);
    return this.getPost(id);
  }

  deletePost(id) {
    this.db.prepare('DELETE FROM posts WHERE id = ?').run(id);
  }
}

module.exports = { Store, NotFound };
