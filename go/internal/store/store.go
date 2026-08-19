// Package store is the SQLite data-access layer. Kept as plain SQL over
// database/sql — no ORM, the domain is three tables.
package store

import (
	"context"
	"database/sql"
	"errors"
	"time"
)

var ErrNotFound = errors.New("not found")

type Store struct {
	DB *sql.DB
}

type User struct {
	ID           int64
	Username     string
	Email        string
	PasswordHash string
	CreatedAt    time.Time
}

type Post struct {
	ID        int64
	AuthorID  int64
	Title     string
	Body      string
	Published bool
	CreatedAt time.Time
}

type Comment struct {
	ID        int64
	PostID    int64
	AuthorID  int64
	Body      string
	CreatedAt time.Time
}

func New(db *sql.DB) *Store {
	return &Store{DB: db}
}

func (s *Store) CreateUser(ctx context.Context, username, email, passwordHash string) (User, error) {
	res, err := s.DB.ExecContext(ctx,
		`INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)`,
		username, email, passwordHash)
	if err != nil {
		return User{}, err
	}
	id, err := res.LastInsertId()
	if err != nil {
		return User{}, err
	}
	return s.GetUserByID(ctx, id)
}

func (s *Store) GetUserByID(ctx context.Context, id int64) (User, error) {
	return s.scanUser(s.DB.QueryRowContext(ctx,
		`SELECT id, username, email, password_hash, created_at FROM users WHERE id = ?`, id))
}

func (s *Store) GetUserByEmail(ctx context.Context, email string) (User, error) {
	return s.scanUser(s.DB.QueryRowContext(ctx,
		`SELECT id, username, email, password_hash, created_at FROM users WHERE email = ?`, email))
}

func (s *Store) scanUser(row *sql.Row) (User, error) {
	var u User
	var createdAt string
	err := row.Scan(&u.ID, &u.Username, &u.Email, &u.PasswordHash, &createdAt)
	if errors.Is(err, sql.ErrNoRows) {
		return User{}, ErrNotFound
	}
	if err != nil {
		return User{}, err
	}
	u.CreatedAt, err = parseTime(createdAt)
	return u, err
}

func (s *Store) GetPost(ctx context.Context, id int64) (Post, error) {
	var p Post
	var createdAt string
	var published int
	err := s.DB.QueryRowContext(ctx,
		`SELECT id, author_id, title, body, published, created_at FROM posts WHERE id = ?`, id).
		Scan(&p.ID, &p.AuthorID, &p.Title, &p.Body, &published, &createdAt)
	if errors.Is(err, sql.ErrNoRows) {
		return Post{}, ErrNotFound
	}
	if err != nil {
		return Post{}, err
	}
	p.Published = published != 0
	p.CreatedAt, err = parseTime(createdAt)
	return p, err
}

func (s *Store) ListCommentsByPost(ctx context.Context, postID int64) ([]Comment, error) {
	rows, err := s.DB.QueryContext(ctx,
		`SELECT id, post_id, author_id, body, created_at FROM comments WHERE post_id = ? ORDER BY id`, postID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var comments []Comment
	for rows.Next() {
		var c Comment
		var createdAt string
		if err := rows.Scan(&c.ID, &c.PostID, &c.AuthorID, &c.Body, &createdAt); err != nil {
			return nil, err
		}
		c.CreatedAt, err = parseTime(createdAt)
		if err != nil {
			return nil, err
		}
		comments = append(comments, c)
	}
	return comments, rows.Err()
}

func parseTime(s string) (time.Time, error) {
	return time.Parse("2006-01-02T15:04:05.000Z", s)
}
