import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
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
    # --- 変換補助 (STEP 7) ---
    #: True にすると、ルールベースが分解できなかった並列表現だけ Claude に区切りを尋ねる。
    #: 原文の部分文字列以外は採用しないため、標準書に無い語がチェック項目に混ざることはない。
    #: ANTHROPIC_API_KEY と anthropic SDK が無ければ、True でもルールベースのまま動く。
    llm_split_enabled: bool = False
    #: 応答のキャッシュ。同じ標準書を再解析してもチェック項目がずれないようにする。
    llm_split_cache: str = "./storage/llm-split-cache.json"

    #: STEP 5 補助: 規範表現を持たない行が規定か記述例かを Claude に判定させる。
    #: 答えさせるのは可否・規範レベル・原文中の根拠だけで、文言は生成させない。
    #: ANTHROPIC_API_KEY と anthropic SDK が無ければ、True でもルールベースのまま動く。
    llm_classify_enabled: bool = False
    #: 応答のキャッシュ。同じ標準書を再解析してもチェック項目がずれないようにする。
    llm_classify_cache: str = "./storage/llm-classify-cache.json"

    #: Claude API の資格情報。DSC_ 接頭辞を付けない名前で受ける (SDK の慣習に合わせる)。
    #:
    #: 設定として持つのは、.env に書いた値を効かせるため。anthropic SDK も
    #: claude_available() も os.environ しか見ないが、pydantic-settings が .env を
    #: 読んでも os.environ には入らない。Docker では compose が環境変数として渡すため
    #: 気付きにくいが、ローカル起動では .env に書いても補助が無効のままになっていた。
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")

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
    def llm_split_cache_path(self) -> Path | None:
        p = Path(self.llm_split_cache)
        if not p.is_absolute():
            p = BASE_DIR / p
        return p

    @property
    def llm_classify_cache_path(self) -> Path | None:
        p = Path(self.llm_classify_cache)
        if not p.is_absolute():
            p = BASE_DIR / p
        return p

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """設定を1度だけ読む。

    .env から読んだ Claude の資格情報は os.environ へ渡す。SDK も
    llm_split / llm_classify の claude_available() も os.environ しか見ないため、
    ここで橋渡ししないと .env に書いた値が効かない。
    既に環境変数がある場合は、そちらを優先して上書きしない。
    """
    settings = Settings()
    if settings.anthropic_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
    return settings
