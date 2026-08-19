// Package db opens the shared SQLite file. PRAGMA foreign_keys=ON is
// mandatory here — SQLite defaults it off, which would silently defeat the
// ON DELETE CASCADE in schema.sql (plan.md criterion #2 / cascade delete).
package db

import (
	"database/sql"
	"fmt"

	_ "modernc.org/sqlite"
)

func Open(path string) (*sql.DB, error) {
	dsn := fmt.Sprintf("file:%s?_pragma=foreign_keys(1)", path)
	conn, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}
	// SQLite only supports one writer at a time; a single connection avoids
	// SQLITE_BUSY under the concurrent workloads this comparison load-tests.
	conn.SetMaxOpenConns(1)
	if err := conn.Ping(); err != nil {
		return nil, err
	}
	return conn, nil
}
