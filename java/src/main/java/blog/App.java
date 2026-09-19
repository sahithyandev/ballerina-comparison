package blog;

import blog.model.CreateCommentRequest;
import blog.model.CreatePostRequest;
import blog.model.LoginRequest;
import blog.model.RegisterRequest;
import blog.model.UpdatePostRequest;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.javalin.Javalin;
import io.javalin.http.Context;
import io.javalin.json.JavalinJackson;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

// Builds the Javalin app + all endpoint handlers. Mirrors rust/src/app.rs
// 1:1 in behavior (status codes, error codes/messages, validation rules).
// Routes are hand-written; only the request DTOs (blog.model.*) are
// generated from ../openapi.yaml, same commit-the-generated-code split as
// Go's api.gen.go and Ballerina's types.bal.
public final class App {

    private static final Logger log = LoggerFactory.getLogger(App.class);

    private final Config cfg;
    private final Store store;
    private final Profanity profanity;
    private final ObjectMapper mapper = new ObjectMapper();

    // Fan-out pool (plan.md criterion #7): one virtual thread per task. Real
    // threads, not Node/Bun's single JS thread — but every task still
    // serializes behind Store's synchronized single connection, so the DB
    // work is concurrent, not parallel. Same story as Go and Rust; see
    // README.md's concurrency section.
    private final ExecutorService fanout = Executors.newVirtualThreadPerTaskExecutor();

    private App(Config cfg, Store store, Profanity profanity) {
        this.cfg = cfg;
        this.store = store;
        this.profanity = profanity;
    }

    public static Javalin build(Config cfg, Store store, Profanity profanity) {
        App app = new App(cfg, store, profanity);
        Javalin javalin = Javalin.create(c -> {
            c.useVirtualThreads = true;
            c.showJavalinBanner = false;
            c.jsonMapper(new JavalinJackson(app.mapper, false));
        });

        javalin.exception(Http.AppException.class, (e, ctx) ->
                ctx.status(e.status).json(Http.envelope(e.code, e.getMessage())));
        javalin.exception(Exception.class, (e, ctx) -> {
            log.warn("unhandled error", e);
            ctx.status(500).json(Http.envelope("internal_error", "internal error"));
        });
        javalin.before(ctx -> log.info("{} {}", ctx.method(), ctx.path()));

        javalin.post("/api/v1/auth/register", app::register);
        javalin.post("/api/v1/auth/login", app::login);
        javalin.get("/api/v1/posts", app::listPosts);
        javalin.post("/api/v1/posts", app::createPost);
        javalin.get("/api/v1/posts/{id}", app::getPost);
        javalin.put("/api/v1/posts/{id}", app::updatePost);
        javalin.delete("/api/v1/posts/{id}", app::deletePost);
        javalin.get("/api/v1/posts/{id}/comments", app::listComments);
        javalin.post("/api/v1/posts/{id}/comments", app::createComment);
        return javalin;
    }

    // ---- helpers ----

    private <T> T body(Context ctx, Class<T> cls) {
        try {
            return mapper.readValue(ctx.body(), cls);
        } catch (Exception e) {
            throw Http.badRequest("invalid_body", "request body is not valid JSON");
        }
    }

    private long requireAuth(Context ctx) {
        String h = ctx.header("Authorization");
        if (h == null || !h.startsWith("Bearer ")) {
            throw Http.unauthorized("unauthorized", "missing bearer token");
        }
        try {
            return Auth.parseToken(cfg.jwtSecret(), h.substring("Bearer ".length()));
        } catch (Exception e) {
            throw Http.unauthorized("unauthorized", "invalid or expired token");
        }
    }

    private long pathId(Context ctx) {
        try {
            return Long.parseLong(ctx.pathParam("id"));
        } catch (NumberFormatException e) {
            throw Http.notFound("not_found", "post not found");
        }
    }

    private Store.Post postOr404(long id) {
        try {
            return store.getPost(id);
        } catch (Store.NotFoundException e) {
            throw Http.notFound("not_found", "post not found");
        }
    }

