// Integration tests against the running service (plan.md criterion #10).
// `bal test` starts the module's real listener + dbClient, so these tests
// hit the actual HTTP service — mirrors go/internal/handlers/handlers_test.go.
//
// Requires the same setup as `bal run`: a blog.db created from
// ../schema.sql (see README "Getting Started"), plus JWT_SECRET (and
// ideally PROFANITY_URL pointed at an unreachable host, so writes exercise
// the fail-open fallback deterministically instead of depending on the
// mock-profanity-api stub being up).
import ballerina/http;
import ballerina/test;

http:Client testClient = check new ("http://localhost:" + listenPort.toString());

function req(string? token, json body) returns http:Request {
    http:Request r = new;
    if body !is () {
        r.setJsonPayload(body);
    }
    if token is string {
        r.setHeader("Authorization", "Bearer " + token);
    }
    return r;
}

function register(string username, string email, string password) returns [string, int]|error {
    http:Response resp = check testClient->post("/api/v1/auth/register", req((), {username, email, password}));
    test:assertEquals(resp.statusCode, 201);
    AuthResponse auth = check (check resp.getJsonPayload()).cloneWithType(AuthResponse);
    return [auth.token, auth.user.id];
}

// Clean slate before the suite runs — assumes blog.db's tables already
// exist (created from schema.sql per the README setup steps).
@test:BeforeSuite
function setup() returns error? {
    _ = check dbClient->execute(`DELETE FROM comments`);
    _ = check dbClient->execute(`DELETE FROM posts`);
    _ = check dbClient->execute(`DELETE FROM users`);
}

@test:Config {}
function testRegisterValidation() returns error? {
    http:Response resp = check testClient->post("/api/v1/auth/register",
        req((), {username: "ab", email: "a@example.com", password: "password123"}));
    test:assertEquals(resp.statusCode, 400);
    Error err = check (check resp.getJsonPayload()).cloneWithType(Error);
    test:assertEquals(err.'error.code, "validation_failed");

    resp = check testClient->post("/api/v1/auth/register",
        req((), {username: "alice", email: "a@example.com", password: "short"}));
    test:assertEquals(resp.statusCode, 400);

    resp = check testClient->post("/api/v1/auth/register",
        req((), {username: "alice", email: "", password: "password123"}));
    test:assertEquals(resp.statusCode, 400);
}

@test:Config {}
function testRegisterDuplicateEmail() returns error? {
    [string, int] _ = check register("bob", "bob@example.com", "password123");

    http:Response resp = check testClient->post("/api/v1/auth/register",
        req((), {username: "bob2", email: "bob@example.com", password: "password123"}));
    test:assertEquals(resp.statusCode, 409);
}

@test:Config {}
function testLoginFlow() returns error? {
    [string, int] _ = check register("carol", "carol@example.com", "password123");

    http:Response resp = check testClient->post("/api/v1/auth/login",
        req((), {email: "carol@example.com", password: "wrong-password"}));
    test:assertEquals(resp.statusCode, 401);

    resp = check testClient->post("/api/v1/auth/login",
        req((), {email: "carol@example.com", password: "password123"}));
    test:assertEquals(resp.statusCode, 200);
    AuthResponse auth = check (check resp.getJsonPayload()).cloneWithType(AuthResponse);
    test:assertTrue(auth.token.length() > 0);
}

@test:Config {}
function testCreatePostRequiresAuth() returns error? {
    http:Response resp = check testClient->post("/api/v1/posts", req((), {title: "t", body: "b"}));
    test:assertEquals(resp.statusCode, 401);
}

@test:Config {}
function testCreatePostValidation() returns error? {
    [string, int] [token, _] = check register("dave", "dave@example.com", "password123");

    http:Response resp = check testClient->post("/api/v1/posts", req(token, {title: "  ", body: "body"}));
    test:assertEquals(resp.statusCode, 400);

    // Valid post, with the profanity check unreachable — must fail open.
    resp = check testClient->post("/api/v1/posts", req(token, {title: "title", body: "body"}));
    test:assertEquals(resp.statusCode, 201);
}

@test:Config {}
function testPostOwnership() returns error? {
    [string, int] [authorToken, _] = check register("erin", "erin@example.com", "password123");
    [string, int] [otherToken, _] = check register("frank", "frank@example.com", "password123");

    http:Response resp = check testClient->post("/api/v1/posts", req(authorToken, {title: "hello", body: "world"}));
    Post post = check (check resp.getJsonPayload()).cloneWithType(Post);
    string path = string `/api/v1/posts/${post.id}`;

    resp = check testClient->put(path, req(otherToken, {title: "hijacked"}));
    test:assertEquals(resp.statusCode, 403);

    resp = check testClient->delete(path, req(otherToken, ()));
    test:assertEquals(resp.statusCode, 403);

    resp = check testClient->put(path, req(authorToken, {title: "updated"}));
    test:assertEquals(resp.statusCode, 200);
}

@test:Config {}
function testGetPostFanOut() returns error? {
    [string, int] [authorToken, _] = check register("gina", "gina@example.com", "password123");
    [string, int] [commenterToken, _] = check register("hank", "hank@example.com", "password123");

    http:Response resp = check testClient->post("/api/v1/posts", req(authorToken, {title: "hello", body: "world"}));
    Post post = check (check resp.getJsonPayload()).cloneWithType(Post);
    string path = string `/api/v1/posts/${post.id}`;

    resp = check testClient->post(path + "/comments", req(commenterToken, {body: "nice post"}));
    test:assertEquals(resp.statusCode, 201);

    resp = check testClient->get(path);
    test:assertEquals(resp.statusCode, 200);
    PostDetail detail = check (check resp.getJsonPayload()).cloneWithType(PostDetail);
    test:assertEquals(detail.author.username, "gina");
    test:assertEquals(detail.comments.length(), 1);
    test:assertEquals(detail.comments[0].author.username, "hank");
}
