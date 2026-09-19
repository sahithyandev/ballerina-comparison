package blog;

import java.time.Duration;

// Config loads settings strictly from env vars (plan.md criterion #9). No
// hardcoded fallback for JWT_SECRET: missing it fails startup, not a silent
// insecure default. Java has no built-in .env loading, so the shell/CI
// exports these at runtime, same as Go, Ballerina, and Rust.
public record Config(
        String port,
        String dbPath,
        String jwtSecret,
        Duration jwtExpiry,
        String profanityUrl,
        Duration profanityTimeout) {

    public static Config load() {
        String jwtSecret = System.getenv("JWT_SECRET");
        if (jwtSecret == null || jwtSecret.isEmpty()) {
            throw new IllegalStateException("JWT_SECRET is required");
        }
        return new Config(
                getenv("PORT", "8080"),
                getenv("DB_PATH", "./blog.db"),
                jwtSecret,
                parseDuration(getenv("JWT_EXPIRY", "24h")),
                getenv("PROFANITY_URL", "http://localhost:9090"),
                parseDuration(getenv("PROFANITY_TIMEOUT", "2s")));
    }

    private static String getenv(String key, String fallback) {
        String v = System.getenv(key);
        return v == null ? fallback : v;
    }

    // Same small hand-rolled parser as config.py/config.js/config.ts/config.rs —
    // java.time.Duration.parse only accepts ISO-8601 ("PT24H"), not the
    // "24h"/"2s"/"200ms" forms the shared .env uses.
    static Duration parseDuration(String s) {
        s = s.trim();
        String unit = s.endsWith("ms") ? "ms" : s.substring(s.length() - 1);
        long n = Long.parseLong(s.substring(0, s.length() - unit.length()).trim());
        return switch (unit) {
            case "ms" -> Duration.ofMillis(n);
            case "s" -> Duration.ofSeconds(n);
            case "m" -> Duration.ofMinutes(n);
            case "h" -> Duration.ofHours(n);
            default -> throw new IllegalArgumentException("invalid duration: " + s);
        };
    }
}
