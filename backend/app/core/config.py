from pydantic import field_validator
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
    jwt_secret: str

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_must_be_set(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("JWT_SECRET must be set in environment or .env file")
        return v
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

    # Tavily (web search)
    tavily_api_key: str = ""
    web_search_max_results: int = 8
    web_search_depth: str = "advanced"
    web_search_synthesis_model: str = "gemini-1.5-flash"

    # Slack
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_app_token: str = ""
    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_oauth_redirect_uri: str = ""
    slack_debug: bool = False

    # Frontend URL (for OAuth callback redirects)
    frontend_url: str = "http://localhost:3000"

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # BART API (default is the public demo key from api.bart.gov)
    bart_api_key: str = "MW9S-E7SL-26DU-VV8V"

    # Embeddings
    embedding_model: str = "BAAI/bge-base-en-v1.5"

    # Memory
    memory_retrieval_limit: int = 5
    memory_similarity_threshold: float = 0.7  # for deduplication

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
