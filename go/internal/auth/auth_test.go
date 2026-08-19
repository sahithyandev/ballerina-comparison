package auth_test

import (
	"testing"
	"time"

	"blog-go/internal/auth"
)

func TestHashAndCheckPassword(t *testing.T) {
	hash, err := auth.HashPassword("password123")
	if err != nil {
		t.Fatalf("HashPassword: %v", err)
	}
	if !auth.CheckPassword(hash, "password123") {
		t.Fatal("expected correct password to check out")
	}
	if auth.CheckPassword(hash, "wrong-password") {
		t.Fatal("expected wrong password to fail")
	}
}

func TestIssueAndParseToken(t *testing.T) {
	token, err := auth.IssueToken("secret", time.Hour, 42)
	if err != nil {
		t.Fatalf("IssueToken: %v", err)
	}

	uid, err := auth.ParseToken("secret", token)
	if err != nil {
		t.Fatalf("ParseToken: %v", err)
	}
	if uid != 42 {
		t.Fatalf("uid = %d, want 42", uid)
	}

	if _, err := auth.ParseToken("wrong-secret", token); err == nil {
		t.Fatal("expected token signed with a different secret to be rejected")
	}
}

func TestParseTokenExpired(t *testing.T) {
	token, err := auth.IssueToken("secret", -time.Hour, 1)
	if err != nil {
		t.Fatalf("IssueToken: %v", err)
	}
	if _, err := auth.ParseToken("secret", token); err == nil {
		t.Fatal("expected expired token to be rejected")
	}
}
