from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DSC_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./storage/dsc.db"
    storage_dir: str = "./storage/uploads"
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
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    (BASE_DIR / "storage").mkdir(parents=True, exist_ok=True)
    return s
