// Mock profanity-check stub server. Not part of the language comparison —
// exists purely so both stacks can exercise "external HTTP call with
// timeout + graceful fallback" (plan.md criterion #6) deterministically.
//
// POST /check {"text": "..."} -> {"clean": bool, "matches": [...]}
//
// Force failure/slowness per-request via headers, no restart needed:
//
//	X-Mock-Delay: 3s      sleep before responding
//	X-Mock-Status: 500    respond with this status and no body
//
// Or force it for every subsequent /check call — useful for integration
// tests that hit a blog service, which has no reason to forward the headers
// above on its own outbound call:
//
//	POST /control {"delay": "3s", "status": 500}   set
//	POST /control {}                               clear
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

var wordlist = []string{"badword", "damn", "heck"}

var (
	mu           sync.Mutex
	globalDelay  time.Duration
	globalStatus int
)

type controlRequest struct {
	Delay  string `json:"delay"`
	Status int    `json:"status"`
}

func handleControl(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var req controlRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid body", http.StatusBadRequest)
		return
	}
	delay, _ := time.ParseDuration(req.Delay)

	mu.Lock()
	globalDelay, globalStatus = delay, req.Status
	mu.Unlock()

	w.WriteHeader(http.StatusNoContent)
}

type checkRequest struct {
	Text string `json:"text"`
}

type checkResponse struct {
	Clean   bool     `json:"clean"`
	Matches []string `json:"matches"`
}

func handleCheck(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	mu.Lock()
	delay, status := globalDelay, globalStatus
	mu.Unlock()

	if d := r.Header.Get("X-Mock-Delay"); d != "" {
		if dur, err := time.ParseDuration(d); err == nil {
			delay = dur
		}
	}
	if s := r.Header.Get("X-Mock-Status"); s != "" {
		fmt.Sscanf(s, "%d", &status)
	}

	if delay > 0 {
		time.Sleep(delay)
	}
	if status != 0 {
		w.WriteHeader(status)
		return
	}

	var req checkRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid body", http.StatusBadRequest)
		return
	}

	lower := strings.ToLower(req.Text)
	var matches []string
	for _, word := range wordlist {
		if strings.Contains(lower, word) {
			matches = append(matches, word)
		}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(checkResponse{
		Clean:   len(matches) == 0,
		Matches: matches,
	})
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "9090"
	}
	http.HandleFunc("/check", handleCheck)
	http.HandleFunc("/control", handleControl)
	log.Printf("mock-profanity-api listening on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
