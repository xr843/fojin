"""Tests for the custom exception hierarchy."""

from fastapi import status

from app.core.exceptions import (
    AuthError,
    DianjinServiceError,
    FoJinError,
    InvalidCredentialsError,
    NotFoundError,
    SearchServiceError,
    SourceNotFoundError,
    TextNotFoundError,
    TokenExpiredError,
    ValidationError,
    fojin_error_to_http,
)


class TestExceptionHierarchy:
    def test_base_error(self):
        err = FoJinError("自定义消息")
        assert str(err) == "自定义消息"
        assert err.message == "自定义消息"

    def test_base_error_default_message(self):
        err = FoJinError()
        assert err.message == "服务内部错误"

    def test_text_not_found_by_id(self):
        err = TextNotFoundError(text_id=42)
        assert "42" in err.message
        assert err.text_id == 42

    def test_text_not_found_by_cbeta_id(self):
        err = TextNotFoundError(cbeta_id="T0001")
        assert "T0001" in err.message
        assert err.cbeta_id == "T0001"

    def test_source_not_found(self):
        err = SourceNotFoundError("cbeta")
        assert "cbeta" in err.message

    def test_inheritance(self):
        assert isinstance(TextNotFoundError(text_id=1), NotFoundError)
        assert isinstance(TextNotFoundError(text_id=1), FoJinError)
        assert isinstance(SearchServiceError(), FoJinError)
        assert isinstance(InvalidCredentialsError(), AuthError)


class TestErrorToHTTP:
    def test_not_found_maps_to_404(self):
        http = fojin_error_to_http(TextNotFoundError(text_id=1))
        assert http.status_code == status.HTTP_404_NOT_FOUND

    def test_auth_maps_to_401(self):
        http = fojin_error_to_http(InvalidCredentialsError())
        assert http.status_code == status.HTTP_401_UNAUTHORIZED

    def test_token_expired_maps_to_401(self):
        http = fojin_error_to_http(TokenExpiredError())
        assert http.status_code == status.HTTP_401_UNAUTHORIZED

    def test_validation_maps_to_422(self):
        http = fojin_error_to_http(ValidationError("字段无效"))
        assert http.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_search_service_maps_to_503(self):
        http = fojin_error_to_http(SearchServiceError())
        assert http.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_dianjin_service_maps_to_502(self):
        http = fojin_error_to_http(DianjinServiceError())
        assert http.status_code == status.HTTP_502_BAD_GATEWAY

    def test_base_error_maps_to_500(self):
        http = fojin_error_to_http(FoJinError("unexpected"))
        assert http.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_detail_preserved(self):
        http = fojin_error_to_http(TextNotFoundError(cbeta_id="T0001"))
        assert "T0001" in http.detail
