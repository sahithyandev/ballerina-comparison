// Package httpx holds tiny response helpers shared by handlers.
package httpx

import (
	"encoding/json"
	"net/http"

	"blog-go/internal/api"
)

func JSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if body != nil {
		json.NewEncoder(w).Encode(body)
	}
}

func Err(w http.ResponseWriter, status int, code, message string) {
	JSON(w, status, api.Error{Error: struct {
		Code    string  `json:"code"`
		Details *string `json:"details,omitempty"`
		Message string  `json:"message"`
	}{Code: code, Message: message}})
}
