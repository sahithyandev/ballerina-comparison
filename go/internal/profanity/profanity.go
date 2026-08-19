// Package profanity calls the mock profanity-check stub with a timeout and
// fails open: any error or timeout is treated as "clean" and logged, so a
// down dependency never blocks a user's write (plan.md criterion #6).
package profanity

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"time"
)

type Checker struct {
	URL     string
	Timeout time.Duration
	Client  *http.Client
}

func New(url string, timeout time.Duration) *Checker {
	return &Checker{URL: url, Timeout: timeout, Client: &http.Client{}}
}

func (c *Checker) IsClean(ctx context.Context, text string) bool {
	ctx, cancel := context.WithTimeout(ctx, c.Timeout)
	defer cancel()

	body, _ := json.Marshal(map[string]string{"text": text})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.URL+"/check", bytes.NewReader(body))
	if err != nil {
		slog.Warn("profanity check request build failed, allowing content", "err", err)
		return true
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.Client.Do(req)
	if err != nil {
		slog.Warn("profanity check unreachable, allowing content", "err", err)
		return true
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		slog.Warn("profanity check returned non-200, allowing content", "status", resp.StatusCode)
		return true
	}

	var result struct {
		Clean bool `json:"clean"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		slog.Warn("profanity check response unreadable, allowing content", "err", err)
		return true
	}
	return result.Clean
}
