from pydantic import field_validator, model_validator
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
    web_search_synthesis_model: str = "gemini-2.5-flash-lite"

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

    # Encryption (envelope encryption for token storage)
    encryption_kek_provider: str = "local"  # "local" | "gcp_kms" | "aws_kms"
    encryption_kek_local_key: str = ""  # base64-encoded Fernet key
    encryption_kek_local_key_file: str = ""  # alternative: path to key file
    encryption_gcp_kms_key_name: str = ""
    encryption_aws_kms_key_id: str = ""

    @model_validator(mode="after")
    def validate_encryption_config(self) -> "Settings":
        provider = self.encryption_kek_provider
        if provider == "local":
            if (
                not self.encryption_kek_local_key
                and not self.encryption_kek_local_key_file
            ):
                raise ValueError(
                    "ENCRYPTION_KEK_LOCAL_KEY or ENCRYPTION_KEK_LOCAL_KEY_FILE must be set "
                    "when using the 'local' encryption provider. "
                    'Generate a key with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
                )
        elif provider == "gcp_kms":
            if not self.encryption_gcp_kms_key_name:
                raise ValueError(
                    "ENCRYPTION_GCP_KMS_KEY_NAME must be set when using the 'gcp_kms' encryption provider."
                )
        elif provider == "aws_kms":
            if not self.encryption_aws_kms_key_id:
                raise ValueError(
                    "ENCRYPTION_AWS_KMS_KEY_ID must be set when using the 'aws_kms' encryption provider."
                )
        return self

    # GitHub App
    github_app_id: str = ""
    github_app_private_key: str = ""
    github_app_private_key_file: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    github_webhook_secret: str = ""
    github_oauth_redirect_uri: str = ""

    # Google Calendar
    google_calendar_oauth_redirect_uri: str = ""
    google_calendar_webhook_url: str = ""  # Public URL for push notifications

    # Triage
    triage_classification_model: str = "gemini-2.5-flash"
    triage_vertex_location: str = (
        ""  # override VERTEX_LOCATION for triage (e.g. "us-central1")
    )

    # Sandbox orchestrator (for docker_sandbox runtime)
    sandbox_url: str = "http://alfred-sandbox:8080"
    sandbox_api_key: str = ""
    claude_code_image: str = "alfred-claude-code:latest"
    sandbox_docker_network: str = (
        ""  # Docker network for containers (e.g. "alfred-pa_default")
    )

    # Coding assistant — runtime
    coding_runtime_provider: str = (
        "docker_sandbox"  # "docker_sandbox" | "kubernetes" | "cloudrun"
    )
    coding_job_timeout_minutes: int = 30
    coding_sensitive_paths: str = ".github/workflows,Dockerfile,docker-compose,.env"
    coding_max_concurrent_jobs: int = 2  # Per user
    coding_slack_channel: str = ""  # Channel for web-initiated coding job threads

    # Coding assistant — completion reporting
    coding_completion_method: str = "callback"  # "callback" | "redis" | "gcp_pubsub"
    coding_callback_base_url: str = ""  # e.g. "http://backend:8000"

    # Coding assistant — event bus (for redis/gcp_pubsub completion + general events)
    coding_event_bus_provider: str = "redis"  # "redis" | "gcp_pubsub" | "kafka"
    coding_gcp_pubsub_project: str = ""
    coding_gcp_pubsub_topic_prefix: str = "alfred-events"

    # Claude Code LLM provider: "vertex" (Vertex AI) or "api" (direct Anthropic API)
    claude_code_provider: str = "vertex"

    # Direct Anthropic API (when claude_code_provider = "api")
    claude_code_api_key: str = ""

    # Vertex AI for Claude Code (when claude_code_provider = "vertex")
    claude_code_vertex_project: str = ""
    claude_code_vertex_region: str = "us-east5"

    # GCP credentials for Claude Code containers (priority: sa_json > file > adc_path)
    # Option 1: SA JSON as env var value (most portable — works everywhere)
    claude_code_gcp_sa_json: str = ""
    # Option 2: SA JSON file path on host (Docker only)
    claude_code_gcp_credentials_file: str = ""
    # Option 3: gcloud ADC config directory on host (Docker dev only)
    claude_code_gcp_adc_path: str = ""

    # Kubernetes runtime settings (when coding_runtime_provider = "kubernetes")
    coding_k8s_namespace: str = "alfred"
    coding_k8s_service_account: str = ""
    coding_k8s_image_pull_secret: str = ""

    # Cloud Run runtime settings (when coding_runtime_provider = "cloudrun")
    coding_cloudrun_project: str = ""
    coding_cloudrun_region: str = ""
    coding_cloudrun_service_account: str = ""

    # Memory
    memory_retrieval_limit: int = 5
    memory_similarity_threshold: float = 0.7  # for deduplication

    # Context window management
    context_usage_threshold: float = 0.8  # trigger summarization at this % of context
    context_summary_model: str = ""  # empty = use default_llm

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
