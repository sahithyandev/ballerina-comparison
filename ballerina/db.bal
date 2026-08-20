// SQLite access via kanushka/sqlite, a native Ballerina Central connector
// (no JDBC/Java interop needed for this data point, unlike bcrypt).
import kanushka/sqlite;
import ballerina/sql;

// PRAGMA foreign_keys=ON is mandatory: SQLite defaults it off, which would
// silently defeat schema.sql's ON DELETE CASCADE (plan.md cascade-delete
// criterion). It's per-connection, so it's set via options, not once.
final sqlite:Client dbClient = check new ({
    path: dbPath,
    options: {properties: {"foreign_keys": "on"}},
    connectionPool: {maxOpenConnections: 1}
});

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

// kanushka/sqlite's queryRow/query return untyped `record {}` (unlike
// ballerinax/java.jdbc, which infers the target record type from context) —
// cloneWithType() does the conversion at each call site instead.
function getUserById(int id) returns UserRow|error {
    record {} row = check dbClient->queryRow(`SELECT id, username, email, password_hash, created_at FROM users WHERE id = ${id}`);
    return row.cloneWithType(UserRow);
}

function getUserByEmail(string email) returns UserRow|error {
    record {} row = check dbClient->queryRow(`SELECT id, username, email, password_hash, created_at FROM users WHERE email = ${email}`);
    return row.cloneWithType(UserRow);
}

function getPostById(int id) returns PostRow|error {
    record {} row = check dbClient->queryRow(`SELECT id, author_id, title, body, published, created_at FROM posts WHERE id = ${id}`);
    return row.cloneWithType(PostRow);
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

    stream<record {}, sql:Error?> resultStream = dbClient->query(sql:queryConcat(baseQuery, filter, page));
    PostRow[] posts = [];
    check from record {} r in resultStream
        do {
            posts.push(check r.cloneWithType(PostRow));
        };

    record {} countRaw = check dbClient->queryRow(sql:queryConcat(countBaseQuery, filter));
    record {|int total;|} countRow = check countRaw.cloneWithType();
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
    record {} countRaw = check dbClient->queryRow(
        `SELECT count(*) AS total FROM comments WHERE post_id = ${postId}`);
    record {|int total;|} countRow = check countRaw.cloneWithType();
    return {comments, total: countRow.total};
}

function createComment(int postId, int authorId, string body) returns CommentRow|error {
    sql:ExecutionResult res = check dbClient->execute(`
        INSERT INTO comments (post_id, author_id, body) VALUES (${postId}, ${authorId}, ${body})`);
    int|string? id = res.lastInsertId;
    if id !is int {
        return error("could not determine inserted comment id");
    }
    record {} row = check dbClient->queryRow(`SELECT id, post_id, author_id, body, created_at FROM comments WHERE id = ${id}`);
    return row.cloneWithType(CommentRow);
}

function runCommentQuery(sql:ParameterizedQuery query) returns CommentRow[]|error {
    stream<record {}, sql:Error?> resultStream = dbClient->query(query);
    CommentRow[] comments = [];
    check from record {} r in resultStream
        do {
            comments.push(check r.cloneWithType(CommentRow));
        };
    return comments;
}
