import logging
import os

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

_DEFAULT_JWT_SECRET = "dev-only-insecure-default-replace-in-production"


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "fojin"
    postgres_user: str = "fojin"
    postgres_password: str = ""

    # Elasticsearch
    es_host: str = "http://localhost:9200"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # JWT
    jwt_secret_key: str = os.environ.get("JWT_SECRET_KEY", _DEFAULT_JWT_SECRET)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 8  # 8 hours

    # BYOK API key encryption — independent of jwt_secret_key so rotating
    # one doesn't silently destroy the other (see P0-1 audit).  Must be a
    # base64-urlsafe 32-byte key in Fernet.generate_key() format.  In
    # production this is fail-fast at boot; in dev a temporary key is
    # generated on each boot, which means stored ciphertexts won't decrypt
    # across restarts — intentional, to avoid silent dev/prod divergence.
    api_key_encryption_key: str = os.environ.get("API_KEY_ENCRYPTION_KEY", "")

    # LLM (OpenAI-compatible API) — primary model
    llm_api_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # LLM fallback — platform secondary model used when the primary provider
    # fails before any tokens have been streamed. Leave empty to disable.
    llm_fallback_api_url: str = ""
    llm_fallback_api_key: str = ""
    llm_fallback_model: str = ""

    # Embedding (can use a separate provider)
    embedding_api_url: str = ""  # Falls back to llm_api_url if empty
    embedding_api_key: str = ""  # Falls back to llm_api_key if empty
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024

    # Reranker (optional API-based cross-encoder, e.g. SiliconFlow bge-reranker-v2-m3)
    reranker_api_url: str = ""   # e.g. https://api.siliconflow.cn/v1
    reranker_api_key: str = ""   # Falls back to embedding_api_key if empty
    reranker_model: str = "BAAI/bge-reranker-v2-m3"

    # Observability — expose Prometheus metrics at /metrics (app root, not
    # /api; not proxied by nginx, so network-internal only). Set false to
    # not mount the endpoint at all. See app/core/metrics.py.
    metrics_enabled: bool = True

    # 典津 API (guji.cckb.cn)
    dianjin_api_key: str = ""
    dianjin_api_url: str = "https://guji.cckb.cn/api"

    # OAuth: GitHub
    github_client_id: str = ""
    github_client_secret: str = ""

    # OAuth: Google
    google_client_id: str = ""
    google_client_secret: str = ""

    # SMS: Alibaba Cloud
    aliyun_sms_access_key_id: str = ""
    aliyun_sms_access_key_secret: str = ""
    aliyun_sms_sign_name: str = "佛津"
    aliyun_sms_template_code: str = ""

    # OAuth callback base URL (e.g. https://fojin.app)
    oauth_redirect_base: str = "http://localhost:3000"

    # Chat attachment uploads — parsed-to-text files prepended to user
    # messages. Directory is created on first write; override per-env.
    upload_dir: str = "/data/uploads/chat"

    # Rate limiting (requests per minute)
    rate_limit_default: int = 200
    rate_limit_login: int = 10
    rate_limit_register: int = 5

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    model_config = {"env_file": ("../.env", ".env"), "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

_fojin_env = os.environ.get("FOJIN_ENV", "development").lower()

if _fojin_env == "production":
    if settings.jwt_secret_key == _DEFAULT_JWT_SECRET or len(settings.jwt_secret_key) < 32:
        raise RuntimeError(
            "FATAL: In production, JWT_SECRET_KEY must be set and at least 32 characters. "
            "Set the JWT_SECRET_KEY environment variable."
        )
    # Validate API_KEY_ENCRYPTION_KEY at boot.  Fernet construction is the
    # canonical "is this a usable key?" check — covers length, base64
    # alphabet, and padding in one call.
    if not settings.api_key_encryption_key:
        raise RuntimeError(
            "FATAL: In production, API_KEY_ENCRYPTION_KEY must be set. "
            "Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        from cryptography.fernet import Fernet as _Fernet  # local import keeps tooling import paths clean

        _Fernet(settings.api_key_encryption_key.encode())
    except Exception as exc:  # pragma: no cover — exercised manually at boot
        raise RuntimeError(
            f"FATAL: API_KEY_ENCRYPTION_KEY is not a valid Fernet key: {exc}. "
            "Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ) from None
else:
    if settings.jwt_secret_key == _DEFAULT_JWT_SECRET:
        logger.warning(
            "JWT_SECRET_KEY not set — using insecure default. "
            "Set the JWT_SECRET_KEY environment variable in production!"
        )
    if not settings.api_key_encryption_key:
        # Dev fallback: ephemeral key.  Stored ciphertexts won't survive a
        # restart, but that's preferable to silently sharing a derived key
        # across machines (the bug we're fixing in prod).
        from cryptography.fernet import Fernet as _Fernet

        settings.api_key_encryption_key = _Fernet.generate_key().decode()
        logger.warning(
            "API_KEY_ENCRYPTION_KEY not set — generated an ephemeral dev key. "
            "Stored BYOK ciphertexts will not decrypt across restarts."
        )
