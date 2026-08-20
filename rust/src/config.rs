// Config loads settings strictly from env vars (plan.md criterion #9). No
// hardcoded fallback for JWT_SECRET: missing it fails startup, not a silent
// insecure default.
use std::time::Duration;

#[derive(Clone)]
pub struct Config {
    pub port: String,
    pub db_path: String,
    pub jwt_secret: String,
    pub jwt_expiry: Duration,
    pub profanity_url: String,
    pub profanity_timeout: Duration,
}

impl Config {
    pub fn load() -> Result<Config, String> {
        let jwt_secret = std::env::var("JWT_SECRET")
            .map_err(|_| "JWT_SECRET is required".to_string())?;
        if jwt_secret.is_empty() {
            return Err("JWT_SECRET is required".to_string());
        }

        Ok(Config {
            port: getenv("PORT", "8080"),
            db_path: getenv("DB_PATH", "./blog.db"),
            jwt_secret,
            jwt_expiry: parse_duration(&getenv("JWT_EXPIRY", "24h"))?,
            profanity_url: getenv("PROFANITY_URL", "http://localhost:9090"),
            profanity_timeout: parse_duration(&getenv("PROFANITY_TIMEOUT", "2s"))?,
        })
    }
}

fn getenv(key: &str, fallback: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| fallback.to_string())
}

// Same small hand-rolled parser as config.js/config.py/config.ts — Rust's
// stdlib has no duration-string parser either, unlike Go's time.ParseDuration.
fn parse_duration(s: &str) -> Result<Duration, String> {
    let s = s.trim();
    let (num, unit) = s.split_at(s.len() - if s.ends_with("ms") { 2 } else { 1 });
    let n: u64 = num
        .parse()
        .map_err(|_| format!("invalid duration: {s}"))?;
    let d = match unit {
        "ms" => Duration::from_millis(n),
        "s" => Duration::from_secs(n),
        "m" => Duration::from_secs(n * 60),
        "h" => Duration::from_secs(n * 3600),
        _ => return Err(format!("invalid duration: {s}")),
    };
    Ok(d)
}
