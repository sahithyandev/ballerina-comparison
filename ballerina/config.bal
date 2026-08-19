// Config loaded strictly from env vars (plan.md criterion #9), mirroring
// go/internal/config: no hardcoded fallback for JWT_SECRET, fail fast if unset.
import ballerina/os;

function getenv(string key, string fallback) returns string {
    string val = os:getEnv(key);
    return val == "" ? fallback : val;
}

function requireEnv(string key) returns string|error {
    string val = os:getEnv(key);
    if val == "" {
        return error(key + " is required");
    }
    return val;
}

// .env uses Go-style durations ("2s", "24h", "300ms") so the same file works
// unmodified for both stacks; convert to seconds for Ballerina's decimal APIs.
function toSeconds(string duration) returns decimal|error {
    if duration.endsWith("ms") {
        return (check decimal:fromString(duration.substring(0, duration.length() - 2))) / 1000;
    }
    if duration.endsWith("h") {
        return (check decimal:fromString(duration.substring(0, duration.length() - 1))) * 3600;
    }
    if duration.endsWith("m") {
        return (check decimal:fromString(duration.substring(0, duration.length() - 1))) * 60;
    }
    if duration.endsWith("s") {
        return check decimal:fromString(duration.substring(0, duration.length() - 1));
    }
    return check decimal:fromString(duration);
}

final string dbPath = getenv("DB_PATH", "./blog.db");
final string jwtSecret = check requireEnv("JWT_SECRET");
final decimal jwtExpirySeconds = check toSeconds(getenv("JWT_EXPIRY", "24h"));
final int listenPort = check int:fromString(getenv("PORT", "8080"));
final string profanityUrl = getenv("PROFANITY_URL", "http://localhost:9090");
final decimal profanityTimeoutSeconds = check toSeconds(getenv("PROFANITY_TIMEOUT", "2s"));
