// Tiny response helpers shared by handlers: consistent JSON error envelope
// on every error response (plan.md criterion #5), no stack traces leaking.
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::json;

pub struct AppError {
    pub status: StatusCode,
    pub code: &'static str,
    pub message: &'static str,
}

impl AppError {
    pub fn new(status: StatusCode, code: &'static str, message: &'static str) -> Self {
        AppError { status, code, message }
    }
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        (
            self.status,
            Json(json!({ "error": { "code": self.code, "message": self.message } })),
        )
            .into_response()
    }
}

pub fn unauthorized(code: &'static str, message: &'static str) -> AppError {
    AppError::new(StatusCode::UNAUTHORIZED, code, message)
}

pub fn bad_request(code: &'static str, message: &'static str) -> AppError {
    AppError::new(StatusCode::BAD_REQUEST, code, message)
}

pub fn forbidden(code: &'static str, message: &'static str) -> AppError {
    AppError::new(StatusCode::FORBIDDEN, code, message)
}

pub fn not_found(code: &'static str, message: &'static str) -> AppError {
    AppError::new(StatusCode::NOT_FOUND, code, message)
}

pub fn conflict(code: &'static str, message: &'static str) -> AppError {
    AppError::new(StatusCode::CONFLICT, code, message)
}

pub fn internal(code: &'static str, message: &'static str) -> AppError {
    AppError::new(StatusCode::INTERNAL_SERVER_ERROR, code, message)
}
