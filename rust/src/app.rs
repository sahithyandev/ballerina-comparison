// Builds the axum Router + all endpoint handlers. Mirrors handlers.go
// 1:1 in behavior (status codes, error codes/messages, validation rules).
use axum::extract::{Path, Query, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::sync::Arc;

use crate::auth;
use crate::config::Config;
use crate::httpx::{self, AppError};
use crate::profanity::Checker;
use crate::store::{self, Db, PostUpdate, StoreError};

#[derive(Clone)]
pub struct AppState {
    pub db: Db,
    pub cfg: Config,
    pub profanity: Checker,
}

pub fn build_router(state: AppState) -> Router {
    Router::new()
        .route("/auth/register", post(register))
        .route("/auth/login", post(login))
        .route("/posts", get(list_posts).post(create_post))
        .route("/posts/{id}", get(get_post).put(update_post).delete(delete_post))
        .route(
            "/posts/{id}/comments",
            get(list_comments).post(create_comment),
        )
        .with_state(Arc::new(state))
}

async fn call_db<F, T>(db: &Db, f: F) -> Result<T, StoreError>
where
    F: FnOnce(&rusqlite::Connection) -> Result<T, StoreError> + Send + 'static,
    T: Send + 'static,
{
    let db = db.clone();
    tokio::task::spawn_blocking(move || {
        let conn = db.lock().unwrap();
        f(&conn)
    })
    .await
    .map_err(|e| StoreError::Other(e.to_string()))?
}

fn internal_error(_e: StoreError) -> AppError {
    httpx::internal("internal_error", "internal error")
}

fn require_auth(headers: &HeaderMap, cfg: &Config) -> Result<i64, AppError> {
    let h = headers
        .get("Authorization")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    let Some(token) = h.strip_prefix("Bearer ") else {
        return Err(httpx::unauthorized("unauthorized", "missing bearer token"));
    };
    auth::parse_token(&cfg.jwt_secret, token)
        .map_err(|_| httpx::unauthorized("unauthorized", "invalid or expired token"))
}

// ---- wire types ----

#[derive(Serialize)]
struct UserOut {
    id: i64,
    username: String,
    email: String,
    created_at: String,
}

impl From<store::User> for UserOut {
    fn from(u: store::User) -> Self {
        UserOut { id: u.id, username: u.username, email: u.email, created_at: u.created_at }
    }
}

#[derive(Serialize)]
struct PostOut {
    id: i64,
    author_id: i64,
    title: String,
    body: String,
    published: bool,
    created_at: String,
}

impl From<store::Post> for PostOut {
    fn from(p: store::Post) -> Self {
        PostOut {
            id: p.id,
            author_id: p.author_id,
            title: p.title,
            body: p.body,
            published: p.published,
            created_at: p.created_at,
        }
    }
}

#[derive(Serialize)]
struct CommentOut {
    id: i64,
    post_id: i64,
    author_id: i64,
    body: String,
    created_at: String,
}

impl From<store::Comment> for CommentOut {
    fn from(c: store::Comment) -> Self {
        CommentOut { id: c.id, post_id: c.post_id, author_id: c.author_id, body: c.body, created_at: c.created_at }
    }
}

#[derive(Serialize)]
struct CommentWithAuthorOut {
    #[serde(flatten)]
    comment: CommentOut,
    author: UserOut,
}

#[derive(Serialize)]
struct AuthResponse {
    token: String,
    user: UserOut,
}

#[derive(Deserialize)]
struct RegisterRequest {
    username: String,
    email: String,
    password: String,
}

#[derive(Deserialize)]
struct LoginRequest {
    email: String,
    password: String,
}

#[derive(Deserialize)]
struct CreatePostRequest {
    title: String,
    body: String,
    published: Option<bool>,
}

#[derive(Deserialize, Default)]
struct UpdatePostRequest {
    title: Option<String>,
    body: Option<String>,
    published: Option<bool>,
}

#[derive(Deserialize)]
struct CreateCommentRequest {
    body: String,
}

#[derive(Deserialize)]
struct PageParams {
    page: Option<i64>,
    limit: Option<i64>,
}

#[derive(Deserialize)]
struct ListPostsParams {
    page: Option<i64>,
    limit: Option<i64>,
    published: Option<bool>,
}

fn json_response(status: StatusCode, body: impl Serialize) -> Response {
    (status, Json(body)).into_response()
}

// ---- POST /auth/register ----

async fn register(
    State(state): State<Arc<AppState>>,
    body: Result<Json<RegisterRequest>, axum::extract::rejection::JsonRejection>,
) -> Result<Response, AppError> {
    let Json(req) = body.map_err(|_| httpx::bad_request("invalid_body", "request body is not valid JSON"))?;

    if req.username.len() < 3 || req.password.len() < 8 || req.email.is_empty() {
        return Err(httpx::bad_request(
            "validation_failed",
            "username (>=3 chars), password (>=8 chars) and email are required",
        ));
    }

    let hash = auth::hash_password(&req.password)
        .map_err(|_| httpx::internal("internal_error", "could not hash password"))?;

    let db = state.db.clone();
    let username = req.username.clone();
    let email = req.email.clone();
    let user = call_db(&db, move |conn| store::create_user(conn, &username, &email, &hash))
        .await
        .map_err(|_| httpx::conflict("user_exists", "username or email already registered"))?;

    let token = auth::issue_token(&state.cfg.jwt_secret, state.cfg.jwt_expiry, user.id)
        .map_err(|_| httpx::internal("internal_error", "could not issue token"))?;

    Ok(json_response(
        StatusCode::CREATED,
        AuthResponse { token, user: user.into() },
    ))
}

// ---- POST /auth/login ----

async fn login(
    State(state): State<Arc<AppState>>,
    body: Result<Json<LoginRequest>, axum::extract::rejection::JsonRejection>,
) -> Result<Response, AppError> {
    let Json(req) = body.map_err(|_| httpx::bad_request("invalid_body", "request body is not valid JSON"))?;

    let email = req.email.clone();
    let user = call_db(&state.db, move |conn| store::get_user_by_email(conn, &email)).await;

    let user = match user {
        Ok(u) if auth::check_password(&u.password_hash, &req.password) => u,
        Ok(_) => {
            return Err(httpx::unauthorized("invalid_credentials", "email or password is incorrect"))
        }
        Err(StoreError::NotFound) => {
            return Err(httpx::unauthorized("invalid_credentials", "email or password is incorrect"))
        }
        Err(e) => return Err(internal_error(e)),
    };

    let token = auth::issue_token(&state.cfg.jwt_secret, state.cfg.jwt_expiry, user.id)
        .map_err(|_| httpx::internal("internal_error", "could not issue token"))?;

    Ok(json_response(StatusCode::OK, AuthResponse { token, user: user.into() }))
}

// ---- GET /posts ----

async fn list_posts(
    State(state): State<Arc<AppState>>,
    Query(params): Query<ListPostsParams>,
) -> Result<Response, AppError> {
    let page = params.page.unwrap_or(1);
    let limit = params.limit.unwrap_or(20);
    if page < 1 || limit < 1 || limit > 100 {
        return Err(httpx::bad_request(
            "validation_failed",
            "page must be >=1, limit must be 1-100",
        ));
    }

    let published = params.published;
    let (posts, total) = call_db(&state.db, move |conn| {
        store::list_posts(conn, published, limit, (page - 1) * limit)
    })
    .await
    .map_err(internal_error)?;

    Ok(json_response(
        StatusCode::OK,
        json!({
            "posts": posts.into_iter().map(PostOut::from).collect::<Vec<_>>(),
            "page": page,
            "limit": limit,
            "total": total,
        }),
    ))
}

// ---- POST /posts ----

async fn create_post(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    body: Result<Json<CreatePostRequest>, axum::extract::rejection::JsonRejection>,
) -> Result<Response, AppError> {
    let uid = require_auth(&headers, &state.cfg)?;
    let Json(req) = body.map_err(|_| httpx::bad_request("invalid_body", "request body is not valid JSON"))?;

    if req.title.trim().is_empty() || req.body.trim().is_empty() {
        return Err(httpx::bad_request("validation_failed", "title and body are required"));
    }
    if !state.profanity.is_clean(&format!("{} {}", req.title, req.body)).await {
        return Err(httpx::bad_request("validation_failed", "content contains profanity"));
    }

    let published = req.published.unwrap_or(false);
    let title = req.title.clone();
    let post_body = req.body.clone();
    let post = call_db(&state.db, move |conn| {
        store::create_post(conn, uid, &title, &post_body, published)
    })
    .await
    .map_err(internal_error)?;

    Ok(json_response(StatusCode::CREATED, PostOut::from(post)))
}

// ---- PUT /posts/{id} ----

async fn update_post(
    State(state): State<Arc<AppState>>,
    Path(id): Path<i64>,
    headers: HeaderMap,
    body: Result<Json<UpdatePostRequest>, axum::extract::rejection::JsonRejection>,
) -> Result<Response, AppError> {
    let uid = require_auth(&headers, &state.cfg)?;

    let post = call_db(&state.db, move |conn| store::get_post(conn, id))
        .await
        .map_err(|e| match e {
            StoreError::NotFound => httpx::not_found("not_found", "post not found"),
            e => internal_error(e),
        })?;
    if post.author_id != uid {
        return Err(httpx::forbidden("forbidden", "only the author can modify this post"));
    }

    let Json(req) = body.map_err(|_| httpx::bad_request("invalid_body", "request body is not valid JSON"))?;
    if let Some(t) = &req.title {
        if t.trim().is_empty() {
            return Err(httpx::bad_request("validation_failed", "title cannot be empty"));
        }
    }
    if let Some(b) = &req.body {
        if b.trim().is_empty() {
            return Err(httpx::bad_request("validation_failed", "body cannot be empty"));
        }
    }

    let check_title = req.title.clone().unwrap_or_else(|| post.title.clone());
    let check_body = req.body.clone().unwrap_or_else(|| post.body.clone());
    if !state.profanity.is_clean(&format!("{} {}", check_title, check_body)).await {
        return Err(httpx::bad_request("validation_failed", "content contains profanity"));
    }

    let update = PostUpdate { title: req.title, body: req.body, published: req.published };
    let updated = call_db(&state.db, move |conn| store::update_post(conn, id, update))
        .await
        .map_err(internal_error)?;

    Ok(json_response(StatusCode::OK, PostOut::from(updated)))
}

// ---- DELETE /posts/{id} ----

async fn delete_post(
    State(state): State<Arc<AppState>>,
    Path(id): Path<i64>,
    headers: HeaderMap,
) -> Result<Response, AppError> {
    let uid = require_auth(&headers, &state.cfg)?;

    let post = call_db(&state.db, move |conn| store::get_post(conn, id))
        .await
        .map_err(|e| match e {
            StoreError::NotFound => httpx::not_found("not_found", "post not found"),
            e => internal_error(e),
        })?;
    if post.author_id != uid {
        return Err(httpx::forbidden("forbidden", "only the author can delete this post"));
    }

    call_db(&state.db, move |conn| store::delete_post(conn, id))
        .await
        .map_err(internal_error)?;

    Ok(StatusCode::NO_CONTENT.into_response())
}

// ---- GET /posts/{id}/comments ----

async fn list_comments(
    State(state): State<Arc<AppState>>,
    Path(id): Path<i64>,
    Query(params): Query<PageParams>,
) -> Result<Response, AppError> {
    call_db(&state.db, move |conn| store::get_post(conn, id))
        .await
        .map_err(|e| match e {
            StoreError::NotFound => httpx::not_found("not_found", "post not found"),
            e => internal_error(e),
        })?;

    let page = params.page.unwrap_or(1);
    let limit = params.limit.unwrap_or(20);
    if page < 1 || limit < 1 || limit > 100 {
        return Err(httpx::bad_request(
            "validation_failed",
            "page must be >=1, limit must be 1-100",
        ));
    }

    let (comments, total) = call_db(&state.db, move |conn| {
        store::list_comments_page(conn, id, limit, (page - 1) * limit)
    })
    .await
    .map_err(internal_error)?;

    let with_authors = attach_authors(&state.db, comments).await.map_err(internal_error)?;

    Ok(json_response(
        StatusCode::OK,
        json!({ "comments": with_authors, "page": page, "limit": limit, "total": total }),
    ))
}

// ---- POST /posts/{id}/comments ----

async fn create_comment(
    State(state): State<Arc<AppState>>,
    Path(id): Path<i64>,
    headers: HeaderMap,
    body: Result<Json<CreateCommentRequest>, axum::extract::rejection::JsonRejection>,
) -> Result<Response, AppError> {
    let uid = require_auth(&headers, &state.cfg)?;

    call_db(&state.db, move |conn| store::get_post(conn, id))
        .await
        .map_err(|e| match e {
            StoreError::NotFound => httpx::not_found("not_found", "post not found"),
            e => internal_error(e),
        })?;

    let Json(req) = body.map_err(|_| httpx::bad_request("invalid_body", "request body is not valid JSON"))?;
    if req.body.trim().is_empty() {
        return Err(httpx::bad_request("validation_failed", "body is required"));
    }
    if !state.profanity.is_clean(&req.body).await {
        return Err(httpx::bad_request("validation_failed", "content contains profanity"));
    }

    let comment_body = req.body.clone();
    let comment = call_db(&state.db, move |conn| {
        store::create_comment(conn, id, uid, &comment_body)
    })
    .await
    .map_err(internal_error)?;

    Ok(json_response(StatusCode::CREATED, CommentOut::from(comment)))
}

// ---- GET /posts/{id} ----
//
// Fan-out join point (plan.md criterion #7): fetches the post's author and
// its comments concurrently via tokio::join! over spawn_blocking tasks —
// real OS threads (tokio's blocking pool), unlike Node/Bun's single JS
// thread, but both tasks still serialize behind the single-connection
// mutex in `store::Db`, so the DB access itself is not actually parallel —
// see RESULTS.md.

async fn get_post(
    State(state): State<Arc<AppState>>,
    Path(id): Path<i64>,
) -> Result<Response, AppError> {
    let post = call_db(&state.db, move |conn| store::get_post(conn, id))
        .await
        .map_err(|e| match e {
            StoreError::NotFound => httpx::not_found("not_found", "post not found"),
            e => internal_error(e),
        })?;

    let author_id = post.author_id;
    let post_id = post.id;
    let db1 = state.db.clone();
    let db2 = state.db.clone();
    let (author, comments) = tokio::join!(
        call_db(&db1, move |conn| store::get_user_by_id(conn, author_id)),
        call_db(&db2, move |conn| store::list_comments_by_post(conn, post_id)),
    );
    let author = author.map_err(internal_error)?;
    let comments = comments.map_err(internal_error)?;

    let with_authors = attach_authors(&state.db, comments).await.map_err(internal_error)?;

    Ok(json_response(
        StatusCode::OK,
        json!({
            "id": post.id,
            "author_id": post.author_id,
            "title": post.title,
            "body": post.body,
            "published": post.published,
            "created_at": post.created_at,
            "author": UserOut::from(author),
            "comments": with_authors,
        }),
    ))
}

// Fetches each comment's author concurrently, same real-threads-behind-a-
// mutex story as get_post above.
async fn attach_authors(
    db: &Db,
    comments: Vec<store::Comment>,
) -> Result<Vec<CommentWithAuthorOut>, StoreError> {
    let futures = comments.into_iter().map(|c| {
        let db = db.clone();
        async move {
            let author = call_db(&db, move |conn| store::get_user_by_id(conn, c.author_id)).await?;
            Ok::<_, StoreError>(CommentWithAuthorOut { comment: CommentOut::from(c), author: author.into() })
        }
    });
    let results: Vec<Result<CommentWithAuthorOut, StoreError>> = futures::future::join_all(futures).await;
    results.into_iter().collect()
}
