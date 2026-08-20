// Integration suite against a temp SQLite db built from schema.sql, with an
// unreachable profanity URL so the fail-open fallback (plan.md criterion
// #6) is exercised on every write — same trick as the Go/Ballerina/Python/
// Node/Bun suites. One real server shared across all tests in this file,
// started lazily on first use.
use blog_rust::{app, config, profanity};
use rusqlite::Connection;
use serde_json::{json, Value};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::Duration;

static BASE_URL: OnceLock<String> = OnceLock::new();

fn base_url() -> &'static str {
    BASE_URL.get_or_init(|| {
        let (tx, rx) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            let rt = tokio::runtime::Runtime::new().unwrap();
            rt.block_on(async move {
                let mut db_path = std::env::temp_dir();
                db_path.push(format!("blog-rust-test-{}.db", std::process::id()));
                let _ = std::fs::remove_file(&db_path);
                let conn = Connection::open(&db_path).unwrap();
                let schema = std::fs::read_to_string(
                    concat!(env!("CARGO_MANIFEST_DIR"), "/../schema.sql"),
                )
                .unwrap();
                conn.execute_batch(&schema).unwrap();

                let cfg = config::Config {
                    port: "0".into(),
                    db_path: db_path.to_string_lossy().into_owned(),
                    jwt_secret: "test-secret".into(),
                    jwt_expiry: Duration::from_secs(3600),
                    profanity_url: "http://127.0.0.1:1".into(), // nothing listens -> fails open
                    profanity_timeout: Duration::from_millis(200),
                };
                let profanity = profanity::Checker::new(cfg.profanity_url.clone(), cfg.profanity_timeout);
                let state = app::AppState { db: Arc::new(Mutex::new(conn)), cfg, profanity };
                let router = axum::Router::new().nest("/api/v1", app::build_router(state));

                let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
                let port = listener.local_addr().unwrap().port();
                tx.send(port).unwrap();
                axum::serve(listener, router).await.unwrap();
            });
        });
        let port = rx.recv().unwrap();
        format!("http://127.0.0.1:{port}/api/v1")
    })
}

fn client() -> reqwest::blocking::Client {
    reqwest::blocking::Client::new()
}

fn register(username: &str, email: &str) -> Value {
    client()
        .post(format!("{}/auth/register", base_url()))
        .json(&json!({ "username": username, "email": email, "password": "password123" }))
        .send()
        .unwrap()
        .json()
        .unwrap()
}

#[test]
fn register_validation_rejects_short_username_password() {
    let resp = client()
        .post(format!("{}/auth/register", base_url()))
        .json(&json!({ "username": "ab", "email": "short@example.com", "password": "short" }))
        .send()
        .unwrap();
    assert_eq!(resp.status(), 400);
    let body: Value = resp.json().unwrap();
    assert_eq!(body["error"]["code"], "validation_failed");
}

#[test]
fn register_then_login_succeeds() {
    let body = register("alice1", "alice1@example.com");
    assert_eq!(body["user"]["username"], "alice1");
    assert!(body["token"].is_string());

    let login = client()
        .post(format!("{}/auth/login", base_url()))
        .json(&json!({ "email": "alice1@example.com", "password": "password123" }))
        .send()
        .unwrap();
    assert_eq!(login.status(), 200);
}

#[test]
fn duplicate_register_is_rejected() {
    register("dup1", "dup1@example.com");
    let resp = client()
        .post(format!("{}/auth/register", base_url()))
        .json(&json!({ "username": "dup1b", "email": "dup1@example.com", "password": "password123" }))
        .send()
        .unwrap();
    assert_eq!(resp.status(), 409);
    let body: Value = resp.json().unwrap();
    assert_eq!(body["error"]["code"], "user_exists");
}

#[test]
fn login_with_wrong_password_is_rejected() {
    register("wrongpw", "wrongpw@example.com");
    let resp = client()
        .post(format!("{}/auth/login", base_url()))
        .json(&json!({ "email": "wrongpw@example.com", "password": "nope-nope-nope" }))
        .send()
        .unwrap();
    assert_eq!(resp.status(), 401);
    let body: Value = resp.json().unwrap();
    assert_eq!(body["error"]["code"], "invalid_credentials");
}

#[test]
fn creating_a_post_requires_auth() {
    let resp = client()
        .post(format!("{}/posts", base_url()))
        .json(&json!({ "title": "t", "body": "b" }))
        .send()
        .unwrap();
    assert_eq!(resp.status(), 401);
}

