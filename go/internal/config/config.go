// Package config loads settings strictly from env vars (plan.md criterion #9).
// No hardcoded fallback for secrets: missing JWT_SECRET fails startup, not a
// silent insecure default.
package config

import (
	"fmt"
	"os"
	"time"
)

type Config struct {
	Port             string
	DBPath           string
	JWTSecret        string
	JWTExpiry        time.Duration
	ProfanityURL     string
	ProfanityTimeout time.Duration
}

func Load() (Config, error) {
	c := Config{
		Port:         getenv("PORT", "8080"),
		DBPath:       getenv("DB_PATH", "./blog.db"),
		ProfanityURL: getenv("PROFANITY_URL", "http://localhost:9090"),
	}

	c.JWTSecret = os.Getenv("JWT_SECRET")
	if c.JWTSecret == "" {
		return Config{}, fmt.Errorf("JWT_SECRET is required")
	}

	expiry, err := time.ParseDuration(getenv("JWT_EXPIRY", "24h"))
	if err != nil {
		return Config{}, fmt.Errorf("invalid JWT_EXPIRY: %w", err)
	}
	c.JWTExpiry = expiry

	timeout, err := time.ParseDuration(getenv("PROFANITY_TIMEOUT", "2s"))
	if err != nil {
		return Config{}, fmt.Errorf("invalid PROFANITY_TIMEOUT: %w", err)
	}
	c.ProfanityTimeout = timeout

	return c, nil
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
