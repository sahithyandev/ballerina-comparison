"""Pydantic request/response models matching openapi.yaml, hand-written
(no codegen layer — see RESULTS.md for the contract-direction discussion).
Mirrors go/internal/api/api.gen.go's shapes.
"""
from typing import Optional

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class User(BaseModel):
    id: int
    username: str
    email: str
    created_at: str


class AuthResponse(BaseModel):
    token: str
    user: User


class Post(BaseModel):
    id: int
    author_id: int
    title: str
    body: str
    published: bool
    created_at: str


class CommentWithAuthor(BaseModel):
    id: int
    post_id: int
    author_id: int
    body: str
    created_at: str
    author: User


class PostDetail(Post):
    author: User
    comments: list[CommentWithAuthor]


class CreatePostRequest(BaseModel):
    title: str
    body: str
    published: Optional[bool] = None


class UpdatePostRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    published: Optional[bool] = None


class PostListResponse(BaseModel):
    posts: list[Post]
    page: int
    limit: int
    total: int


class Comment(BaseModel):
    id: int
    post_id: int
    author_id: int
    body: str
    created_at: str


class CreateCommentRequest(BaseModel):
    body: str


class CommentListResponse(BaseModel):
    comments: list[CommentWithAuthor]
    page: int
    limit: int
    total: int


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Optional[str] = None


class Error(BaseModel):
    error: ErrorBody
