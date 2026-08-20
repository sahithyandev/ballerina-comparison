"""FastAPI service, mounted at /api/v1 — mirrors main.go + handlers.go
endpoint-for-endpoint. No generated layer: FastAPI derives its own OpenAPI
doc from these routes/models, the inverse of Go's spec->code oapi-codegen
(see RESULTS.md).
"""
import asyncio
import logging
import sqlite3
import sys

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

import auth
import config
import models
from profanity import Checker
from store import NotFound, Store

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='{"level":"info","msg":%(message)r}')
log = logging.getLogger("app")

cfg = config.load()
store = Store(cfg.db_path)
profanity = Checker(cfg.profanity_url, cfg.profanity_timeout)

app = FastAPI()


def err_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code=status_code, detail=err_body(code, message))


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status_code, content=exc.detail)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Collapse FastAPI/pydantic's default 422 shape into the shared envelope
    # so the error contract matches Go/Ballerina rather than leaking pydantic
    # internals.
    return JSONResponse(
        status_code=400,
        content=err_body("invalid_body", "request body is not valid JSON"),
    )


@app.middleware("http")
async def request_logger(request: Request, call_next):
    log.info('"method":"%s","path":"%s"', request.method, request.url.path)
    return await call_next(request)


async def require_auth(authorization: str | None = Header(default=None)) -> int:
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise ApiError(401, "unauthorized", "missing bearer token")
    try:
        return auth.parse_token(cfg.jwt_secret, authorization[len(prefix):])
    except auth.InvalidToken:
        raise ApiError(401, "unauthorized", "invalid or expired token")


def to_api_user(u: dict) -> dict:
    return {"id": u["id"], "username": u["username"], "email": u["email"], "created_at": u["created_at"]}


def to_api_post(p: dict) -> dict:
    return {
        "id": p["id"], "author_id": p["author_id"], "title": p["title"], "body": p["body"],
        "published": p["published"], "created_at": p["created_at"],
    }


async def attach_authors(comments: list[dict]) -> list[dict]:
    authors = await asyncio.gather(
        *(asyncio.to_thread(store.get_user_by_id, c["author_id"]) for c in comments)
    )
    return [
        {
            "id": c["id"], "post_id": c["post_id"], "author_id": c["author_id"], "body": c["body"],
            "created_at": c["created_at"], "author": to_api_user(a),
        }
        for c, a in zip(comments, authors)
    ]


# --- POST /auth/register ---

@app.post("/api/v1/auth/register", status_code=201)
async def register(req: models.RegisterRequest):
    if len(req.username) < 3 or len(req.password) < 8:
        raise ApiError(400, "validation_failed",
                        "username (>=3 chars), password (>=8 chars) and email are required")

    password_hash = auth.hash_password(req.password)
    try:
        u = await asyncio.to_thread(store.create_user, req.username, req.email, password_hash)
    except sqlite3.IntegrityError:
        raise ApiError(409, "user_exists", "username or email already registered")

    token = auth.issue_token(cfg.jwt_secret, cfg.jwt_expiry, u["id"])
    return {"token": token, "user": to_api_user(u)}


# --- POST /auth/login ---

@app.post("/api/v1/auth/login")
async def login(req: models.LoginRequest):
    try:
        u = await asyncio.to_thread(store.get_user_by_email, req.email)
    except NotFound:
        raise ApiError(401, "invalid_credentials", "email or password is incorrect")

    if not auth.check_password(u["password_hash"], req.password):
        raise ApiError(401, "invalid_credentials", "email or password is incorrect")

    token = auth.issue_token(cfg.jwt_secret, cfg.jwt_expiry, u["id"])
    return {"token": token, "user": to_api_user(u)}


# --- GET /posts ---

@app.get("/api/v1/posts")
async def list_posts(page: int = 1, limit: int = 20, published: bool | None = None):
    if page < 1 or limit < 1 or limit > 100:
        raise ApiError(400, "validation_failed", "page must be >=1, limit must be 1-100")

    posts, total = await asyncio.to_thread(store.list_posts, published, limit, (page - 1) * limit)
    return {"posts": [to_api_post(p) for p in posts], "page": page, "limit": limit, "total": total}


# --- POST /posts ---

