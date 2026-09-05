"""認証。既定は無効、有効化すると全APIがログイン必須になる。"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.core.security import TokenError, create_token, hash_password, read_token, verify_password
from app.db import Base, get_db
from app.main import app
from tests.test_api import client  # noqa: F401  (認証が無効な既定状態のフィクスチャ)

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "画面設計標準.md"
SECRET = "test-secret-key-do-not-use-in-production"


@pytest.fixture
def auth_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "secret_key", SECRET)
    monkeypatch.setattr(settings, "bootstrap_admin_username", "")
    monkeypatch.setattr(settings, "bootstrap_admin_password", "")
    monkeypatch.setattr(type(settings), "storage_path", property(lambda self: tmp_path))

    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth.db'}", connect_args={"check_same_thread": False}
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _bootstrap(client: TestClient, username: str = "admin", password: str = "correct-horse-1") -> str:
    created = client.post(
        "/api/auth/users",
        json={"username": username, "password": password, "display_name": "管理者"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_admin"] is True

    login = client.post("/api/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    return login.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- パスワードとトークン -----------------------------------------------------


def test_password_hash_is_salted_and_verifiable() -> None:
    a = hash_password("same-password")
    b = hash_password("same-password")
    assert a != b, "ソルトが効いていない"
    assert a.startswith("scrypt$")
    assert "same-password" not in a
    assert verify_password("same-password", a)
    assert not verify_password("wrong-password", a)
    assert not verify_password("same-password", "壊れたハッシュ")


def test_token_roundtrip_and_tampering() -> None:
    token = create_token(secret=SECRET, user_id=7, username="taro", ttl_seconds=60)
    payload = read_token(secret=SECRET, token=token)
    assert payload["sub"] == 7
    assert payload["name"] == "taro"

    with pytest.raises(TokenError, match="署名"):
        read_token(secret="別の鍵", token=token)

    body, signature = token.split(".", 1)
    with pytest.raises(TokenError, match="署名"):
        read_token(secret=SECRET, token=f"{body}x.{signature}")

    with pytest.raises(TokenError):
        read_token(secret=SECRET, token="形式が不正")


def test_expired_token_is_rejected() -> None:
    token = create_token(secret=SECRET, user_id=1, username="x", ttl_seconds=-1)
    time.sleep(0.01)
    with pytest.raises(TokenError, match="有効期限"):
        read_token(secret=SECRET, token=token)


# --- 認証が無効なとき（既定） -------------------------------------------------


def test_disabled_by_default(client: TestClient) -> None:
    status = client.get("/api/auth/status").json()
    assert status["auth_enabled"] is False
    # ログインなしで従来どおり使える
    assert client.get("/api/documents").status_code == 200


# --- 認証が有効なとき ---------------------------------------------------------


def test_status_reports_bootstrap_need(auth_client: TestClient) -> None:
    status = auth_client.get("/api/auth/status").json()
    assert status["auth_enabled"] is True
    assert status["needs_bootstrap"] is True
    assert status["user"] is None


def test_api_requires_login(auth_client: TestClient) -> None:
    for path in ("/api/documents", "/api/review-sets", "/api/meta"):
        response = auth_client.get(path)
        assert response.status_code in (401, 200), path
    assert auth_client.get("/api/documents").status_code == 401
    assert auth_client.get("/api/review-sets").status_code == 401
    # 死活監視は認証なしで通す
    assert auth_client.get("/api/health").status_code == 200


def test_login_and_use_api(auth_client: TestClient) -> None:
    token = _bootstrap(auth_client)

    me = auth_client.get("/api/auth/me", headers=_auth(token))
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    assert me.json()["display_name"] == "管理者"

    assert auth_client.get("/api/documents", headers=_auth(token)).status_code == 200

    status = auth_client.get("/api/auth/status", headers=_auth(token)).json()
    assert status["needs_bootstrap"] is False
    assert status["user"]["username"] == "admin"


def test_wrong_password_is_rejected(auth_client: TestClient) -> None:
    _bootstrap(auth_client)
    response = auth_client.post(
        "/api/auth/login", json={"username": "admin", "password": "まちがい"}
    )
    assert response.status_code == 401
    # 利用者の存在有無を推測させない
    unknown = auth_client.post(
        "/api/auth/login", json={"username": "いない人", "password": "まちがい"}
    )
    assert unknown.status_code == 401
    assert unknown.json()["detail"] == response.json()["detail"]


def test_invalid_token_is_rejected(auth_client: TestClient) -> None:
    _bootstrap(auth_client)
    # HTTPヘッダはASCIIのみなので、偽トークンもASCIIで作る
    assert auth_client.get("/api/documents", headers=_auth("not-a-real-token")).status_code == 401


def test_second_user_requires_admin(auth_client: TestClient) -> None:
    token = _bootstrap(auth_client)

    # 未認証では2人目を作れない
    assert (
        auth_client.post(
            "/api/auth/users", json={"username": "reviewer", "password": "another-pass-1"}
        ).status_code
        == 401
    )

    created = auth_client.post(
        "/api/auth/users",
        json={"username": "reviewer", "password": "another-pass-1", "display_name": "レビュア"},
        headers=_auth(token),
    )
    assert created.status_code == 201
    assert created.json()["is_admin"] is False

    # 管理者でない利用者は追加できない
    reviewer_token = auth_client.post(
        "/api/auth/login", json={"username": "reviewer", "password": "another-pass-1"}
    ).json()["token"]
    assert (
        auth_client.post(
            "/api/auth/users",
            json={"username": "third", "password": "third-pass-12"},
            headers=_auth(reviewer_token),
        ).status_code
        == 403
    )
    assert auth_client.get("/api/auth/users", headers=_auth(reviewer_token)).status_code == 403
    assert auth_client.get("/api/auth/users", headers=_auth(token)).status_code == 200


def test_duplicate_username_is_rejected(auth_client: TestClient) -> None:
    token = _bootstrap(auth_client)
    response = auth_client.post(
        "/api/auth/users",
        json={"username": "admin", "password": "yet-another-1"},
        headers=_auth(token),
    )
    assert response.status_code == 409


def test_short_password_is_rejected(auth_client: TestClient) -> None:
    response = auth_client.post("/api/auth/users", json={"username": "a", "password": "short"})
    assert response.status_code == 422


def test_reviewer_is_filled_from_the_logged_in_user(auth_client: TestClient) -> None:
    """誰が判定したのかを残す。明示入力があればそちらを尊重する。"""
    token = _bootstrap(auth_client)
    headers = _auth(token)

    doc = auth_client.post(
        "/api/documents",
        files={"file": (SAMPLE.name, SAMPLE.read_bytes(), "text/markdown")},
        data={"document_type": "screen", "document_name": "画面設計標準"},
        headers=headers,
    ).json()
    checks = auth_client.get(f"/api/documents/{doc['id']}/checklist", headers=headers).json()

    auto = auth_client.patch(
        f"/api/documents/{doc['id']}/checklist/{checks[0]['id']}",
        json={"result": "OK"},
        headers=headers,
    ).json()
    assert auto["reviewer"] == "管理者"

    explicit = auth_client.patch(
        f"/api/documents/{doc['id']}/checklist/{checks[1]['id']}",
        json={"result": "NG", "reviewer": "代理入力: 佐藤"},
        headers=headers,
    ).json()
    assert explicit["reviewer"] == "代理入力: 佐藤"
