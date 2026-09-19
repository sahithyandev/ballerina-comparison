package blog;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

// SQLite data-access layer over sqlite-jdbc. Plain SQL, no ORM — the domain
// is three tables, same as store.go/store.py/store.js/store.ts/store.rs.
//
// One java.sql.Connection, and every method is `synchronized`: SQLite only
// supports one writer at a time, and a single serialized connection avoids
// SQLITE_BUSY under the concurrent workloads this comparison load-tests —
// the same single-writer constraint as Go's SetMaxOpenConns(1) and Rust's
// Mutex<Connection>, made explicit since sqlite-jdbc ships no pool.
public final class Store implements AutoCloseable {

    public record User(long id, String username, String email, String passwordHash, String createdAt) {
    }

    public record Post(long id, long authorId, String title, String body, boolean published, String createdAt) {
    }

    public record Comment(long id, long postId, long authorId, String body, String createdAt) {
    }

    public static final class NotFoundException extends RuntimeException {
    }

    private final Connection conn;

    public Store(String path) {
        try {
            this.conn = DriverManager.getConnection("jdbc:sqlite:" + path);
            try (Statement s = conn.createStatement()) {
                // Mandatory: SQLite defaults foreign_keys OFF, which silently
                // defeats the ON DELETE CASCADE in schema.sql.
                s.execute("PRAGMA foreign_keys = ON");
            }
        } catch (SQLException e) {
            throw new RuntimeException("db open failed: " + e.getMessage(), e);
        }
    }

    @Override
    public synchronized void close() throws SQLException {
        conn.close();
    }

    // ---- row mappers ----

    private static User toUser(ResultSet rs) throws SQLException {
        return new User(rs.getLong(1), rs.getString(2), rs.getString(3), rs.getString(4), rs.getString(5));
    }

    private static Post toPost(ResultSet rs) throws SQLException {
        return new Post(rs.getLong(1), rs.getLong(2), rs.getString(3), rs.getString(4),
                rs.getInt(5) != 0, rs.getString(6));
    }

    private static Comment toComment(ResultSet rs) throws SQLException {
        return new Comment(rs.getLong(1), rs.getLong(2), rs.getLong(3), rs.getString(4), rs.getString(5));
    }

    // ---- users ----

