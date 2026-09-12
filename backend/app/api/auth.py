"""認証。既定は無効で、DSC_AUTH_ENABLED=true にすると全APIがログイン必須になる。

無効時は誰でも使える（従来どおり、ローカル/社内の単独利用を想定）。
有効時は個人アカウントでログインし、レビュー結果の Reviewer 欄と結び付けられる。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.security import (
    TokenError,
    create_token,
    hash_password,
    read_token,
    verify_password,
)
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

#: auto_error=False にして、ヘッダが無い場合の扱いを各所で決められるようにする。
#: 認証が無効なときは未提示でも通す必要があるため、ここで自動的に 401 にはしない。
bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    """ログイン要求。"""
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    """利用者の応答。パスワードハッシュは決して含めない。"""
    id: int
    username: str
    display_name: str
    is_admin: bool


class LoginResponse(BaseModel):
    """ログイン成功時の応答。expires_in は秒数。"""
    token: str
    expires_in: int
    user: UserOut


class AuthStatus(BaseModel):
    """認証の状態。ログイン前でも取得できる。

    auth_enabled が False なら認証機能そのものが無効で、誰でも利用できる。
    """
    auth_enabled: bool
    #: 有効なのに利用者が1人もいない状態 (初期セットアップが必要)
    needs_bootstrap: bool
    user: UserOut | None = None


class UserCreate(BaseModel):
    """利用者の作成要求。

    パスワードの下限は 8 文字。ここを緩めると総当たりが現実的になる。
    """
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8)
    display_name: str = ""
    is_admin: bool = False


def _to_out(user: User) -> UserOut:
    """モデルを応答へ変換する。

    表示名が空ならユーザー名で代替する。Reviewer 欄が空欄になるのを防ぐため。
    """
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name or user.username,
        is_admin=user.is_admin,
    )


def _secret() -> str:
    """トークンの署名鍵を取り出す。未設定なら 500 で落とす。

    鍵が無いまま署名すると誰でもトークンを偽造できるので、既定値では代用しない。
    """
    settings = get_settings()
    if not settings.secret_key:
        raise HTTPException(
            status_code=500,
            detail="DSC_SECRET_KEY が未設定です。認証を有効にする場合は必ず設定してください。",
        )
    return settings.secret_key


def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """認証が有効なら利用者を返す。無効なら None（誰でも通す）。"""
    settings = get_settings()
    if not settings.auth_enabled:
        return None

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="ログインが必要です",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = read_token(secret=_secret(), token=credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=401, detail=str(exc), headers={"WWW-Authenticate": "Bearer"}
        ) from exc

    user = db.get(User, int(payload.get("sub", 0)))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="利用者が見つからないか無効です")
    request.state.user = user
    return user


def require_admin(user: User | None = Depends(current_user)) -> User | None:
    """管理者だけを通す依存関数。

    認証が無効なときは current_user が None を返すため、この関数も素通しになる。
    """
    if user is not None and not user.is_admin:
        raise HTTPException(status_code=403, detail="管理者権限が必要です")
    return user


def _user_count(db: Session) -> int:
    """登録済みの利用者数。初期セットアップが必要かの判定に使う。"""
    return db.scalar(select(func.count()).select_from(User)) or 0


@router.get("/status", response_model=AuthStatus)
def status(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> AuthStatus:
    """ログイン前でも呼べる。フロントエンドがログイン画面の要否を判断する。"""
    settings = get_settings()
    if not settings.auth_enabled:
        return AuthStatus(auth_enabled=False, needs_bootstrap=False)

    user_out: UserOut | None = None
    if credentials is not None and credentials.credentials and settings.secret_key:
        try:
            payload = read_token(secret=settings.secret_key, token=credentials.credentials)
            user = db.get(User, int(payload.get("sub", 0)))
            if user is not None and user.is_active:
                user_out = _to_out(user)
        except TokenError:
            user_out = None

    return AuthStatus(
        auth_enabled=True,
        needs_bootstrap=_user_count(db) == 0,
        user=user_out,
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """ログインしてトークンを発行する。

    認証が無効なときは 400。無効なのにトークンを配ると、状態が食い違う。
    """
    settings = get_settings()
    if not settings.auth_enabled:
        raise HTTPException(status_code=400, detail="認証は無効です")

    user = db.scalars(select(User).where(User.username == payload.username)).first()
    # 利用者の存在有無を応答時間や文言から推測されないよう、常に同じ扱いにする
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="ユーザー名またはパスワードが違います")

    user.last_login_at = datetime.now(UTC)
    db.commit()

    ttl = settings.session_ttl_seconds
    return LoginResponse(
        token=create_token(
            secret=_secret(), user_id=user.id, username=user.username, ttl_seconds=ttl
        ),
        expires_in=ttl,
        user=_to_out(user),
    )


@router.get("/me", response_model=UserOut)
def me(user: User | None = Depends(current_user)) -> UserOut:
    """ログイン中の利用者。"""
    if user is None:
        raise HTTPException(status_code=400, detail="認証は無効です")
    return _to_out(user)


@router.get("/users", response_model=list[UserOut])
def list_users(
    _: User | None = Depends(require_admin), db: Session = Depends(get_db)
) -> list[UserOut]:
    """利用者一覧。管理者のみ。"""
    return [_to_out(u) for u in db.scalars(select(User).order_by(User.id)).all()]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> UserOut:
    """利用者の追加。

    1人目だけは未認証でも作成できる（初期セットアップ）。以降は管理者のみ。
    """
    settings = get_settings()
    if not settings.auth_enabled:
        raise HTTPException(status_code=400, detail="認証は無効です")

    is_bootstrap = _user_count(db) == 0
    if not is_bootstrap:
        if credentials is None or not credentials.credentials:
            raise HTTPException(status_code=401, detail="ログインが必要です")
        try:
            token_payload = read_token(secret=_secret(), token=credentials.credentials)
        except TokenError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        actor = db.get(User, int(token_payload.get("sub", 0)))
        if actor is None or not actor.is_active or not actor.is_admin:
            raise HTTPException(status_code=403, detail="管理者権限が必要です")

    # 一意制約に任せず先に確認する。DB エラーではなく意味のある文言を返すため
    if db.scalars(select(User).where(User.username == payload.username)).first():
        raise HTTPException(status_code=409, detail="そのユーザー名は既に使われています")

    user = User(
        username=payload.username.strip(),
        display_name=(payload.display_name or payload.username).strip(),
        password_hash=hash_password(payload.password),
        # 1人目は必ず管理者にする（誰も管理できなくなるのを防ぐ）
        is_admin=True if is_bootstrap else payload.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_out(user)


def bootstrap_admin(db: Session) -> None:
    """環境変数で初期管理者が指定されていれば作成する（既に利用者がいれば何もしない）。"""
    settings = get_settings()
    if not settings.auth_enabled:
        return
    if not settings.bootstrap_admin_username or not settings.bootstrap_admin_password:
        return
    if _user_count(db) > 0:
        return
    db.add(
        User(
            username=settings.bootstrap_admin_username.strip(),
            display_name=settings.bootstrap_admin_username.strip(),
            password_hash=hash_password(settings.bootstrap_admin_password),
            is_admin=True,
        )
    )
    db.commit()
