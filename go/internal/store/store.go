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
	return s.listComments(ctx, `SELECT id, post_id, author_id, body, created_at FROM comments WHERE post_id = ? ORDER BY id`, postID)
}

func (s *Store) ListCommentsPage(ctx context.Context, postID int64, limit, offset int) ([]Comment, int, error) {
	comments, err := s.listComments(ctx,
		`SELECT id, post_id, author_id, body, created_at FROM comments WHERE post_id = ? ORDER BY id LIMIT ? OFFSET ?`,
		postID, limit, offset)
	if err != nil {
		return nil, 0, err
	}
	var total int
	if err := s.DB.QueryRowContext(ctx, `SELECT count(*) FROM comments WHERE post_id = ?`, postID).Scan(&total); err != nil {
		return nil, 0, err
	}
	return comments, total, nil
}

func (s *Store) listComments(ctx context.Context, query string, args ...any) ([]Comment, error) {
	rows, err := s.DB.QueryContext(ctx, query, args...)
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

func (s *Store) CreateComment(ctx context.Context, postID, authorID int64, body string) (Comment, error) {
	res, err := s.DB.ExecContext(ctx,
		`INSERT INTO comments (post_id, author_id, body) VALUES (?, ?, ?)`, postID, authorID, body)
	if err != nil {
		return Comment{}, err
	}
	id, err := res.LastInsertId()
	if err != nil {
		return Comment{}, err
	}
	comments, err := s.listComments(ctx,
		`SELECT id, post_id, author_id, body, created_at FROM comments WHERE id = ?`, id)
	if err != nil {
		return Comment{}, err
	}
	return comments[0], nil
}

func (s *Store) ListPosts(ctx context.Context, published *bool, limit, offset int) ([]Post, int, error) {
	query := `SELECT id, author_id, title, body, published, created_at FROM posts`
	countQuery := `SELECT count(*) FROM posts`
	var args []any
	if published != nil {
		v := 0
		if *published {
			v = 1
		}
		query += ` WHERE published = ?`
		countQuery += ` WHERE published = ?`
		args = append(args, v)
	}
	query += ` ORDER BY id LIMIT ? OFFSET ?`

	rows, err := s.DB.QueryContext(ctx, query, append(args, limit, offset)...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	var posts []Post
	for rows.Next() {
		var p Post
		var createdAt string
		var pub int
		if err := rows.Scan(&p.ID, &p.AuthorID, &p.Title, &p.Body, &pub, &createdAt); err != nil {
			return nil, 0, err
		}
		p.Published = pub != 0
		p.CreatedAt, err = parseTime(createdAt)
		if err != nil {
			return nil, 0, err
		}
		posts = append(posts, p)
	}
	if err := rows.Err(); err != nil {
		return nil, 0, err
	}

	var total int
	if err := s.DB.QueryRowContext(ctx, countQuery, args...).Scan(&total); err != nil {
		return nil, 0, err
	}
	return posts, total, nil
}

func (s *Store) CreatePost(ctx context.Context, authorID int64, title, body string, published bool) (Post, error) {
	res, err := s.DB.ExecContext(ctx,
		`INSERT INTO posts (author_id, title, body, published) VALUES (?, ?, ?, ?)`,
		authorID, title, body, published)
	if err != nil {
		return Post{}, err
	}
	id, err := res.LastInsertId()
	if err != nil {
		return Post{}, err
	}
	return s.GetPost(ctx, id)
}

type PostUpdate struct {
	Title     *string
	Body      *string
	Published *bool
}

func (s *Store) UpdatePost(ctx context.Context, id int64, u PostUpdate) (Post, error) {
	current, err := s.GetPost(ctx, id)
	if err != nil {
		return Post{}, err
	}
	title, body, published := current.Title, current.Body, current.Published
	if u.Title != nil {
		title = *u.Title
	}
	if u.Body != nil {
		body = *u.Body
	}
	if u.Published != nil {
		published = *u.Published
	}
	_, err = s.DB.ExecContext(ctx,
		`UPDATE posts SET title = ?, body = ?, published = ? WHERE id = ?`, title, body, published, id)
	if err != nil {
		return Post{}, err
	}
	return s.GetPost(ctx, id)
}

func (s *Store) DeletePost(ctx context.Context, id int64) error {
	_, err := s.DB.ExecContext(ctx, `DELETE FROM posts WHERE id = ?`, id)
	return err
}

func parseTime(s string) (time.Time, error) {
	return time.Parse("2006-01-02T15:04:05.000Z", s)
}
