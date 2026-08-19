package handlers_test

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"

	"blog-go/internal/api"
	"blog-go/internal/config"
	"blog-go/internal/db"
	"blog-go/internal/handlers"
	"blog-go/internal/store"
)

// newTestServer wires up a real HTTP server against a fresh on-disk SQLite
// db built from the shared schema.sql, with an unreachable profanity URL so
// the fail-open fallback (plan.md criterion #6) is exercised on every write
// in these tests rather than depending on the stub server being up.
func newTestServer(t *testing.T) *httptest.Server {
	t.Helper()

	dbPath := filepath.Join(t.TempDir(), "test.db")
	conn, err := db.Open(dbPath)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	schema, err := os.ReadFile("../../../schema.sql")
	if err != nil {
		t.Fatalf("read schema.sql: %v", err)
	}
	if _, err := conn.Exec(string(schema)); err != nil {
		t.Fatalf("apply schema: %v", err)
	}

	cfg := config.Config{
		JWTSecret:        "test-secret",
		JWTExpiry:        time.Hour,
		ProfanityURL:     "http://127.0.0.1:1", // nothing listens here -> fails open
		ProfanityTimeout: 200 * time.Millisecond,
	}
	s := handlers.New(store.New(conn), cfg)
	r := chi.NewRouter()
	r.Mount("/api/v1", api.HandlerFromMux(s, chi.NewRouter()))

	ts := httptest.NewServer(r)
	t.Cleanup(func() {
		ts.Close()
		conn.Close()
	})
	return ts
}

// do issues a JSON request and decodes the JSON response body, if any.
func do(t *testing.T, ts *httptest.Server, method, path, token string, body any) (*http.Response, map[string]any) {
	t.Helper()

	var reader *bytes.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal body: %v", err)
		}
		reader = bytes.NewReader(b)
	} else {
		reader = bytes.NewReader(nil)
	}

	req, err := http.NewRequest(method, ts.URL+path, reader)
	if err != nil {
		t.Fatalf("build request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}

	resp, err := ts.Client().Do(req)
	if err != nil {
		t.Fatalf("do request: %v", err)
	}
	defer resp.Body.Close()

	var out map[string]any
	if resp.ContentLength != 0 {
		if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
			t.Fatalf("decode response: %v", err)
		}
	}
	return resp, out
}

func register(t *testing.T, ts *httptest.Server, username, email, password string) (token string, userID float64) {
	t.Helper()
	resp, out := do(t, ts, http.MethodPost, "/api/v1/auth/register", "", map[string]string{
		"username": username, "email": email, "password": password,
	})
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("register %s: status %d, body %v", username, resp.StatusCode, out)
	}
	return out["token"].(string), out["user"].(map[string]any)["id"].(float64)
}

func TestRegisterValidation(t *testing.T) {
	ts := newTestServer(t)

	cases := []struct {
		name       string
		body       map[string]string
		wantStatus int
		wantCode   string
	}{
		{"username too short", map[string]string{"username": "ab", "email": "a@example.com", "password": "password123"}, http.StatusBadRequest, "validation_failed"},
		{"password too short", map[string]string{"username": "alice", "email": "a@example.com", "password": "short"}, http.StatusBadRequest, "validation_failed"},
		{"malformed email", map[string]string{"username": "alice", "email": "not-an-email", "password": "password123"}, http.StatusBadRequest, "invalid_body"},
		{"valid", map[string]string{"username": "alice", "email": "alice@example.com", "password": "password123"}, http.StatusCreated, ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			resp, out := do(t, ts, http.MethodPost, "/api/v1/auth/register", "", tc.body)
			if resp.StatusCode != tc.wantStatus {
				t.Fatalf("status = %d, want %d (body %v)", resp.StatusCode, tc.wantStatus, out)
			}
			if tc.wantCode != "" && out["error"].(map[string]any)["code"] != tc.wantCode {
				t.Fatalf("error code = %v, want %s", out["error"], tc.wantCode)
			}
		})
	}
}

func TestRegisterDuplicateEmail(t *testing.T) {
	ts := newTestServer(t)
	register(t, ts, "bob", "bob@example.com", "password123")

	resp, out := do(t, ts, http.MethodPost, "/api/v1/auth/register", "", map[string]string{
		"username": "bob2", "email": "bob@example.com", "password": "password123",
	})
	if resp.StatusCode != http.StatusConflict {
		t.Fatalf("status = %d, want 409 (body %v)", resp.StatusCode, out)
	}
}

