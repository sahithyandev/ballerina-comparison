package blog;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.javalin.Javalin;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;
import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

// Integration suite against a temp SQLite db built from ../schema.sql, with
// an unreachable profanity URL so the fail-open fallback (plan.md criterion
// #6) is exercised on every write — same trick as the Go/Ballerina/Python/
// Node/Bun/Rust suites. One real server for the whole class; `./gradlew
// test` needs no env vars set, same as `cargo test` / `go test ./...`.
class ApiTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final HttpClient HTTP = HttpClient.newHttpClient();
    private static Javalin server;
    private static String baseUrl;

    @BeforeAll
    static void start() throws Exception {
        Path dbPath = Files.createTempFile("blog-java-test-", ".db");
        Files.deleteIfExists(dbPath);
        String schema = Files.readString(Path.of("../schema.sql"))
                .replaceAll("(?m)^\\s*--.*$", "");
        try (Connection c = DriverManager.getConnection("jdbc:sqlite:" + dbPath)) {
            for (String stmt : schema.split(";")) {
                if (!stmt.isBlank()) {
                    try (Statement s = c.createStatement()) {
                        s.execute(stmt.trim());
                    }
                }
            }
        }

        Config cfg = new Config("0", dbPath.toString(), "test-secret", Duration.ofHours(1),
                "http://127.0.0.1:1", Duration.ofMillis(200));
        Store store = new Store(cfg.dbPath());
        Profanity profanity = new Profanity(cfg.profanityUrl(), cfg.profanityTimeout());
        server = App.build(cfg, store, profanity).start(0);
        baseUrl = "http://127.0.0.1:" + server.port() + "/api/v1";
    }

    @AfterAll
    static void stop() {
        if (server != null) {
            server.stop();
        }
    }

    // ---- http helpers ----

    private HttpResponse<String> send(String method, String path, String token, Object jsonBody) throws Exception {
        HttpRequest.BodyPublisher pub = jsonBody == null
                ? HttpRequest.BodyPublishers.noBody()
                : HttpRequest.BodyPublishers.ofString(MAPPER.writeValueAsString(jsonBody));
        HttpRequest.Builder b = HttpRequest.newBuilder(URI.create(baseUrl + path))
                .header("Content-Type", "application/json")
                .method(method, pub);
        if (token != null) {
            b.header("Authorization", "Bearer " + token);
        }
        return HTTP.send(b.build(), HttpResponse.BodyHandlers.ofString());
    }

    private JsonNode json(HttpResponse<String> resp) throws Exception {
        return MAPPER.readTree(resp.body());
    }

    private JsonNode register(String username, String email) throws Exception {
        return json(send("POST", "/auth/register", null,
                java.util.Map.of("username", username, "email", email, "password", "password123")));
    }

    // ---- tests ----

    @Test
    void registerValidationRejectsShortUsernamePassword() throws Exception {
        var resp = send("POST", "/auth/register", null,
                java.util.Map.of("username", "ab", "email", "short@example.com", "password", "short"));
        assertEquals(400, resp.statusCode());
        assertEquals("validation_failed", json(resp).at("/error/code").asText());
    }

    @Test
    void registerThenLoginSucceeds() throws Exception {
        var body = register("alice1", "alice1@example.com");
        assertEquals("alice1", body.at("/user/username").asText());
        assertTrue(body.get("token").isTextual());

        var login = send("POST", "/auth/login", null,
                java.util.Map.of("email", "alice1@example.com", "password", "password123"));
        assertEquals(200, login.statusCode());
    }

    @Test
    void duplicateRegisterIsRejected() throws Exception {
        register("dup1", "dup1@example.com");
        var resp = send("POST", "/auth/register", null,
                java.util.Map.of("username", "dup1b", "email", "dup1@example.com", "password", "password123"));
        assertEquals(409, resp.statusCode());
        assertEquals("user_exists", json(resp).at("/error/code").asText());
    }

    @Test
    void loginWithWrongPasswordIsRejected() throws Exception {
        register("wrongpw", "wrongpw@example.com");
        var resp = send("POST", "/auth/login", null,
                java.util.Map.of("email", "wrongpw@example.com", "password", "nope-nope-nope"));
        assertEquals(401, resp.statusCode());
        assertEquals("invalid_credentials", json(resp).at("/error/code").asText());
    }

    @Test
    void creatingAPostRequiresAuth() throws Exception {
        var resp = send("POST", "/posts", null, java.util.Map.of("title", "t", "body", "b"));
        assertEquals(401, resp.statusCode());
    }

    @Test
    void postCrudAndFanOut() throws Exception {
        String token = register("fanout", "fanout@example.com").get("token").asText();

        var post = json(send("POST", "/posts", token,
                java.util.Map.of("title", "Hello", "body", "World", "published", true)));
        long postId = post.get("id").asLong();

        var comment = send("POST", "/posts/" + postId + "/comments", token, java.util.Map.of("body", "nice post"));
        assertEquals(201, comment.statusCode());

        var detail = json(send("GET", "/posts/" + postId, null, null));
        assertEquals("fanout", detail.at("/author/username").asText());
        assertEquals(1, detail.get("comments").size());
        assertEquals("fanout", detail.at("/comments/0/author/username").asText());
    }

    @Test
    void ownershipCheckReturns403ForNonAuthors() throws Exception {
        String owner = register("owner", "owner@example.com").get("token").asText();
        String intruder = register("intruder", "intruder@example.com").get("token").asText();

        var post = json(send("POST", "/posts", owner, java.util.Map.of("title", "t", "body", "b")));
        var resp = send("PUT", "/posts/" + post.get("id").asLong(), intruder,
                java.util.Map.of("title", "hijacked"));
        assertEquals(403, resp.statusCode());
        assertEquals("forbidden", json(resp).at("/error/code").asText());
    }

    @Test
    void missingPostReturns404() throws Exception {
        String token = register("notfound", "notfound@example.com").get("token").asText();
        var resp = send("DELETE", "/posts/999999", token, null);
        assertEquals(404, resp.statusCode());
        assertEquals("not_found", json(resp).at("/error/code").asText());
    }

    @Test
    void deletingAPostCascadesItsComments() throws Exception {
        String token = register("cascade", "cascade@example.com").get("token").asText();
        var post = json(send("POST", "/posts", token, java.util.Map.of("title", "t", "body", "b")));
        long postId = post.get("id").asLong();
        send("POST", "/posts/" + postId + "/comments", token, java.util.Map.of("body", "c1"));

        var del = send("DELETE", "/posts/" + postId, token, null);
        assertEquals(204, del.statusCode());

        var comments = send("GET", "/posts/" + postId + "/comments", null, null);
        assertEquals(404, comments.statusCode());
    }

    @Test
    void paginationBoundsAreEnforced() throws Exception {
        assertEquals(400, send("GET", "/posts?page=0", null, null).statusCode());
        assertEquals(400, send("GET", "/posts?limit=101", null, null).statusCode());
        var ok = send("GET", "/posts?page=1&limit=20", null, null);
        assertEquals(200, ok.statusCode());
        assertEquals(1, json(ok).get("page").asInt());
    }

    @Test
    void profanityCheckFailsOpenWhenTheStubIsUnreachable() throws Exception {
        String token = register("failopen", "failopen@example.com").get("token").asText();
        var resp = send("POST", "/posts", token, java.util.Map.of("title", "t", "body", "b"));
        assertEquals(201, resp.statusCode());
    }
}
