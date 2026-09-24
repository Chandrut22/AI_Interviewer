from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    DOUBT_THRESHOLD: int = 4
    MAX_VIOLATIONS: int = 3
    MIN_TOPIC_SECONDS: int = 150
    MAX_EXTENSION_SECONDS: int = 60
    MAX_TOPIC_EXTENSION_SECONDS: int = 120

    MAX_FOLLOWUPS_PER_TOPIC: int = 2
    MAX_CLARIFICATIONS_PER_TOPIC: int = 1

    HISTORY_MESSAGES: int = 4

    DEFAULT_QUESTION_SECONDS: int = 120
    MIN_QUESTION_SECONDS: int = 45

    PLAN_FIX_ATTEMPTS: int = 2
    TOPICS_COVER_SUGGESTION: str = None

    SENIORITY_BASELINE: dict[str, int] = {}


settings = Settings()