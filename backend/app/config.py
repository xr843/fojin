from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "fojin"
    postgres_user: str = "fojin"
    postgres_password: str = "fojin_secret"

    # Elasticsearch
    es_host: str = "http://localhost:9200"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # JWT
    jwt_secret_key: str = "fojin-jwt-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    # LLM (OpenAI-compatible API)
    llm_api_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # Embedding (can use a separate provider)
    embedding_api_url: str = ""  # Falls back to llm_api_url if empty
    embedding_api_key: str = ""  # Falls back to llm_api_key if empty
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024

    # 典津 API (guji.cckb.cn)
    dianjin_api_key: str = ""
    dianjin_api_url: str = "https://guji.cckb.cn/api"

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
