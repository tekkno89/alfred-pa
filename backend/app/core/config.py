from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "Alfred AI Assistant"
    debug: bool = False

    # Database
    database_url: str = "postgresql://alfred:alfred@localhost:5432/alfred"
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379"

    # JWT Authentication
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 30

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # Vertex AI / LLM
    vertex_project_id: str = ""
    vertex_location: str = "us-central1"
    default_llm: str = "gemini-1.5-pro"

    # OpenRouter (for multi-model access)
    openrouter_api_key: str = ""

    # Slack
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_app_token: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
