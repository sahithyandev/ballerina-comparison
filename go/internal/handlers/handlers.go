// Package handlers implements api.ServerInterface.
package handlers

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"golang.org/x/sync/errgroup"

	"blog-go/internal/api"
	"blog-go/internal/auth"
	"blog-go/internal/config"
	"blog-go/internal/httpx"
	"blog-go/internal/profanity"
	"blog-go/internal/store"
)

type Server struct {
	api.Unimplemented
	Store     *store.Store
	Cfg       config.Config
	Profanity *profanity.Checker
}

func New(s *store.Store, cfg config.Config) *Server {
	return &Server{Store: s, Cfg: cfg, Profanity: profanity.New(cfg.ProfanityURL, cfg.ProfanityTimeout)}
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

func toAPIComment(c store.Comment) api.Comment {
	return api.Comment{Id: c.ID, PostId: c.PostID, AuthorId: c.AuthorID, Body: c.Body, CreatedAt: c.CreatedAt}
}

// requireAuth reads and validates the bearer token directly, rather than a
// blanket middleware, since only some routes need it.
func (s *Server) requireAuth(w http.ResponseWriter, r *http.Request) (int64, bool) {
	h := r.Header.Get("Authorization")
	const prefix = "Bearer "
	if !strings.HasPrefix(h, prefix) {
		httpx.Err(w, http.StatusUnauthorized, "unauthorized", "missing bearer token")
		return 0, false
	}
	uid, err := auth.ParseToken(s.Cfg.JWTSecret, strings.TrimPrefix(h, prefix))
	if err != nil {
		httpx.Err(w, http.StatusUnauthorized, "unauthorized", "invalid or expired token")
		return 0, false
	}
	return uid, true
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

// --- GET /posts ---

func (s *Server) ListPosts(w http.ResponseWriter, r *http.Request, params api.ListPostsParams) {
	page, limit := 1, 20
	if params.Page != nil {
		page = *params.Page
	}
	if params.Limit != nil {
		limit = *params.Limit
	}
	if page < 1 || limit < 1 || limit > 100 {
		httpx.Err(w, http.StatusBadRequest, "validation_failed", "page must be >=1, limit must be 1-100")
		return
	}

	posts, total, err := s.Store.ListPosts(r.Context(), params.Published, limit, (page-1)*limit)
	if err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not list posts")
		return
	}
	apiPosts := make([]api.Post, len(posts))
	for i, p := range posts {
		apiPosts[i] = toAPIPost(p)
	}
	httpx.JSON(w, http.StatusOK, api.PostListResponse{Posts: apiPosts, Page: page, Limit: limit, Total: total})
}

// --- POST /posts ---

func (s *Server) CreatePost(w http.ResponseWriter, r *http.Request) {
	uid, ok := s.requireAuth(w, r)
	if !ok {
		return
	}

	var req api.CreatePostRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		httpx.Err(w, http.StatusBadRequest, "invalid_body", "request body is not valid JSON")
		return
	}
	if strings.TrimSpace(req.Title) == "" || strings.TrimSpace(req.Body) == "" {
		httpx.Err(w, http.StatusBadRequest, "validation_failed", "title and body are required")
		return
	}
	if !s.Profanity.IsClean(r.Context(), req.Title+" "+req.Body) {
		httpx.Err(w, http.StatusBadRequest, "validation_failed", "content contains profanity")
		return
	}

	published := req.Published != nil && *req.Published
	p, err := s.Store.CreatePost(r.Context(), uid, req.Title, req.Body, published)
	if err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not create post")
		return
	}
	httpx.JSON(w, http.StatusCreated, toAPIPost(p))
}

// --- PUT /posts/{id} ---

func (s *Server) UpdatePost(w http.ResponseWriter, r *http.Request, id api.PostId) {
	uid, ok := s.requireAuth(w, r)
	if !ok {
		return
	}

	post, err := s.Store.GetPost(r.Context(), id)
	if errors.Is(err, store.ErrNotFound) {
		httpx.Err(w, http.StatusNotFound, "not_found", "post not found")
		return
	}
	if err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not load post")
		return
	}
	if post.AuthorID != uid {
		httpx.Err(w, http.StatusForbidden, "forbidden", "only the author can modify this post")
		return
	}

	var req api.UpdatePostRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		httpx.Err(w, http.StatusBadRequest, "invalid_body", "request body is not valid JSON")
		return
	}
	if req.Title != nil && strings.TrimSpace(*req.Title) == "" {
		httpx.Err(w, http.StatusBadRequest, "validation_failed", "title cannot be empty")
		return
	}
	if req.Body != nil && strings.TrimSpace(*req.Body) == "" {
		httpx.Err(w, http.StatusBadRequest, "validation_failed", "body cannot be empty")
		return
	}
	checkText := post.Title + " " + post.Body
	if req.Title != nil || req.Body != nil {
		title, body := post.Title, post.Body
		if req.Title != nil {
			title = *req.Title
		}
		if req.Body != nil {
			body = *req.Body
		}
		checkText = title + " " + body
	}
	if !s.Profanity.IsClean(r.Context(), checkText) {
		httpx.Err(w, http.StatusBadRequest, "validation_failed", "content contains profanity")
		return
	}

	updated, err := s.Store.UpdatePost(r.Context(), id, store.PostUpdate{Title: req.Title, Body: req.Body, Published: req.Published})
	if err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not update post")
		return
	}
	httpx.JSON(w, http.StatusOK, toAPIPost(updated))
}

