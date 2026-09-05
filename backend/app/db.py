"""DB接続。SQLite と PostgreSQL の双方を同じコードで扱う。

既定は SQLite (単独利用・お試し向け)。複数人で同時にレビュー記入する場合は
DSC_DATABASE_URL に PostgreSQL を指定する。
SQLite は書き込みが直列化されるため、同時記入では待ちや失敗が起きやすい。
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import BASE_DIR, get_settings

settings = get_settings()


def _resolve_url(raw: str) -> str:
    """相対パスのSQLiteを backend/ 基準の絶対パスにする。"""
    if raw.startswith("sqlite:///./"):
        return "sqlite:///" + str((BASE_DIR / raw.removeprefix("sqlite:///./")).resolve())
    return raw


def build_engine(raw_url: str) -> Engine:
    url = make_url(_resolve_url(raw_url))

    if url.get_backend_name() == "sqlite":
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if url.database in (None, "", ":memory:"):
            kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **kwargs)

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - 接続時フック
            cursor = dbapi_connection.cursor()
            # 同時アクセスでの "database is locked" を減らす
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        return engine

    # PostgreSQL など。接続断を検知して張り直す。
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )


engine = build_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
