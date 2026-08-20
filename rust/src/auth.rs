// Password hashing and JWT issue/validate (plan.md criterion #4: JWT bearer
// auth, HS256, secret+expiry from env).
use jsonwebtoken::{decode, encode, DecodingKey, EncodingKey, Header, Validation};
use serde::{Deserialize, Serialize};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub fn hash_password(password: &str) -> Result<String, String> {
    bcrypt::hash(password, bcrypt::DEFAULT_COST).map_err(|e| e.to_string())
}

pub fn check_password(hash: &str, password: &str) -> bool {
    bcrypt::verify(password, hash).unwrap_or(false)
}

#[derive(Serialize, Deserialize)]
struct Claims {
    user_id: i64,
    exp: usize,
    iat: usize,
}

pub fn issue_token(secret: &str, expiry: Duration, user_id: i64) -> Result<String, String> {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| e.to_string())?;
    let claims = Claims {
        user_id,
        iat: now.as_secs() as usize,
        exp: (now + expiry).as_secs() as usize,
    };
    encode(
        &Header::default(),
        &claims,
        &EncodingKey::from_secret(secret.as_bytes()),
    )
    .map_err(|e| e.to_string())
}

pub fn parse_token(secret: &str, token: &str) -> Result<i64, String> {
    decode::<Claims>(
        token,
        &DecodingKey::from_secret(secret.as_bytes()),
        &Validation::default(),
    )
    .map(|data| data.claims.user_id)
    .map_err(|e| e.to_string())
}
