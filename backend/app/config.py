from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "mysql+aiomysql://root:@localhost:3306/cuotiben"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_EXPIRE_DAYS: int = 7
    WX_APPID: str = ""
    WX_SECRET: str = ""
    STORAGE_DIR: str = "storage"
    DASHSCOPE_API_KEY: str = ""
    ARK_API_KEY: str = ""

    REVIEW_CONFIDENCE_THRESHOLD: float = 0.8
    NAME_MATCH_THRESHOLD: float = 0.8
    MONTHLY_PAGE_QUOTA: int = 300
    ORIGINAL_RETENTION_DAYS: int = 30

    # model name -> (input fen per 1k tokens, output fen per 1k tokens)
    PRICE_FEN_PER_1K: dict[str, tuple[float, float]] = {}


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def set_settings(value: Settings | None) -> None:
    """Override (or reset with None) the process-wide settings; used by tests."""
    global _settings
    _settings = value