#[test]
fn post_crud_and_fan_out() {
    let reg = register("fanout", "fanout@example.com");
    let token = reg["token"].as_str().unwrap();

    let post: Value = client()
        .post(format!("{}/posts", base_url()))
        .bearer_auth(token)
        .json(&json!({ "title": "Hello", "body": "World", "published": true }))
        .send()
        .unwrap()
        .json()
        .unwrap();
    let post_id = post["id"].as_i64().unwrap();

    let comment = client()
        .post(format!("{}/posts/{post_id}/comments", base_url()))
        .bearer_auth(token)
        .json(&json!({ "body": "nice post" }))
        .send()
        .unwrap();
    assert_eq!(comment.status(), 201);

    let detail: Value = client()
        .get(format!("{}/posts/{post_id}", base_url()))
        .send()
        .unwrap()
        .json()
        .unwrap();
    assert_eq!(detail["author"]["username"], "fanout");
    assert_eq!(detail["comments"].as_array().unwrap().len(), 1);
    assert_eq!(detail["comments"][0]["author"]["username"], "fanout");
}

#[test]
fn ownership_check_returns_403_for_non_authors() {
    let a = register("owner", "owner@example.com");
    let b = register("intruder", "intruder@example.com");

    let post: Value = client()
        .post(format!("{}/posts", base_url()))
        .bearer_auth(a["token"].as_str().unwrap())
        .json(&json!({ "title": "t", "body": "b" }))
        .send()
        .unwrap()
        .json()
        .unwrap();

    let resp = client()
        .put(format!("{}/posts/{}", base_url(), post["id"]))
        .bearer_auth(b["token"].as_str().unwrap())
        .json(&json!({ "title": "hijacked" }))
        .send()
        .unwrap();
    assert_eq!(resp.status(), 403);
    let body: Value = resp.json().unwrap();
    assert_eq!(body["error"]["code"], "forbidden");
}

#[test]
fn missing_post_returns_404() {
    let reg = register("notfound", "notfound@example.com");
    let resp = client()
        .delete(format!("{}/posts/999999", base_url()))
        .bearer_auth(reg["token"].as_str().unwrap())
        .send()
        .unwrap();
    assert_eq!(resp.status(), 404);
    let body: Value = resp.json().unwrap();
    assert_eq!(body["error"]["code"], "not_found");
}

#[test]
fn deleting_a_post_cascades_its_comments() {
    let reg = register("cascade", "cascade@example.com");
    let token = reg["token"].as_str().unwrap();

    let post: Value = client()
        .post(format!("{}/posts", base_url()))
        .bearer_auth(token)
        .json(&json!({ "title": "t", "body": "b" }))
        .send()
        .unwrap()
        .json()
        .unwrap();
    let post_id = post["id"].as_i64().unwrap();
    client()
        .post(format!("{}/posts/{post_id}/comments", base_url()))
        .bearer_auth(token)
        .json(&json!({ "body": "c1" }))
        .send()
        .unwrap();

    let del = client()
        .delete(format!("{}/posts/{post_id}", base_url()))
        .bearer_auth(token)
        .send()
        .unwrap();
    assert_eq!(del.status(), 204);

    let comments = client()
        .get(format!("{}/posts/{post_id}/comments", base_url()))
        .send()
        .unwrap();
    assert_eq!(comments.status(), 404);
}

#[test]
fn pagination_bounds_are_enforced() {
    assert_eq!(
        client().get(format!("{}/posts?page=0", base_url())).send().unwrap().status(),
        400
    );
    assert_eq!(
        client().get(format!("{}/posts?limit=101", base_url())).send().unwrap().status(),
        400
    );
    let ok = client()
        .get(format!("{}/posts?page=1&limit=20", base_url()))
        .send()
        .unwrap();
    assert_eq!(ok.status(), 200);
    let body: Value = ok.json().unwrap();
    assert_eq!(body["page"], 1);
}

#[test]
fn profanity_check_fails_open_when_the_stub_is_unreachable() {
    let reg = register("failopen", "failopen@example.com");
    let resp = client()
        .post(format!("{}/posts", base_url()))
        .bearer_auth(reg["token"].as_str().unwrap())
        .json(&json!({ "title": "t", "body": "b" }))
        .send()
        .unwrap();
    assert_eq!(resp.status(), 201);
}
