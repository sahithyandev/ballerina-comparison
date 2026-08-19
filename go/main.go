package main

import (
	"log/slog"
	"net/http"
	"os"

	"github.com/go-chi/chi/v5"

	"blog-go/internal/api"
	"blog-go/internal/config"
	"blog-go/internal/db"
	"blog-go/internal/handlers"
	"blog-go/internal/store"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config error", "err", err)
		os.Exit(1)
	}

	conn, err := db.Open(cfg.DBPath)
	if err != nil {
		slog.Error("db open failed", "err", err)
		os.Exit(1)
	}
	defer conn.Close()

	s := handlers.New(store.New(conn), cfg)

	r := chi.NewRouter()
	r.Use(requestLogger)
	apiRouter := api.HandlerFromMux(s, chi.NewRouter())
	r.Mount("/api/v1", apiRouter)

	slog.Info("listening", "port", cfg.Port)
	if err := http.ListenAndServe(":"+cfg.Port, r); err != nil {
		slog.Error("server stopped", "err", err)
		os.Exit(1)
	}
}

func requestLogger(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		slog.Info("request", "method", r.Method, "path", r.URL.Path)
		next.ServeHTTP(w, r)
	})
}