func TestLoginFlow(t *testing.T) {
	ts := newTestServer(t)
	register(t, ts, "carol", "carol@example.com", "password123")

	resp, out := do(t, ts, http.MethodPost, "/api/v1/auth/login", "", map[string]string{
		"email": "carol@example.com", "password": "wrong-password",
	})
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("wrong password: status = %d, want 401 (body %v)", resp.StatusCode, out)
	}

	resp, out = do(t, ts, http.MethodPost, "/api/v1/auth/login", "", map[string]string{
		"email": "carol@example.com", "password": "password123",
	})
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("correct password: status = %d, want 200 (body %v)", resp.StatusCode, out)
	}
	if out["token"] == nil || out["token"] == "" {
		t.Fatalf("expected a token in response, got %v", out)
	}
}

func TestCreatePostRequiresAuth(t *testing.T) {
	ts := newTestServer(t)
	resp, _ := do(t, ts, http.MethodPost, "/api/v1/posts", "", map[string]string{"title": "t", "body": "b"})
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401", resp.StatusCode)
	}
}

func TestCreatePostValidation(t *testing.T) {
	ts := newTestServer(t)
	token, _ := register(t, ts, "dave", "dave@example.com", "password123")

	resp, out := do(t, ts, http.MethodPost, "/api/v1/posts", token, map[string]string{"title": "  ", "body": "body"})
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("empty title: status = %d, want 400 (body %v)", resp.StatusCode, out)
	}

	resp, out = do(t, ts, http.MethodPost, "/api/v1/posts", token, map[string]string{"title": "title", "body": "body"})
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("valid post (with profanity check unreachable, should fail open): status = %d, want 201 (body %v)", resp.StatusCode, out)
	}
}

func TestPostOwnership(t *testing.T) {
	ts := newTestServer(t)
	authorToken, _ := register(t, ts, "erin", "erin@example.com", "password123")
	otherToken, _ := register(t, ts, "frank", "frank@example.com", "password123")

	_, post := do(t, ts, http.MethodPost, "/api/v1/posts", authorToken, map[string]string{"title": "hello", "body": "world"})
	postID := int64(post["id"].(float64))
	path := "/api/v1/posts/" + strconv.FormatInt(postID, 10)

	resp, _ := do(t, ts, http.MethodPut, path, otherToken, map[string]string{"title": "hijacked"})
	if resp.StatusCode != http.StatusForbidden {
		t.Fatalf("update by non-author: status = %d, want 403", resp.StatusCode)
	}

	resp, _ = do(t, ts, http.MethodDelete, path, otherToken, nil)
	if resp.StatusCode != http.StatusForbidden {
		t.Fatalf("delete by non-author: status = %d, want 403", resp.StatusCode)
	}

	resp, _ = do(t, ts, http.MethodPut, path, authorToken, map[string]string{"title": "updated"})
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("update by author: status = %d, want 200", resp.StatusCode)
	}
}

func TestGetPostFanOut(t *testing.T) {
	ts := newTestServer(t)
	authorToken, _ := register(t, ts, "gina", "gina@example.com", "password123")
	commenterToken, _ := register(t, ts, "hank", "hank@example.com", "password123")

	_, post := do(t, ts, http.MethodPost, "/api/v1/posts", authorToken, map[string]string{"title": "hello", "body": "world"})
	postID := int64(post["id"].(float64))
	path := "/api/v1/posts/" + strconv.FormatInt(postID, 10)

	resp, _ := do(t, ts, http.MethodPost, path+"/comments", commenterToken, map[string]string{"body": "nice post"})
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("create comment: status = %d", resp.StatusCode)
	}

	resp, out := do(t, ts, http.MethodGet, path, "", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("get post: status = %d", resp.StatusCode)
	}
	author, ok := out["author"].(map[string]any)
	if !ok || author["username"] != "gina" {
		t.Fatalf("expected author gina attached, got %v", out["author"])
	}
	comments, ok := out["comments"].([]any)
	if !ok || len(comments) != 1 {
		t.Fatalf("expected 1 comment, got %v", out["comments"])
	}
	commentAuthor := comments[0].(map[string]any)["author"].(map[string]any)
	if commentAuthor["username"] != "hank" {
		t.Fatalf("expected comment author hank, got %v", commentAuthor)
	}
}
