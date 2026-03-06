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


# ---- Validation errors ----

class ValidationError(FoJinError):
    """Input validation error."""

    message = "输入参数无效"


# ---- Converter: FoJinError -> HTTPException ----

STATUS_MAP: dict[type, int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    TextNotFoundError: status.HTTP_404_NOT_FOUND,
    SourceNotFoundError: status.HTTP_404_NOT_FOUND,
    AuthError: status.HTTP_401_UNAUTHORIZED,
    InvalidCredentialsError: status.HTTP_401_UNAUTHORIZED,
    TokenExpiredError: status.HTTP_401_UNAUTHORIZED,
    ValidationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ServiceError: status.HTTP_503_SERVICE_UNAVAILABLE,
    SearchServiceError: status.HTTP_503_SERVICE_UNAVAILABLE,
    DianjinServiceError: status.HTTP_502_BAD_GATEWAY,
    LLMServiceError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def fojin_error_to_http(exc: FoJinError) -> HTTPException:
    """Convert a FoJinError to an appropriate HTTPException."""
    status_code = STATUS_MAP.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    return HTTPException(status_code=status_code, detail=exc.message)
