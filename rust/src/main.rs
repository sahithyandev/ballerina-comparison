use blog_rust::{app, config, db, profanity};
use std::sync::{Arc, Mutex};

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt().json().init();

    let cfg = match config::Config::load() {
        Ok(c) => c,
        Err(e) => {
            tracing::error!(err = %e, "config error");
            std::process::exit(1);
        }
    };

    let conn = match db::open(&cfg.db_path) {
        Ok(c) => c,
        Err(e) => {
            tracing::error!(err = %e, "db open failed");
            std::process::exit(1);
        }
    };

    let port = cfg.port.clone();
    let profanity = profanity::Checker::new(cfg.profanity_url.clone(), cfg.profanity_timeout);
    let state = app::AppState { db: Arc::new(Mutex::new(conn)), cfg, profanity };
    let router = axum::Router::new()
        .nest("/api/v1", app::build_router(state))
        .layer(axum::middleware::from_fn(request_logger));

    let listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{port}"))
        .await
        .expect("bind failed");
    tracing::info!(port = %port, "listening");
    axum::serve(listener, router).await.expect("server stopped");
}

async fn request_logger(
    req: axum::extract::Request,
    next: axum::middleware::Next,
) -> axum::response::Response {
    tracing::info!(method = %req.method(), path = %req.uri().path(), "request");
    next.run(req).await
}
