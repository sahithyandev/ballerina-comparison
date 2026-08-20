"""Env-var config (plan.md criterion #9). Missing JWT_SECRET fails startup,
no silent insecure default — mirrors go/internal/config/config.go.
"""
import os
import re
import sys
from dataclasses import dataclass

_UNITS = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1, "m": 60, "h": 3600}


def parse_duration(s: str) -> float:
    """Parse a Go-style duration string ("24h", "2s") into seconds."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(ns|us|ms|s|m|h)", s)
    if not m:
        raise ValueError(f"invalid duration: {s!r}")
    value, unit = m.groups()
    return float(value) * _UNITS[unit]


@dataclass
class Config:
    port: str
    db_path: str
    jwt_secret: str
    jwt_expiry: float
    profanity_url: str
    profanity_timeout: float


def load() -> Config:
    jwt_secret = os.environ.get("JWT_SECRET", "")
    if not jwt_secret:
        print("config error: JWT_SECRET is required", file=sys.stderr)
        sys.exit(1)

    return Config(
        port=os.environ.get("PORT", "8080"),
        db_path=os.environ.get("DB_PATH", "./blog.db"),
        jwt_secret=jwt_secret,
        jwt_expiry=parse_duration(os.environ.get("JWT_EXPIRY", "24h")),
        profanity_url=os.environ.get("PROFANITY_URL", "http://localhost:9090"),
        profanity_timeout=parse_duration(os.environ.get("PROFANITY_TIMEOUT", "2s")),
    )