// --- DELETE /posts/{id} ---

func (s *Server) DeletePost(w http.ResponseWriter, r *http.Request, id api.PostId) {
	uid, ok := s.requireAuth(w, r)
	if !ok {
		return
	}

	post, err := s.Store.GetPost(r.Context(), id)
	if errors.Is(err, store.ErrNotFound) {
		httpx.Err(w, http.StatusNotFound, "not_found", "post not found")
		return
	}
	if err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not load post")
		return
	}
	if post.AuthorID != uid {
		httpx.Err(w, http.StatusForbidden, "forbidden", "only the author can delete this post")
		return
	}

	if err := s.Store.DeletePost(r.Context(), id); err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not delete post")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// --- GET /posts/{id}/comments ---

func (s *Server) ListComments(w http.ResponseWriter, r *http.Request, id api.PostId, params api.ListCommentsParams) {
	if _, err := s.Store.GetPost(r.Context(), id); errors.Is(err, store.ErrNotFound) {
		httpx.Err(w, http.StatusNotFound, "not_found", "post not found")
		return
	} else if err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not load post")
		return
	}

	page, limit := 1, 20
	if params.Page != nil {
		page = *params.Page
	}
	if params.Limit != nil {
		limit = *params.Limit
	}
	if page < 1 || limit < 1 || limit > 100 {
		httpx.Err(w, http.StatusBadRequest, "validation_failed", "page must be >=1, limit must be 1-100")
		return
	}

	comments, total, err := s.Store.ListCommentsPage(r.Context(), id, limit, (page-1)*limit)
	if err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not list comments")
		return
	}

	withAuthors, err := s.attachAuthors(r.Context(), comments)
	if err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not load comment authors")
		return
	}
	httpx.JSON(w, http.StatusOK, api.CommentListResponse{Comments: withAuthors, Page: page, Limit: limit, Total: total})
}

// --- POST /posts/{id}/comments ---

func (s *Server) CreateComment(w http.ResponseWriter, r *http.Request, id api.PostId) {
	uid, ok := s.requireAuth(w, r)
	if !ok {
		return
	}

	if _, err := s.Store.GetPost(r.Context(), id); errors.Is(err, store.ErrNotFound) {
		httpx.Err(w, http.StatusNotFound, "not_found", "post not found")
		return
	} else if err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not load post")
		return
	}

	var req api.CreateCommentRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		httpx.Err(w, http.StatusBadRequest, "invalid_body", "request body is not valid JSON")
		return
	}
	if strings.TrimSpace(req.Body) == "" {
		httpx.Err(w, http.StatusBadRequest, "validation_failed", "body is required")
		return
	}
	if !s.Profanity.IsClean(r.Context(), req.Body) {
		httpx.Err(w, http.StatusBadRequest, "validation_failed", "content contains profanity")
		return
	}

	c, err := s.Store.CreateComment(r.Context(), id, uid, req.Body)
	if err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not create comment")
		return
	}
	httpx.JSON(w, http.StatusCreated, toAPIComment(c))
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

	apiComments, err := s.attachAuthors(ctx, comments)
	if err != nil {
		httpx.Err(w, http.StatusInternalServerError, "internal_error", "could not load comment authors")
		return
	}

	httpx.JSON(w, http.StatusOK, api.PostDetail{
		Id: post.ID, AuthorId: post.AuthorID, Title: post.Title, Body: post.Body,
		Published: post.Published, CreatedAt: post.CreatedAt,
		Author: toAPIUser(author), Comments: apiComments,
	})
}

// attachAuthors fetches each comment's author concurrently via errgroup.
func (s *Server) attachAuthors(ctx context.Context, comments []store.Comment) ([]api.CommentWithAuthor, error) {
	commentAuthors := make([]store.User, len(comments))
	g, gctx := errgroup.WithContext(ctx)
	for i, c := range comments {
		i, c := i, c
		g.Go(func() error {
			u, err := s.Store.GetUserByID(gctx, c.AuthorID)
			commentAuthors[i] = u
			return err
		})
	}
	if err := g.Wait(); err != nil {
		return nil, err
	}

	result := make([]api.CommentWithAuthor, len(comments))
	for i, c := range comments {
		result[i] = api.CommentWithAuthor{
			Id: c.ID, PostId: c.PostID, AuthorId: c.AuthorID, Body: c.Body,
			CreatedAt: c.CreatedAt, Author: toAPIUser(commentAuthors[i]),
		}
	}
	return result, nil
}
