"""パスワードハッシュとセッショントークン。標準ライブラリのみで実装する。

依存を増やさないため、hashlib.scrypt (パスワード) と hmac 署名 (トークン) を使う。
外部の認証基盤 (SSO 等) を使う場合は、この層を差し替えれば済むようにしてある。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

#: scrypt のパラメータ。RFC 7914 の interactive 相当。
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
KEY_BYTES = 32


class TokenError(RuntimeError):
    pass


def hash_password(password: str) -> str:
    """`scrypt$N$r$p$salt$key` 形式で返す。"""
    salt = secrets.token_bytes(SALT_BYTES)
    key = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=KEY_BYTES
    )
    return "$".join(
        [
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            _b64(salt),
            _b64(key),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, key_b64 = encoded.split("$")
        if scheme != "scrypt":
            return False
        expected = _unb64(key_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def create_token(*, secret: str, user_id: int, username: str, ttl_seconds: int) -> str:
    """`payload.signature` 形式の署名付きトークン。"""
    payload = {
        "sub": user_id,
        "name": username,
        "exp": int(time.time()) + ttl_seconds,
        "jti": secrets.token_hex(8),
    }
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{body}.{_sign(secret, body)}"


def read_token(*, secret: str, token: str) -> dict:
    """検証して payload を返す。不正・期限切れは TokenError。"""
    try:
        body, signature = token.split(".", 1)
    except ValueError as exc:
        raise TokenError("トークンの形式が不正です") from exc

    if not hmac.compare_digest(_sign(secret, body), signature):
        raise TokenError("トークンの署名が一致しません")

    try:
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError) as exc:
        raise TokenError("トークンを解釈できません") from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise TokenError("トークンの有効期限が切れています")
    return payload


def _sign(secret: str, body: str) -> str:
    return _b64(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
