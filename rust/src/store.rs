// SQLite data-access layer over rusqlite. Kept as plain SQL, no ORM — the
// domain is three tables, same as store.go/store.py/store.js/store.ts.
use rusqlite::{params, Connection, OptionalExtension};
use serde::Serialize;
use std::sync::{Arc, Mutex};

pub type Db = Arc<Mutex<Connection>>;

#[derive(Debug)]
pub enum StoreError {
    NotFound,
    Other(String),
}

impl From<rusqlite::Error> for StoreError {
    fn from(e: rusqlite::Error) -> Self {
        StoreError::Other(e.to_string())
    }
}

#[derive(Clone, Serialize)]
pub struct User {
    pub id: i64,
    pub username: String,
    pub email: String,
    #[serde(skip)]
    pub password_hash: String,
    pub created_at: String,
}

#[derive(Clone, Serialize)]
pub struct Post {
    pub id: i64,
    pub author_id: i64,
    pub title: String,
    pub body: String,
    pub published: bool,
    pub created_at: String,
}

#[derive(Clone, Serialize)]
pub struct Comment {
    pub id: i64,
    pub post_id: i64,
    pub author_id: i64,
    pub body: String,
    pub created_at: String,
}

#[derive(Default)]
pub struct PostUpdate {
    pub title: Option<String>,
    pub body: Option<String>,
    pub published: Option<bool>,
}

fn row_to_user(row: &rusqlite::Row) -> rusqlite::Result<User> {
    Ok(User {
        id: row.get(0)?,
        username: row.get(1)?,
        email: row.get(2)?,
        password_hash: row.get(3)?,
        created_at: row.get(4)?,
    })
}

fn row_to_post(row: &rusqlite::Row) -> rusqlite::Result<Post> {
    let published: i64 = row.get(4)?;
    Ok(Post {
        id: row.get(0)?,
        author_id: row.get(1)?,
        title: row.get(2)?,
        body: row.get(3)?,
        published: published != 0,
        created_at: row.get(5)?,
    })
}

fn row_to_comment(row: &rusqlite::Row) -> rusqlite::Result<Comment> {
    Ok(Comment {
        id: row.get(0)?,
        post_id: row.get(1)?,
        author_id: row.get(2)?,
        body: row.get(3)?,
        created_at: row.get(4)?,
    })
}

pub fn create_user(
    conn: &Connection,
    username: &str,
    email: &str,
    password_hash: &str,
) -> Result<User, StoreError> {
    conn.execute(
        "INSERT INTO users (username, email, password_hash) VALUES (?1, ?2, ?3)",
        params![username, email, password_hash],
    )?;
    get_user_by_id(conn, conn.last_insert_rowid())
}

pub fn get_user_by_id(conn: &Connection, id: i64) -> Result<User, StoreError> {
    conn.query_row(
        "SELECT id, username, email, password_hash, created_at FROM users WHERE id = ?1",
        params![id],
        row_to_user,
    )
    .optional()?
    .ok_or(StoreError::NotFound)
}

pub fn get_user_by_email(conn: &Connection, email: &str) -> Result<User, StoreError> {
    conn.query_row(
        "SELECT id, username, email, password_hash, created_at FROM users WHERE email = ?1",
        params![email],
        row_to_user,
    )
    .optional()?
    .ok_or(StoreError::NotFound)
}

pub fn get_post(conn: &Connection, id: i64) -> Result<Post, StoreError> {
    conn.query_row(
        "SELECT id, author_id, title, body, published, created_at FROM posts WHERE id = ?1",
        params![id],
        row_to_post,
    )
    .optional()?
    .ok_or(StoreError::NotFound)
}

pub fn list_comments_by_post(conn: &Connection, post_id: i64) -> Result<Vec<Comment>, StoreError> {
    let mut stmt = conn.prepare(
        "SELECT id, post_id, author_id, body, created_at FROM comments WHERE post_id = ?1 ORDER BY id",
    )?;
    let rows = stmt.query_map(params![post_id], row_to_comment)?;
    Ok(rows.collect::<Result<Vec<_>, _>>()?)
}

