// SQLite access via java.jdbc + the sqlite-jdbc driver (declared in
// Ballerina.toml under [[platform.java21.dependency]]) — Ballerina has no
// native SQLite client.
import ballerinax/java.jdbc;
import ballerina/sql;

// PRAGMA foreign_keys=ON is mandatory: SQLite defaults it off, which would
// silently defeat schema.sql's ON DELETE CASCADE (plan.md cascade-delete
// criterion). It's per-connection, so it's set via the JDBC URL, not once.
final jdbc:Client dbClient = check new (
    url = "jdbc:sqlite:" + dbPath + "?foreign_keys=on",
    connectionPool = {maxOpenConnections: 1}
);

type UserRow record {|
    int id;
    string username;
    string email;
    string password_hash;
    string created_at;
|};

type PostRow record {|
    int id;
    int author_id;
    string title;
    string body;
    int published;
    string created_at;
|};

type CommentRow record {|
    int id;
    int post_id;
    int author_id;
    string body;
    string created_at;
|};

function createUser(string username, string email, string passwordHash) returns UserRow|error {
    sql:ExecutionResult res = check dbClient->execute(`
        INSERT INTO users (username, email, password_hash) VALUES (${username}, ${email}, ${passwordHash})`);
    int|string? id = res.lastInsertId;
    if id !is int {
        return error("could not determine inserted user id");
    }
    return getUserById(id);
}

function getUserById(int id) returns UserRow|error {
    return check dbClient->queryRow(`SELECT id, username, email, password_hash, created_at FROM users WHERE id = ${id}`);
}

function getUserByEmail(string email) returns UserRow|error {
    return check dbClient->queryRow(`SELECT id, username, email, password_hash, created_at FROM users WHERE email = ${email}`);
}

function getPostById(int id) returns PostRow|error {
    return check dbClient->queryRow(`SELECT id, author_id, title, body, published, created_at FROM posts WHERE id = ${id}`);
}

function listCommentsByPost(int postId) returns CommentRow[]|error {
    stream<CommentRow, sql:Error?> resultStream = dbClient->query(
        `SELECT id, post_id, author_id, body, created_at FROM comments WHERE post_id = ${postId} ORDER BY id`);
    CommentRow[] comments = [];
    check from CommentRow c in resultStream
        do {
            comments.push(c);
        };
    return comments;
}
