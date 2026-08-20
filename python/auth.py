"""Password hashing and JWT issue/validate (plan.md criterion #4: JWT bearer
auth, HS256, secret+expiry from env). Mirrors go/internal/auth/auth.go.
"""
import time

import bcrypt
import jwt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(hash_: str, password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hash_.encode())
    except ValueError:
        return False


class InvalidToken(Exception):
    pass


def issue_token(secret: str, expiry_seconds: float, user_id: int) -> str:
    now = int(time.time())
    claims = {"user_id": user_id, "iat": now, "exp": now + int(expiry_seconds)}
    return jwt.encode(claims, secret, algorithm="HS256")


def parse_token(secret: str, token: str) -> int:
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise InvalidToken()
    return claims["user_id"]
