-- Deterministic fixture data, identical for both stacks.
-- Both users' password is "password123" (bcrypt hash below).
-- Fixed ids so loadtest.sh and the step-3 curl gate can hardcode targets.

INSERT INTO users (id, username, email, password_hash) VALUES
    (1, 'alice', 'alice@example.com', '$2a$10$h2/S2r26vMHW3qjCutd5eO7sjB/zVGxuXrH5gRQzhnDmvktJjcm/m'),
    (2, 'bob',   'bob@example.com',   '$2a$10$h2/S2r26vMHW3qjCutd5eO7sjB/zVGxuXrH5gRQzhnDmvktJjcm/m');

-- Post id 1 is the fan-out load-test target: published, has comments from both users.
INSERT INTO posts (id, author_id, title, body, published) VALUES
    (1, 1, 'Welcome to the blog', 'This is the first post, used as the load-test fan-out target.', 1);

INSERT INTO comments (post_id, author_id, body) VALUES
    (1, 2, 'Great first post!'),
    (1, 1, 'Thanks, Bob.'),
    (1, 2, 'Looking forward to more.'),
    (1, 1, 'More is coming soon.'),
    (1, 2, 'Nice.'),
    (1, 1, 'Appreciate it.'),
    (1, 2, 'One more comment.'),
    (1, 1, 'And a reply.'),
    (1, 2, 'Almost done seeding.'),
    (1, 1, 'Last one.');

-- Remaining posts: bulk filler for pagination testing (id 2..50), alternating
-- published/unpublished, alternating author.
INSERT INTO posts (author_id, title, body, published)
SELECT
    CASE WHEN n % 2 = 0 THEN 1 ELSE 2 END,
    'Post number ' || n,
    'Body text for seeded post number ' || n || '.',
    n % 3 != 0
FROM (
    WITH RECURSIVE seq(n) AS (
        SELECT 2
        UNION ALL
        SELECT n + 1 FROM seq WHERE n < 50
    )
    SELECT n FROM seq
);
