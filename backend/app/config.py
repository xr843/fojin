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
    es_user: str = "elastic"
    es_password: str = ""  # empty → connect without auth (backward compatible)

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""

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

    # Feed the imported MITRA cross-lingual parallels (mitra_alignments,
    # ~908K Skt/Tib↔汉 sentence pairs) into the chat RAG context, not just the
    # reader panel. Adds [跨藏对读] evidence for languages the small self-built
    # alignment_pairs table doesn't cover (esp. Sanskrit). Set false to roll
    # back to alignment_pairs-only parallels without a redeploy.
    enable_mitra_rag_parallels: bool = True

    # Quality gate for the MITRA parallels: keep only rows whose proxy quality
    # score (mitra_e_score) clears mitra_min_score. NULL-permissive — unscored
    # rows (the whole table until a prod backfill runs) still flow, so enabling
    # this before the backfill is a no-op. Governs ALL MITRA read paths via
    # services.mitra_gate: the RAG context (_attach_mitra_parallels), the
    # citation drawer (get_chunk_parallels) and the coverage catalog
    # (compute_alignment_catalog). Set false to drop the predicate everywhere
    # and fall back to ungated (pre-gate) behavior, without a redeploy.
    mitra_min_score: float = 0.30
    enable_mitra_score_gate: bool = True

    # Sentence-level 逐句对读 read path (Phase 4 Package C). Gates
    # GET /alignment/sentences/{text_id}/{juan_num}, which serves the future
    # reader's sentence-by-sentence parallel view out of ``sentence_alignments``.
    # Ships DARK (default False): the endpoint returns a clean empty payload
    # (total=0, pairs=[]) instead of querying, so the contract is live and
    # client.ts types can land before the prod refinement job
    # (refine_sentence_alignments.py) populates the table or any UI exists.
    # Flip true via env once BOTH the data is backfilled and the reader UI
    # ships; set false again to instantly roll back to the dark state without a
    # redeploy (and even when true, an empty table self-serves the same empty
    # payload — never an error).
    enable_sentence_parallels: bool = False

    # Open-data bulk exports (/api/exports/*). Ships OFF: the endpoints are
    # unauthenticated and stream whole datasets with no overall cap — a single
    # /exports/kg.json is 50.7 MB / 62 s against production data — and they sit
    # outside STRICT_PATHS, so one IP could hold hundreds of concurrent
    # long-running streams and exhaust the connection pool. The feature is
    # intended (versioned, licensed datasets), just not ready to be public.
    # When off the routes are not registered at all: 404, absent from OpenAPI.
    # Before turning this on, give the heavy paths their own STRICT_PATHS
    # entries.
    enable_open_data_exports: bool = False

    # Observability — expose Prometheus metrics at /metrics (app root, not
    # /api; not proxied by nginx, so network-internal only). Set false to
    # not mount the endpoint at all. See app/core/metrics.py.
    metrics_enabled: bool = True

    # 典津 API (guji.cckb.cn)
    dianjin_api_key: str = ""
    dianjin_api_url: str = "https://guji.cckb.cn/api"

    # 百度搜索资源平台 - 主动推送 API token（可选）。领取：ziyuan.baidu.com →
    # 站点管理 → 普通收录 → API 提交。仅 scripts/baidu_push.py 使用，用来把新
    # 页面 URL 主动推给百度收录；未设置时该脚本报错退出（不静默跳过），不影响
    # 应用本身启动或运行。
    baidu_push_token: str = ""

    # OAuth: GitHub
    github_client_id: str = ""
    github_client_secret: str = ""

    # OAuth: Google
    google_client_id: str = ""
    google_client_secret: str = ""

    # Phone/SMS login. Ships OFF: nothing in the frontend calls
    # /auth/sms/send-code or /auth/sms/login, but they were mounted in
    # production anyway — and /sms/login auto-registers an unknown number
    # into a JWT, so it was an unauthenticated auth surface with no users
    # and no monitoring. When off the routes are not registered at all.
    # Turning it on in production requires the full credential set below
    # (enforced at boot); an enabled-but-unconfigured SMS login is exactly
    # the state that used to print live login codes to the app log.
    enable_sms_login: bool = False

    # SMS: Alibaba Cloud
    aliyun_sms_access_key_id: str = ""
    aliyun_sms_access_key_secret: str = ""
    aliyun_sms_sign_name: str = "佛津"
    aliyun_sms_template_code: str = ""

    # OAuth callback base URL (e.g. https://fojin.app)
    oauth_redirect_base: str = "http://localhost:3000"

    # Public origin of the site, for absolute links handed to third parties
    # (agents, citers) who have no host to attach a relative path to.
    # api/sitemap.py and api/rss.py each carry their own BASE_URL constant and
    # predate this setting; they are SEO-critical and left alone rather than
    # refactored in passing. New code should use this.
    site_base_url: str = "https://fojin.app"

    # Chat attachment uploads — parsed-to-text files prepended to user
    # messages. Directory is created on first write; override per-env.
    upload_dir: str = "/data/uploads/chat"

    # Rate limiting (requests per minute)
    rate_limit_default: int = 200
    rate_limit_login: int = 10
    rate_limit_register: int = 5
    # SMS endpoints — per-IP defense in depth on top of the per-phone caps in
    # oauth.send_sms_code / verify_sms_code. send costs real money; verify is
    # the brute-force surface.
    rate_limit_sms_send: int = 3
    rate_limit_sms_verify: int = 10
    # Paid-inference endpoints (platform key): each request triggers embedding
    # and/or LLM calls, so cap them well below the default per-IP budget.
    rate_limit_semantic: int = 20
    rate_limit_research: int = 10
    rate_limit_ai_diff: int = 10
    # Open-world quote verification: no paid inference, but each call is an
    # ES phrase search plus full-fascicle source reads — same cost class as
    # /api/search/content (30/min).
    rate_limit_verify_quote: int = 30
    rate_limit_commentary: int = 60
    # Chat (AI Q&A) — the most expensive endpoint: RAG retrieval always uses the
    # platform embedding key (even for BYOK users) plus a long streaming LLM
    # call and a DB pool slot. 30/min/IP is generous for real use (a stream
    # takes seconds) while capping abuse far below the 200 default.
    rate_limit_chat: int = 30
    # Attachment upload — anonymous, 10 MB/file, written to host disk with no
    # GC. Real use is a handful of files before one chat turn, so this can be
    # much tighter than the chat limit itself.
    rate_limit_attachment_upload: int = 10

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
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/0"

    model_config = {"env_file": ("../.env", ".env"), "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

# Secure by default: an unset FOJIN_ENV is treated as production, so a bare
# `uvicorn` started outside docker-compose can't silently boot with the
# insecure default secrets. Local dev, tests, and alembic opt into the relaxed
# path by setting FOJIN_ENV=development explicitly (see backend/conftest.py and
# alembic/env.py).
_fojin_env = os.environ.get("FOJIN_ENV", "production").lower()

if _fojin_env != "development":
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
    # SMS login is off by default and its routes aren't mounted, so an unset
    # credential set is the normal state and must not block boot. But turning
    # it ON without credentials is the exact configuration that used to make
    # send_sms_code fall into "dev mode" and log live login codes, so an
    # enabled-but-incomplete config fails fast instead.
    if settings.enable_sms_login:
        _sms_missing = [
            name
            for name, value in (
                ("ALIYUN_SMS_ACCESS_KEY_ID", settings.aliyun_sms_access_key_id),
                ("ALIYUN_SMS_ACCESS_KEY_SECRET", settings.aliyun_sms_access_key_secret),
                ("ALIYUN_SMS_TEMPLATE_CODE", settings.aliyun_sms_template_code),
            )
            if not value
        ]
        if _sms_missing:
            raise RuntimeError(
                "FATAL: ENABLE_SMS_LOGIN is on but SMS is not fully configured. "
                f"Missing: {', '.join(_sms_missing)}. "
                "Set them, or unset ENABLE_SMS_LOGIN to disable phone login."
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
