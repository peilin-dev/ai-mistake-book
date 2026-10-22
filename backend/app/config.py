from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "mysql+aiomysql://root:@localhost:3306/cuotiben"
    # 127.0.0.1, not localhost: on Windows localhost may resolve to ::1 first and
    # time out against a Redis that only listens on IPv4.
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    JWT_SECRET: str = "dev-secret-change-me-please-0123456789"
    JWT_EXPIRE_DAYS: int = 7
    WX_APPID: str = ""
    WX_SECRET: str = ""
    STORAGE_DIR: str = "storage"
    PDF_FONT_PATH: str = ""
    DASHSCOPE_API_KEY: str = ""
    ARK_API_KEY: str = ""
    # OpenAI-compatible endpoints. A Bailian workspace key (sk-ws-...) needs the
    # workspace's own domain: https://ws-<id>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ARK_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"

    # "<provider>:<model>", provider is qwen or doubao.
    # qwen-vl-max is not offered in Bailian workspaces any more; qwen3-vl-plus is the vision model.
    MODEL_FOR_GRADING: str = "qwen:qwen3-vl-plus"
    MODEL_FOR_ANSWER_KEY: str = "qwen:qwen3-vl-plus"
    MODEL_FOR_ANALYSIS: str = "qwen:qwen3-vl-plus"
    MODEL_FOR_PRACTICE_GENERATE: str = "qwen:qwen3-vl-plus"
    # Placeholder: the operator must set this to their own Ark model / endpoint id.
    # Must use a different provider than MODEL_FOR_PRACTICE_GENERATE (spec section 8).
    MODEL_FOR_PRACTICE_VERIFY: str = "doubao:doubao-vision"
    MODEL_TIMEOUT_S: float = 120  # waiting for the model's answer
    # Connecting is quick on a good network; fail fast and retry on a flaky one.
    MODEL_CONNECT_TIMEOUT_S: float = 10
    MODEL_CALL_ATTEMPTS: int = 3

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