    private int intParam(Context ctx, String name, int fallback) {
        String v = ctx.queryParam(name);
        if (v == null || v.isEmpty()) {
            return fallback;
        }
        try {
            return Integer.parseInt(v);
        } catch (NumberFormatException e) {
            throw Http.badRequest("validation_failed", "page must be >=1, limit must be 1-100");
        }
    }

    private static String s(String v) {
        return v == null ? "" : v;
    }

    private static <T> T await(Future<T> f) {
        try {
            return f.get();
        } catch (ExecutionException e) {
            if (e.getCause() instanceof RuntimeException re) {
                throw re;
            }
            throw new RuntimeException(e.getCause());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException(e);
        }
    }

    private Map<String, Object> userOut(Store.User u) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", u.id());
        m.put("username", u.username());
        m.put("email", u.email());
        m.put("created_at", u.createdAt());
        return m;
    }

    private Map<String, Object> postOut(Store.Post p) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", p.id());
        m.put("author_id", p.authorId());
        m.put("title", p.title());
        m.put("body", p.body());
        m.put("published", p.published());
        m.put("created_at", p.createdAt());
        return m;
    }

    private Map<String, Object> commentOut(Store.Comment c) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", c.id());
        m.put("post_id", c.postId());
        m.put("author_id", c.authorId());
        m.put("body", c.body());
        m.put("created_at", c.createdAt());
        return m;
    }

    // Fetches each comment's author concurrently on the fan-out pool.
    private List<Map<String, Object>> attachAuthors(List<Store.Comment> comments) {
        List<Future<Map<String, Object>>> futures = new ArrayList<>();
        for (Store.Comment c : comments) {
            futures.add(fanout.submit(() -> {
                Map<String, Object> m = commentOut(c);
                m.put("author", userOut(store.getUserById(c.authorId())));
                return m;
            }));
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (Future<Map<String, Object>> f : futures) {
            out.add(await(f));
        }
        return out;
    }

    private void ensureClean(String text) {
        if (!profanity.isClean(text)) {
            throw Http.badRequest("validation_failed", "content contains profanity");
        }
    }

    // ---- POST /auth/register ----

    private void register(Context ctx) {
        RegisterRequest req = body(ctx, RegisterRequest.class);
        if (s(req.getUsername()).length() < 3 || s(req.getPassword()).length() < 8 || s(req.getEmail()).isEmpty()) {
            throw Http.badRequest("validation_failed",
                    "username (>=3 chars), password (>=8 chars) and email are required");
        }

        String hash = Auth.hashPassword(req.getPassword());
        Store.User user;
        try {
            user = store.createUser(req.getUsername(), req.getEmail(), hash);
        } catch (Exception e) {
            throw Http.conflict("user_exists", "username or email already registered");
        }

        String token = Auth.issueToken(cfg.jwtSecret(), cfg.jwtExpiry(), user.id());
        ctx.status(201).json(Map.of("token", token, "user", userOut(user)));
    }

    // ---- POST /auth/login ----

    private void login(Context ctx) {
        LoginRequest req = body(ctx, LoginRequest.class);
        Store.User user = store.findUserByEmail(s(req.getEmail()))
                .filter(u -> Auth.checkPassword(u.passwordHash(), s(req.getPassword())))
                .orElseThrow(() -> Http.unauthorized("invalid_credentials", "email or password is incorrect"));

        String token = Auth.issueToken(cfg.jwtSecret(), cfg.jwtExpiry(), user.id());
        ctx.status(200).json(Map.of("token", token, "user", userOut(user)));
    }

    // ---- GET /posts ----

    private void listPosts(Context ctx) {
        int page = intParam(ctx, "page", 1);
        int limit = intParam(ctx, "limit", 20);
        if (page < 1 || limit < 1 || limit > 100) {
            throw Http.badRequest("validation_failed", "page must be >=1, limit must be 1-100");
        }
        String pubParam = ctx.queryParam("published");
        Boolean published = pubParam == null ? null : Boolean.parseBoolean(pubParam);

        Store.PostPage result = store.listPosts(published, limit, (page - 1) * limit);
        List<Map<String, Object>> posts = new ArrayList<>();
        for (Store.Post p : result.posts()) {
            posts.add(postOut(p));
        }
        ctx.status(200).json(Map.of("posts", posts, "page", page, "limit", limit, "total", result.total()));
    }

    // ---- POST /posts ----

    private void createPost(Context ctx) {
        long uid = requireAuth(ctx);
        CreatePostRequest req = body(ctx, CreatePostRequest.class);
        if (s(req.getTitle()).trim().isEmpty() || s(req.getBody()).trim().isEmpty()) {
            throw Http.badRequest("validation_failed", "title and body are required");
        }
        ensureClean(req.getTitle() + " " + req.getBody());

        boolean published = Boolean.TRUE.equals(req.getPublished());
        Store.Post post = store.createPost(uid, req.getTitle(), req.getBody(), published);
        ctx.status(201).json(postOut(post));
    }

    // ---- PUT /posts/{id} ----

    private void updatePost(Context ctx) {
        long uid = requireAuth(ctx);
        Store.Post post = postOr404(pathId(ctx));
        if (post.authorId() != uid) {
            throw Http.forbidden("forbidden", "only the author can modify this post");
        }

        UpdatePostRequest req = body(ctx, UpdatePostRequest.class);
        if (req.getTitle() != null && req.getTitle().trim().isEmpty()) {
            throw Http.badRequest("validation_failed", "title cannot be empty");
        }
        if (req.getBody() != null && req.getBody().trim().isEmpty()) {
            throw Http.badRequest("validation_failed", "body cannot be empty");
        }

        String checkTitle = req.getTitle() != null ? req.getTitle() : post.title();
        String checkBody = req.getBody() != null ? req.getBody() : post.body();
        ensureClean(checkTitle + " " + checkBody);

        Store.Post updated = store.updatePost(post.id(), req.getTitle(), req.getBody(), req.getPublished());
        ctx.status(200).json(postOut(updated));
    }

    // ---- DELETE /posts/{id} ----

    private void deletePost(Context ctx) {
        long uid = requireAuth(ctx);
        Store.Post post = postOr404(pathId(ctx));
        if (post.authorId() != uid) {
            throw Http.forbidden("forbidden", "only the author can delete this post");
        }
        store.deletePost(post.id());
        ctx.status(204);
    }

    // ---- GET /posts/{id}/comments ----

    private void listComments(Context ctx) {
        long postId = postOr404(pathId(ctx)).id();
        int page = intParam(ctx, "page", 1);
        int limit = intParam(ctx, "limit", 20);
        if (page < 1 || limit < 1 || limit > 100) {
            throw Http.badRequest("validation_failed", "page must be >=1, limit must be 1-100");
        }

        Store.CommentPage result = store.listCommentsPage(postId, limit, (page - 1) * limit);
        ctx.status(200).json(Map.of(
                "comments", attachAuthors(result.comments()),
                "page", page, "limit", limit, "total", result.total()));
    }

    // ---- POST /posts/{id}/comments ----

    private void createComment(Context ctx) {
        long uid = requireAuth(ctx);
        long postId = postOr404(pathId(ctx)).id();

        CreateCommentRequest req = body(ctx, CreateCommentRequest.class);
        if (s(req.getBody()).trim().isEmpty()) {
            throw Http.badRequest("validation_failed", "body is required");
        }
        ensureClean(req.getBody());

        Store.Comment comment = store.createComment(postId, uid, req.getBody());
        ctx.status(201).json(commentOut(comment));
    }

    // ---- GET /posts/{id} ----
    //
    // Fan-out join point (plan.md criterion #7): author and comments load
    // concurrently on the virtual-thread pool, then each comment's author.

    private void getPost(Context ctx) {
        Store.Post post = postOr404(pathId(ctx));

        Future<Store.User> authorF = fanout.submit(() -> store.getUserById(post.authorId()));
        Future<List<Store.Comment>> commentsF = fanout.submit(() -> store.listCommentsByPost(post.id()));
        Store.User author = await(authorF);
        List<Map<String, Object>> comments = attachAuthors(await(commentsF));

        Map<String, Object> out = postOut(post);
        out.put("author", userOut(author));
        out.put("comments", comments);
        ctx.status(200).json(out);
    }
}
