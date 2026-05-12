from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    DEEPSEEK_API_KEY: str
    NEWSDATA_API_KEY: str
    NEWSAPI_API_KEY: str
    NEWSCATCHER_API_KEY: str
    GNEWS_API_KEY: str = ""
    GUARDIAN_API_KEY: str = ""
    NYTIMES_API_KEY: str = ""

    class Config:
        # Reads from environment variables (set by Docker); falls back to .env if present
        env_file = ".env"
        extra = "ignore"


settings = Settings()
