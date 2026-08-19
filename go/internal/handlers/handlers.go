// Package handlers implements api.ServerInterface. Server embeds
// api.Unimplemented so endpoints not yet built (step 4 of plan.md) return
// 501 instead of failing to compile.
package handlers

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	"golang.org/x/sync/errgroup"

	"blog-go/internal/api"
	"blog-go/internal/auth"
	"blog-go/internal/config"
	"blog-go/internal/httpx"
	"blog-go/internal/store"
)

type Server struct {
	api.Unimplemented
	Store *store.Store
	Cfg   config.Config
}

func New(s *store.Store, cfg config.Config) *Server {
	return &Server{Store: s, Cfg: cfg}
}

func toAPIUser(u store.User) api.User {
	return api.User{Id: u.ID, Username: u.Username, Email: u.Email, CreatedAt: u.CreatedAt}
}

func toAPIPost(p store.Post) api.Post {
	return api.Post{
		Id: p.ID, AuthorId: p.AuthorID, Title: p.Title, Body: p.Body,
		Published: p.Published, CreatedAt: p.CreatedAt,
	}
}

// --- POST /auth/register ---

func (s *Server) Register(w http.ResponseWriter, r *http.Request) {
	var req api.RegisterRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		httpx.Err(w, http.StatusBadRequest, "invalid_body", "request body is not valid JSON")
		return
	}
	if len(req.Username) < 3 || len(req.Password) < 8 || req.Email == "" {
		httpx.Err(w, http.StatusBadRequest, "validation_failed", "username (>=3 chars), password (>=8 chars) and email are required")
		return
	}

	hash, err := auth.HashPassword(req.Password)
	if err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not hash password")
		return
	}

	u, err := s.Store.CreateUser(r.Context(), req.Username, string(req.Email), hash)
	if err != nil {
		httpx.Err(w, http.StatusConflict, "user_exists", "username or email already registered")
		return
	}

	token, err := auth.IssueToken(s.Cfg.JWTSecret, s.Cfg.JWTExpiry, u.ID)
	if err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not issue token")
		return
	}

	httpx.JSON(w, http.StatusCreated, api.AuthResponse{Token: token, User: toAPIUser(u)})
}

// --- POST /auth/login ---

func (s *Server) Login(w http.ResponseWriter, r *http.Request) {
	var req api.LoginRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		httpx.Err(w, http.StatusBadRequest, "invalid_body", "request body is not valid JSON")
		return
	}

	u, err := s.Store.GetUserByEmail(r.Context(), string(req.Email))
	if errors.Is(err, store.ErrNotFound) || !auth.CheckPassword(u.PasswordHash, req.Password) {
		httpx.Err(w, http.StatusUnauthorized, "invalid_credentials", "email or password is incorrect")
		return
	}
	if err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not look up user")
		return
	}

	token, err := auth.IssueToken(s.Cfg.JWTSecret, s.Cfg.JWTExpiry, u.ID)
	if err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not issue token")
		return
	}

	httpx.JSON(w, http.StatusOK, api.AuthResponse{Token: token, User: toAPIUser(u)})
}

// --- GET /posts/{id} ---
//
// Fan-out join point (plan.md criterion #7): fetches the post's author and
// its comments concurrently, then fetches each comment's author concurrently
// too, via errgroup — the goroutines-vs-Ballerina-workers comparison point.

func (s *Server) GetPost(w http.ResponseWriter, r *http.Request, id api.PostId) {
	ctx := r.Context()

	post, err := s.Store.GetPost(ctx, id)
	if errors.Is(err, store.ErrNotFound) {
		httpx.Err(w, http.StatusNotFound, "not_found", "post not found")
		return
	}
	if err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not load post")
		return
	}

	var author store.User
	var comments []store.Comment

	g, gctx := errgroup.WithContext(ctx)
	g.Go(func() error {
		var err error
		author, err = s.Store.GetUserByID(gctx, post.AuthorID)
		return err
	})
	g.Go(func() error {
		var err error
		comments, err = s.Store.ListCommentsByPost(gctx, post.ID)
		return err
	})
	if err := g.Wait(); err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not load post detail")
		return
	}

	commentAuthors := make([]store.User, len(comments))
	g2, gctx2 := errgroup.WithContext(ctx)
	for i, c := range comments {
		i, c := i, c
		g2.Go(func() error {
			u, err := s.Store.GetUserByID(gctx2, c.AuthorID)
			commentAuthors[i] = u
			return err
		})
	}
	if err := g2.Wait(); err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not load comment authors")
		return
	}

	apiComments := make([]api.CommentWithAuthor, len(comments))
	for i, c := range comments {
		apiComments[i] = api.CommentWithAuthor{
			Id: c.ID, PostId: c.PostID, AuthorId: c.AuthorID, Body: c.Body,
			CreatedAt: c.CreatedAt, Author: toAPIUser(commentAuthors[i]),
		}
	}

	httpx.JSON(w, http.StatusOK, api.PostDetail{
		Id: post.ID, AuthorId: post.AuthorID, Title: post.Title, Body: post.Body,
		Published: post.Published, CreatedAt: post.CreatedAt,
		Author: toAPIUser(author), Comments: apiComments,
	})
}

// AuthMiddleware validates the bearer token and stashes the user id in the
// request context under ctxKeyUserID. Wired up in step 4 once write
// endpoints need it; GetPost/Login/Register don't require auth.
type ctxKey int

const ctxKeyUserID ctxKey = iota

func UserIDFromContext(ctx context.Context) (int64, bool) {
	id, ok := ctx.Value(ctxKeyUserID).(int64)
	return id, ok
}

func AuthMiddleware(secret string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			h := r.Header.Get("Authorization")
			const prefix = "Bearer "
			if len(h) <= len(prefix) || h[:len(prefix)] != prefix {
				httpx.Err(w, http.StatusUnauthorized, "unauthorized", "missing bearer token")
				return
			}
			uid, err := auth.ParseToken(secret, h[len(prefix):])
			if err != nil {
				httpx.Err(w, http.StatusUnauthorized, "unauthorized", "invalid or expired token")
				return
			}
			ctx := context.WithValue(r.Context(), ctxKeyUserID, uid)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}
