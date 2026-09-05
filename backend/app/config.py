from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DSC_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./storage/dsc.db"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    storage_dir: str = "./storage/uploads"

    # --- 認証 ---
    #: True にすると、参照系も含め全APIにログインが必要になる。
    auth_enabled: bool = False
    #: セッショントークンの署名鍵。auth_enabled のとき必須。
    secret_key: str = ""
    #: セッションの有効期間 (秒)。既定12時間。
    session_ttl_seconds: int = 12 * 60 * 60
    #: 起動時に作成する初期管理者。既に存在する場合は何もしない。
    bootstrap_admin_username: str = ""
    bootstrap_admin_password: str = ""
    cors_origins: str = "http://localhost:3000"
    #: 開発時は dev サーバのポートが変わることがあるため localhost 全ポートを許可する。
    #: 本番では空文字にして cors_origins だけで運用する。
    cors_origin_regex: str = r"http://(localhost|127\.0\.0\.1):\d+"

    @property
    def storage_path(self) -> Path:
        p = Path(self.storage_dir)
        if not p.is_absolute():
            p = BASE_DIR / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    (BASE_DIR / "storage").mkdir(parents=True, exist_ok=True)
    return s
