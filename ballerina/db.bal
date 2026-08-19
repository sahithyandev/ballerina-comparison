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
    return runCommentQuery(
        `SELECT id, post_id, author_id, body, created_at FROM comments WHERE post_id = ${postId} ORDER BY id`);
}

type PostPage record {|
    PostRow[] posts;
    int total;
|};

function listPosts(boolean? published, int 'limit, int offset) returns PostPage|error {
    sql:ParameterizedQuery baseQuery = `SELECT id, author_id, title, body, published, created_at FROM posts`;
    sql:ParameterizedQuery countBaseQuery = `SELECT count(*) AS total FROM posts`;
    sql:ParameterizedQuery filter = published is boolean ? ` WHERE published = ${published ? 1 : 0}` : ``;
    sql:ParameterizedQuery page = ` ORDER BY id LIMIT ${'limit} OFFSET ${offset}`;

    stream<PostRow, sql:Error?> resultStream = dbClient->query(sql:queryConcat(baseQuery, filter, page));
    PostRow[] posts = [];
    check from PostRow p in resultStream
        do {
            posts.push(p);
        };

    record {|int total;|} countRow = check dbClient->queryRow(sql:queryConcat(countBaseQuery, filter));
    return {posts, total: countRow.total};
}

function createPost(int authorId, string title, string body, boolean published) returns PostRow|error {
    sql:ExecutionResult res = check dbClient->execute(`
        INSERT INTO posts (author_id, title, body, published) VALUES (${authorId}, ${title}, ${body}, ${published ? 1 : 0})`);
    int|string? id = res.lastInsertId;
    if id !is int {
        return error("could not determine inserted post id");
    }
    return getPostById(id);
}

function updatePost(int id, string? title, string? body, boolean? published) returns PostRow|error {
    PostRow current = check getPostById(id);
    string newTitle = title ?: current.title;
    string newBody = body ?: current.body;
    int newPublished = published is boolean ? (published ? 1 : 0) : current.published;
    _ = check dbClient->execute(`
        UPDATE posts SET title = ${newTitle}, body = ${newBody}, published = ${newPublished} WHERE id = ${id}`);
    return getPostById(id);
}

function deletePost(int id) returns error? {
    _ = check dbClient->execute(`DELETE FROM posts WHERE id = ${id}`);
}

function listCommentsPage(int postId, int 'limit, int offset) returns record {|CommentRow[] comments; int total;|}|error {
    CommentRow[] comments = check runCommentQuery(
        `SELECT id, post_id, author_id, body, created_at FROM comments
         WHERE post_id = ${postId} ORDER BY id LIMIT ${'limit} OFFSET ${offset}`);
    record {|int total;|} countRow = check dbClient->queryRow(
        `SELECT count(*) AS total FROM comments WHERE post_id = ${postId}`);
    return {comments, total: countRow.total};
}

function createComment(int postId, int authorId, string body) returns CommentRow|error {
    sql:ExecutionResult res = check dbClient->execute(`
        INSERT INTO comments (post_id, author_id, body) VALUES (${postId}, ${authorId}, ${body})`);
    int|string? id = res.lastInsertId;
    if id !is int {
        return error("could not determine inserted comment id");
    }
    return check dbClient->queryRow(`SELECT id, post_id, author_id, body, created_at FROM comments WHERE id = ${id}`);
}

function runCommentQuery(sql:ParameterizedQuery query) returns CommentRow[]|error {
    stream<CommentRow, sql:Error?> resultStream = dbClient->query(query);
    CommentRow[] comments = [];
    check from CommentRow c in resultStream
        do {
            comments.push(c);
        };
    return comments;
}
