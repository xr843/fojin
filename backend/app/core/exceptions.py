"""Custom exception hierarchy for FoJin backend.

Usage:
    from app.core.exceptions import TextNotFoundError, SearchServiceError

    raise TextNotFoundError(text_id=42)
    raise SearchServiceError("Elasticsearch cluster unreachable")
"""

from fastapi import HTTPException, status


class FoJinError(Exception):
    """Base exception for all FoJin application errors."""

    message: str = "服务内部错误"

    def __init__(self, message: str | None = None, *, detail: str | None = None):
        self.message = message or self.__class__.message
        self.detail = detail
        super().__init__(self.message)


# ---- Resource errors ----

class NotFoundError(FoJinError):
    """Requested resource does not exist."""

    message = "资源未找到"


class TextNotFoundError(NotFoundError):
    """A specific text was not found."""

    def __init__(self, *, text_id: int | None = None, cbeta_id: str | None = None):
        ident = cbeta_id or (str(text_id) if text_id else "unknown")
        super().__init__(f"经典未找到: {ident}")
        self.text_id = text_id
        self.cbeta_id = cbeta_id


class SourceNotFoundError(NotFoundError):
    """A data source was not found."""

    def __init__(self, code: str):
        super().__init__(f"数据源未找到: {code}")
        self.code = code


class DictionaryEntryNotFoundError(NotFoundError):
    """A dictionary entry was not found."""

    def __init__(self, *, entry_id: int):
        super().__init__(f"词条未找到: {entry_id}")
        self.entry_id = entry_id


class KGEntityNotFoundError(NotFoundError):
    """A knowledge-graph entity was not found."""

    def __init__(self, *, entity_id: int):
        super().__init__(f"实体未找到: {entity_id}")
        self.entity_id = entity_id


class ManifestNotFoundError(NotFoundError):
    """An IIIF manifest was not found."""

    message = "Manifest 未找到"


class SuggestionNotFoundError(NotFoundError):
    """A source suggestion was not found."""

    message = "推荐记录不存在"


# ---- Conflict errors ----

class ConflictError(FoJinError):
    """Resource already exists or conflicts with current state."""

    message = "资源冲突"


class DuplicateBookmarkError(ConflictError):
    """Bookmark already exists for this text."""

    message = "已收藏"


class DuplicateUsernameError(ConflictError):
    """Username is already taken."""

    message = "用户名已存在"


class DuplicateEmailError(ConflictError):
    """Email is already registered."""

    message = "邮箱已被注册"


# ---- Service errors ----

class ServiceError(FoJinError):
    """An external or internal service is unavailable."""

    message = "服务暂时不可用"


class SearchServiceError(ServiceError):
    """Elasticsearch / search service error."""

    message = "搜索服务暂时不可用"


class DianjinServiceError(ServiceError):
    """Dianjin cross-platform API error."""

    message = "典津平台服务异常"


class LLMServiceError(ServiceError):
    """LLM / AI chat service error."""

    message = "AI 服务暂时不可用"


class EmbeddingServiceError(ServiceError):
    """Embedding API error."""

    message = "向量服务暂时不可用"


# ---- Auth errors ----

class AuthError(FoJinError):
    """Authentication or authorization error."""

    message = "认证失败"


class InvalidCredentialsError(AuthError):
    """Wrong username or password."""

    message = "用户名或密码错误"


class TokenExpiredError(AuthError):
    """JWT token has expired."""

    message = "登录已过期，请重新登录"


class AccountDisabledError(AuthError):
    """User account is disabled."""

    message = "账号已被禁用"


# ---- Authorization errors ----

class AccessDeniedError(FoJinError):
    """User does not have permission to access this resource."""

    message = "无权访问"


# ---- Validation errors ----

class ValidationError(FoJinError):
    """Input validation error."""

    message = "输入参数无效"


# ---- Quota errors ----

class QuotaExceededError(FoJinError):
    """User has exceeded their usage quota."""

    message = "额度已用完"

    def __init__(self, limit: int):
        super().__init__(f"今日免费额度已用完（{limit}次/天）。配置自己的 API Key 可无限使用。")
        self.limit = limit


class ResetLinkInvalidError(FoJinError):
    """忘记密码的一次性重置链接无效、已用过、已过期，或期间密码已被改过。

    单独成类、映射 400：继承 InvalidCredentialsError 会因 STATUS_MAP 按类型精确查表
    而落到 500（#1435 上线后实测）；而 401 又会被前端当成「登录失效」。
    """

    message = "链接无效或已过期，请重新申请"


# ---- Converter: FoJinError -> HTTPException ----

STATUS_MAP: dict[type, int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    TextNotFoundError: status.HTTP_404_NOT_FOUND,
    SourceNotFoundError: status.HTTP_404_NOT_FOUND,
    DictionaryEntryNotFoundError: status.HTTP_404_NOT_FOUND,
    KGEntityNotFoundError: status.HTTP_404_NOT_FOUND,
    ManifestNotFoundError: status.HTTP_404_NOT_FOUND,
    SuggestionNotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    DuplicateBookmarkError: status.HTTP_409_CONFLICT,
    DuplicateUsernameError: status.HTTP_409_CONFLICT,
    DuplicateEmailError: status.HTTP_409_CONFLICT,
    AuthError: status.HTTP_401_UNAUTHORIZED,
    InvalidCredentialsError: status.HTTP_401_UNAUTHORIZED,
    TokenExpiredError: status.HTTP_401_UNAUTHORIZED,
    AccountDisabledError: status.HTTP_403_FORBIDDEN,
    ResetLinkInvalidError: status.HTTP_400_BAD_REQUEST,
    AccessDeniedError: status.HTTP_403_FORBIDDEN,
    ValidationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    QuotaExceededError: status.HTTP_429_TOO_MANY_REQUESTS,
    ServiceError: status.HTTP_503_SERVICE_UNAVAILABLE,
    SearchServiceError: status.HTTP_503_SERVICE_UNAVAILABLE,
    DianjinServiceError: status.HTTP_502_BAD_GATEWAY,
    LLMServiceError: status.HTTP_503_SERVICE_UNAVAILABLE,
    EmbeddingServiceError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def fojin_error_to_http(exc: FoJinError) -> HTTPException:
    """Convert a FoJinError to an appropriate HTTPException."""
    status_code = STATUS_MAP.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    return HTTPException(status_code=status_code, detail=exc.message)