pub fn list_comments_page(
    conn: &Connection,
    post_id: i64,
    limit: i64,
    offset: i64,
) -> Result<(Vec<Comment>, i64), StoreError> {
    let mut stmt = conn.prepare(
        "SELECT id, post_id, author_id, body, created_at FROM comments WHERE post_id = ?1 ORDER BY id LIMIT ?2 OFFSET ?3",
    )?;
    let rows = stmt.query_map(params![post_id, limit, offset], row_to_comment)?;
    let comments = rows.collect::<Result<Vec<_>, _>>()?;
    let total: i64 = conn.query_row(
        "SELECT count(*) FROM comments WHERE post_id = ?1",
        params![post_id],
        |r| r.get(0),
    )?;
    Ok((comments, total))
}

pub fn create_comment(
    conn: &Connection,
    post_id: i64,
    author_id: i64,
    body: &str,
) -> Result<Comment, StoreError> {
    conn.execute(
        "INSERT INTO comments (post_id, author_id, body) VALUES (?1, ?2, ?3)",
        params![post_id, author_id, body],
    )?;
    let id = conn.last_insert_rowid();
    conn.query_row(
        "SELECT id, post_id, author_id, body, created_at FROM comments WHERE id = ?1",
        params![id],
        row_to_comment,
    )
    .map_err(StoreError::from)
}

pub fn list_posts(
    conn: &Connection,
    published: Option<bool>,
    limit: i64,
    offset: i64,
) -> Result<(Vec<Post>, i64), StoreError> {
    let (posts, total) = match published {
        Some(p) => {
            let v = if p { 1 } else { 0 };
            let mut stmt = conn.prepare(
                "SELECT id, author_id, title, body, published, created_at FROM posts WHERE published = ?1 ORDER BY id LIMIT ?2 OFFSET ?3",
            )?;
            let rows = stmt.query_map(params![v, limit, offset], row_to_post)?;
            let posts = rows.collect::<Result<Vec<_>, _>>()?;
            let total: i64 = conn.query_row(
                "SELECT count(*) FROM posts WHERE published = ?1",
                params![v],
                |r| r.get(0),
            )?;
            (posts, total)
        }
        None => {
            let mut stmt = conn.prepare(
                "SELECT id, author_id, title, body, published, created_at FROM posts ORDER BY id LIMIT ?1 OFFSET ?2",
            )?;
            let rows = stmt.query_map(params![limit, offset], row_to_post)?;
            let posts = rows.collect::<Result<Vec<_>, _>>()?;
            let total: i64 =
                conn.query_row("SELECT count(*) FROM posts", [], |r| r.get(0))?;
            (posts, total)
        }
    };
    Ok((posts, total))
}

pub fn create_post(
    conn: &Connection,
    author_id: i64,
    title: &str,
    body: &str,
    published: bool,
) -> Result<Post, StoreError> {
    conn.execute(
        "INSERT INTO posts (author_id, title, body, published) VALUES (?1, ?2, ?3, ?4)",
        params![author_id, title, body, published as i64],
    )?;
    get_post(conn, conn.last_insert_rowid())
}

pub fn update_post(conn: &Connection, id: i64, u: PostUpdate) -> Result<Post, StoreError> {
    let current = get_post(conn, id)?;
    let title = u.title.unwrap_or(current.title);
    let body = u.body.unwrap_or(current.body);
    let published = u.published.unwrap_or(current.published);
    conn.execute(
        "UPDATE posts SET title = ?1, body = ?2, published = ?3 WHERE id = ?4",
        params![title, body, published as i64, id],
    )?;
    get_post(conn, id)
}

pub fn delete_post(conn: &Connection, id: i64) -> Result<(), StoreError> {
    conn.execute("DELETE FROM posts WHERE id = ?1", params![id])?;
    Ok(())
}
