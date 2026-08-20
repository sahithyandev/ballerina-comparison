"""Integration suite against a temp SQLite db built from schema.sql, with an
unreachable profanity URL so the fail-open fallback (plan.md criterion #6)
is exercised on every write — same trick as handlers_test.go and the
Ballerina suite.
"""
import os
import pathlib
import sys

import pytest

TESTS_DIR = pathlib.Path(__file__).parent
sys.path.insert(0, str(TESTS_DIR.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    schema = (TESTS_DIR.parent.parent / "schema.sql").read_text()

    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("PROFANITY_URL", "http://127.0.0.1:1")  # nothing listens -> fails open
    monkeypatch.setenv("PROFANITY_TIMEOUT", "200ms")

    for mod in ("main", "config", "store", "auth", "profanity", "models"):
        sys.modules.pop(mod, None)

    import sqlite3
    sqlite3.connect(db_path).executescript(schema)

    import main as main_module
    from fastapi.testclient import TestClient

    with TestClient(main_module.app) as c:
        yield c


def register(client, username="alice", email="alice@example.com", password="password123"):
    return client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": password},
    )


def test_register_validation(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": "ab", "email": "a@b.com", "password": "short"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_failed"


def test_register_and_login(client):
    resp = register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["username"] == "alice"
    assert body["token"]

    resp = client.post(
        "/api/v1/auth/login", json={"email": "alice@example.com", "password": "password123"}
    )
    assert resp.status_code == 200
    assert resp.json()["token"]


def test_register_duplicate(client):
    register(client)
    resp = register(client)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "user_exists"


def test_login_wrong_password(client):
    register(client)
    resp = client.post(
        "/api/v1/auth/login", json={"email": "alice@example.com", "password": "wrong-password"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


def _token(client):
    return register(client).json()["token"]


def test_create_post_requires_auth(client):
    resp = client.post("/api/v1/posts", json={"title": "t", "body": "b"})
    assert resp.status_code == 401


def test_post_crud_and_fanout(client):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/api/v1/posts", json={"title": "Hello", "body": "World", "published": True}, headers=headers
    )
    assert resp.status_code == 201
    post = resp.json()

    resp = client.post(
        f"/api/v1/posts/{post['id']}/comments", json={"body": "nice post"}, headers=headers
    )
    assert resp.status_code == 201

    resp = client.get(f"/api/v1/posts/{post['id']}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["author"]["username"] == "alice"
    assert len(detail["comments"]) == 1
    assert detail["comments"][0]["author"]["username"] == "alice"


def test_post_ownership(client):
    token_a = register(client, "alice", "alice@example.com").json()["token"]
    token_b = register(client, "bob", "bob@example.com").json()["token"]

    post = client.post(
        "/api/v1/posts", json={"title": "t", "body": "b"}, headers={"Authorization": f"Bearer {token_a}"}
    ).json()

    resp = client.put(
        f"/api/v1/posts/{post['id']}",
        json={"title": "hijacked"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


def test_post_not_found(client):
    token = _token(client)
    resp = client.delete("/api/v1/posts/999", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_delete_cascades_comments(client):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    post = client.post("/api/v1/posts", json={"title": "t", "body": "b"}, headers=headers).json()
    client.post(f"/api/v1/posts/{post['id']}/comments", json={"body": "c1"}, headers=headers)

    resp = client.delete(f"/api/v1/posts/{post['id']}", headers=headers)
    assert resp.status_code == 204

    resp = client.get(f"/api/v1/posts/{post['id']}/comments")
    assert resp.status_code == 404


def test_pagination_bounds(client):
    resp = client.get("/api/v1/posts?page=0")
    assert resp.status_code == 400
    resp = client.get("/api/v1/posts?limit=101")
    assert resp.status_code == 400
    resp = client.get("/api/v1/posts?page=1&limit=20")
    assert resp.status_code == 200
    assert resp.json()["page"] == 1


def test_profanity_check_fails_open(client):
    # PROFANITY_URL points at nothing listening -> profanity.is_clean() must
    # return True (fail-open) so the write still succeeds.
    token = _token(client)
    resp = client.post(
        "/api/v1/posts",
        json={"title": "t", "body": "b"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
