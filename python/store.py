"""SQLite data access, stdlib sqlite3 — mirrors go/internal/store/store.go's
SQL verbatim. One connection + a lock (matches Go's SetMaxOpenConns(1));
sync functions, called from async handlers via asyncio.to_thread.
"""
import sqlite3
import threading


class NotFound(Exception):
    pass


class Store:
    def __init__(self, db_path: str):
        # PRAGMA foreign_keys=ON is mandatory — SQLite defaults it off, which
        # would silently defeat schema.sql's ON DELETE CASCADE.
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()

    def _row_to_user(self, row) -> dict:
        return {
            "id": row["id"],
            "username": row["username"],
            "email": row["email"],
            "password_hash": row["password_hash"],
            "created_at": row["created_at"],
        }

    def _row_to_post(self, row) -> dict:
        return {
            "id": row["id"],
            "author_id": row["author_id"],
            "title": row["title"],
            "body": row["body"],
            "published": bool(row["published"]),
            "created_at": row["created_at"],
        }

    def _row_to_comment(self, row) -> dict:
        return {
            "id": row["id"],
            "post_id": row["post_id"],
            "author_id": row["author_id"],
            "body": row["body"],
            "created_at": row["created_at"],
        }

    def create_user(self, username: str, email: str, password_hash: str) -> dict:
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, password_hash),
            )
            self.conn.commit()
            return self._get_user_by_id_unlocked(cur.lastrowid)

    def _get_user_by_id_unlocked(self, id: int) -> dict:
        row = self.conn.execute(
            "SELECT id, username, email, password_hash, created_at FROM users WHERE id = ?",
            (id,),
        ).fetchone()
        if row is None:
            raise NotFound()
        return self._row_to_user(row)

    def get_user_by_id(self, id: int) -> dict:
        with self.lock:
            return self._get_user_by_id_unlocked(id)

    def get_user_by_email(self, email: str) -> dict:
        with self.lock:
            row = self.conn.execute(
                "SELECT id, username, email, password_hash, created_at FROM users WHERE email = ?",
                (email,),
            ).fetchone()
            if row is None:
                raise NotFound()
            return self._row_to_user(row)

    def get_post(self, id: int) -> dict:
        with self.lock:
            return self._get_post_unlocked(id)

    def _get_post_unlocked(self, id: int) -> dict:
        row = self.conn.execute(
            "SELECT id, author_id, title, body, published, created_at FROM posts WHERE id = ?",
            (id,),
        ).fetchone()
        if row is None:
            raise NotFound()
        return self._row_to_post(row)

    def list_comments_by_post(self, post_id: int) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id, post_id, author_id, body, created_at FROM comments WHERE post_id = ? ORDER BY id",
                (post_id,),
            ).fetchall()
            return [self._row_to_comment(r) for r in rows]

    def list_comments_page(self, post_id: int, limit: int, offset: int) -> tuple[list[dict], int]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id, post_id, author_id, body, created_at FROM comments "
                "WHERE post_id = ? ORDER BY id LIMIT ? OFFSET ?",
                (post_id, limit, offset),
            ).fetchall()
            total = self.conn.execute(
                "SELECT count(*) FROM comments WHERE post_id = ?", (post_id,)
            ).fetchone()[0]
            return [self._row_to_comment(r) for r in rows], total

    def create_comment(self, post_id: int, author_id: int, body: str) -> dict:
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO comments (post_id, author_id, body) VALUES (?, ?, ?)",
                (post_id, author_id, body),
            )
            self.conn.commit()
            row = self.conn.execute(
                "SELECT id, post_id, author_id, body, created_at FROM comments WHERE id = ?",
                (cur.lastrowid,),
            ).fetchone()
            return self._row_to_comment(row)

    def list_posts(self, published: bool | None, limit: int, offset: int) -> tuple[list[dict], int]:
        with self.lock:
            query = "SELECT id, author_id, title, body, published, created_at FROM posts"
            count_query = "SELECT count(*) FROM posts"
            args: list = []
            if published is not None:
                query += " WHERE published = ?"
                count_query += " WHERE published = ?"
                args.append(1 if published else 0)
            query += " ORDER BY id LIMIT ? OFFSET ?"

            rows = self.conn.execute(query, (*args, limit, offset)).fetchall()
            total = self.conn.execute(count_query, args).fetchone()[0]
            return [self._row_to_post(r) for r in rows], total

    def create_post(self, author_id: int, title: str, body: str, published: bool) -> dict:
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO posts (author_id, title, body, published) VALUES (?, ?, ?, ?)",
                (author_id, title, body, published),
            )
            self.conn.commit()
            return self._get_post_unlocked(cur.lastrowid)

    def update_post(
        self, id: int, title: str | None, body: str | None, published: bool | None
    ) -> dict:
        with self.lock:
            current = self._get_post_unlocked(id)
            new_title = title if title is not None else current["title"]
            new_body = body if body is not None else current["body"]
            new_published = published if published is not None else current["published"]
            self.conn.execute(
                "UPDATE posts SET title = ?, body = ?, published = ? WHERE id = ?",
                (new_title, new_body, new_published, id),
            )
            self.conn.commit()
            return self._get_post_unlocked(id)

    def delete_post(self, id: int) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM posts WHERE id = ?", (id,))
            self.conn.commit()
