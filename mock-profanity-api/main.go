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
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"
)

var wordlist = []string{"badword", "damn", "heck"}

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

	if d := r.Header.Get("X-Mock-Delay"); d != "" {
		if dur, err := time.ParseDuration(d); err == nil {
			time.Sleep(dur)
		}
	}
	if s := r.Header.Get("X-Mock-Status"); s != "" {
		var code int
		if _, err := fmt.Sscanf(s, "%d", &code); err == nil {
			w.WriteHeader(code)
			return
		}
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
	log.Printf("mock-profanity-api listening on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