    public synchronized User createUser(String username, String email, String passwordHash) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)")) {
            ps.setString(1, username);
            ps.setString(2, email);
            ps.setString(3, passwordHash);
            ps.executeUpdate();
        }
        return getUserById(lastInsertRowid());
    }

    public synchronized User getUserById(long id) {
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT id, username, email, password_hash, created_at FROM users WHERE id = ?")) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new NotFoundException();
                }
                return toUser(rs);
            }
        } catch (SQLException e) {
            throw new RuntimeException(e);
        }
    }

    public synchronized Optional<User> findUserByEmail(String email) {
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT id, username, email, password_hash, created_at FROM users WHERE email = ?")) {
            ps.setString(1, email);
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next() ? Optional.of(toUser(rs)) : Optional.empty();
            }
        } catch (SQLException e) {
            throw new RuntimeException(e);
        }
    }

    // ---- posts ----

    public synchronized Post getPost(long id) {
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT id, author_id, title, body, published, created_at FROM posts WHERE id = ?")) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new NotFoundException();
                }
                return toPost(rs);
            }
        } catch (SQLException e) {
            throw new RuntimeException(e);
        }
    }

    public record PostPage(List<Post> posts, long total) {
    }

    public synchronized PostPage listPosts(Boolean published, int limit, int offset) {
        String where = published == null ? "" : " WHERE published = ?";
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT id, author_id, title, body, published, created_at FROM posts" + where
                        + " ORDER BY id LIMIT ? OFFSET ?");
                PreparedStatement cs = conn.prepareStatement("SELECT count(*) FROM posts" + where)) {
            int i = 1;
            if (published != null) {
                ps.setInt(i++, published ? 1 : 0);
                cs.setInt(1, published ? 1 : 0);
            }
            ps.setInt(i++, limit);
            ps.setInt(i, offset);
            List<Post> posts = new ArrayList<>();
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    posts.add(toPost(rs));
                }
            }
            long total;
            try (ResultSet rs = cs.executeQuery()) {
                rs.next();
                total = rs.getLong(1);
            }
            return new PostPage(posts, total);
        } catch (SQLException e) {
            throw new RuntimeException(e);
        }
    }

    public synchronized Post createPost(long authorId, String title, String body, boolean published) {
        try (PreparedStatement ps = conn.prepareStatement(
                "INSERT INTO posts (author_id, title, body, published) VALUES (?, ?, ?, ?)")) {
            ps.setLong(1, authorId);
            ps.setString(2, title);
            ps.setString(3, body);
            ps.setInt(4, published ? 1 : 0);
            ps.executeUpdate();
            return getPost(lastInsertRowid());
        } catch (SQLException e) {
            throw new RuntimeException(e);
        }
    }

    public synchronized Post updatePost(long id, String title, String body, Boolean published) {
        Post current = getPost(id);
        String newTitle = title != null ? title : current.title();
        String newBody = body != null ? body : current.body();
        boolean newPublished = published != null ? published : current.published();
        try (PreparedStatement ps = conn.prepareStatement(
                "UPDATE posts SET title = ?, body = ?, published = ? WHERE id = ?")) {
            ps.setString(1, newTitle);
            ps.setString(2, newBody);
            ps.setInt(3, newPublished ? 1 : 0);
            ps.setLong(4, id);
            ps.executeUpdate();
            return getPost(id);
        } catch (SQLException e) {
            throw new RuntimeException(e);
        }
    }

    public synchronized void deletePost(long id) {
        try (PreparedStatement ps = conn.prepareStatement("DELETE FROM posts WHERE id = ?")) {
            ps.setLong(1, id);
            ps.executeUpdate();
        } catch (SQLException e) {
            throw new RuntimeException(e);
        }
    }

    // ---- comments ----

    public synchronized List<Comment> listCommentsByPost(long postId) {
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT id, post_id, author_id, body, created_at FROM comments WHERE post_id = ? ORDER BY id")) {
            ps.setLong(1, postId);
            List<Comment> out = new ArrayList<>();
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    out.add(toComment(rs));
                }
            }
            return out;
        } catch (SQLException e) {
            throw new RuntimeException(e);
        }
    }

    public record CommentPage(List<Comment> comments, long total) {
    }

    public synchronized CommentPage listCommentsPage(long postId, int limit, int offset) {
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT id, post_id, author_id, body, created_at FROM comments WHERE post_id = ?"
                        + " ORDER BY id LIMIT ? OFFSET ?");
                PreparedStatement cs = conn.prepareStatement(
                        "SELECT count(*) FROM comments WHERE post_id = ?")) {
            ps.setLong(1, postId);
            ps.setInt(2, limit);
            ps.setInt(3, offset);
            cs.setLong(1, postId);
            List<Comment> comments = new ArrayList<>();
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    comments.add(toComment(rs));
                }
            }
            long total;
            try (ResultSet rs = cs.executeQuery()) {
                rs.next();
                total = rs.getLong(1);
            }
            return new CommentPage(comments, total);
        } catch (SQLException e) {
            throw new RuntimeException(e);
        }
    }

    public synchronized Comment createComment(long postId, long authorId, String body) {
        try (PreparedStatement ps = conn.prepareStatement(
                "INSERT INTO comments (post_id, author_id, body) VALUES (?, ?, ?)")) {
            ps.setLong(1, postId);
            ps.setLong(2, authorId);
            ps.setString(3, body);
            ps.executeUpdate();
        } catch (SQLException e) {
            throw new RuntimeException(e);
        }
        long id = lastInsertRowid();
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT id, post_id, author_id, body, created_at FROM comments WHERE id = ?")) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                rs.next();
                return toComment(rs);
            }
        } catch (SQLException e) {
            throw new RuntimeException(e);
        }
    }

    private long lastInsertRowid() {
        try (Statement s = conn.createStatement();
                ResultSet rs = s.executeQuery("SELECT last_insert_rowid()")) {
            rs.next();
            return rs.getLong(1);
        } catch (SQLException e) {
            throw new RuntimeException(e);
        }
    }
}