@app.post("/api/v1/posts", status_code=201)
async def create_post(req: models.CreatePostRequest, uid: int = Depends(require_auth)):
    if not req.title.strip() or not req.body.strip():
        raise ApiError(400, "validation_failed", "title and body are required")
    if not await profanity.is_clean(f"{req.title} {req.body}"):
        raise ApiError(400, "validation_failed", "content contains profanity")

    p = await asyncio.to_thread(store.create_post, uid, req.title, req.body, bool(req.published))
    return to_api_post(p)


# --- PUT /posts/{id} ---

@app.put("/api/v1/posts/{id}")
async def update_post(id: int, req: models.UpdatePostRequest, uid: int = Depends(require_auth)):
    try:
        post = await asyncio.to_thread(store.get_post, id)
    except NotFound:
        raise ApiError(404, "not_found", "post not found")
    if post["author_id"] != uid:
        raise ApiError(403, "forbidden", "only the author can modify this post")

    if req.title is not None and not req.title.strip():
        raise ApiError(400, "validation_failed", "title cannot be empty")
    if req.body is not None and not req.body.strip():
        raise ApiError(400, "validation_failed", "body cannot be empty")

    check_title = req.title if req.title is not None else post["title"]
    check_body = req.body if req.body is not None else post["body"]
    if not await profanity.is_clean(f"{check_title} {check_body}"):
        raise ApiError(400, "validation_failed", "content contains profanity")

    updated = await asyncio.to_thread(store.update_post, id, req.title, req.body, req.published)
    return to_api_post(updated)


# --- DELETE /posts/{id} ---

@app.delete("/api/v1/posts/{id}", status_code=204)
async def delete_post(id: int, uid: int = Depends(require_auth)):
    try:
        post = await asyncio.to_thread(store.get_post, id)
    except NotFound:
        raise ApiError(404, "not_found", "post not found")
    if post["author_id"] != uid:
        raise ApiError(403, "forbidden", "only the author can delete this post")

    await asyncio.to_thread(store.delete_post, id)


# --- GET /posts/{id}/comments ---

@app.get("/api/v1/posts/{id}/comments")
async def list_comments(id: int, page: int = 1, limit: int = 20):
    try:
        await asyncio.to_thread(store.get_post, id)
    except NotFound:
        raise ApiError(404, "not_found", "post not found")

    if page < 1 or limit < 1 or limit > 100:
        raise ApiError(400, "validation_failed", "page must be >=1, limit must be 1-100")

    comments, total = await asyncio.to_thread(store.list_comments_page, id, limit, (page - 1) * limit)
    with_authors = await attach_authors(comments)
    return {"comments": with_authors, "page": page, "limit": limit, "total": total}


# --- POST /posts/{id}/comments ---

@app.post("/api/v1/posts/{id}/comments", status_code=201)
async def create_comment(id: int, req: models.CreateCommentRequest, uid: int = Depends(require_auth)):
    try:
        await asyncio.to_thread(store.get_post, id)
    except NotFound:
        raise ApiError(404, "not_found", "post not found")

    if not req.body.strip():
        raise ApiError(400, "validation_failed", "body is required")
    if not await profanity.is_clean(req.body):
        raise ApiError(400, "validation_failed", "content contains profanity")

    c = await asyncio.to_thread(store.create_comment, id, uid, req.body)
    return {
        "id": c["id"], "post_id": c["post_id"], "author_id": c["author_id"],
        "body": c["body"], "created_at": c["created_at"],
    }


# --- GET /posts/{id} ---
#
# Fan-out join point (plan.md criterion #7): fetches the post's author and
# its comments concurrently via asyncio.gather, then each comment's author
# concurrently too — the goroutines/workers-vs-asyncio comparison point.

@app.get("/api/v1/posts/{id}")
async def get_post(id: int):
    try:
        post = await asyncio.to_thread(store.get_post, id)
    except NotFound:
        raise ApiError(404, "not_found", "post not found")

    author, comments = await asyncio.gather(
        asyncio.to_thread(store.get_user_by_id, post["author_id"]),
        asyncio.to_thread(store.list_comments_by_post, post["id"]),
    )

    api_comments = await attach_authors(comments)

    return {
        **to_api_post(post),
        "author": to_api_user(author),
        "comments": api_comments,
    }


if __name__ == "__main__":
    import uvicorn

    log.info('"msg":"listening","port":"%s"', cfg.port)
    uvicorn.run(app, host="0.0.0.0", port=int(cfg.port))
