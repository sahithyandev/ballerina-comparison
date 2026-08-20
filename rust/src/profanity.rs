// Calls the mock profanity-check stub with a timeout and fails open: any
// error or timeout is treated as "clean" and logged, so a down dependency
// never blocks a user's write (plan.md criterion #6).
use serde::{Deserialize, Serialize};
use std::time::Duration;

#[derive(Clone)]
pub struct Checker {
    url: String,
    timeout: Duration,
    client: reqwest::Client,
}

#[derive(Serialize)]
struct CheckRequest<'a> {
    text: &'a str,
}

#[derive(Deserialize)]
struct CheckResponse {
    clean: bool,
}

impl Checker {
    pub fn new(url: String, timeout: Duration) -> Self {
        Checker {
            url,
            timeout,
            client: reqwest::Client::new(),
        }
    }

    pub async fn is_clean(&self, text: &str) -> bool {
        let resp = self
            .client
            .post(format!("{}/check", self.url))
            .timeout(self.timeout)
            .json(&CheckRequest { text })
            .send()
            .await;

        let resp = match resp {
            Ok(r) => r,
            Err(e) => {
                tracing::warn!(err = %e, "profanity check unreachable, allowing content");
                return true;
            }
        };

        if !resp.status().is_success() {
            tracing::warn!(status = %resp.status(), "profanity check returned non-200, allowing content");
            return true;
        }

        match resp.json::<CheckResponse>().await {
            Ok(body) => body.clean,
            Err(e) => {
                tracing::warn!(err = %e, "profanity check response unreadable, allowing content");
                true
            }
        }
    }
}
