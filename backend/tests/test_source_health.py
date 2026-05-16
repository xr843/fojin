"""Unit tests for data-source health classification.

数据源健康状态分类的单元测试。Pure logic, no DB / network."""

import pytest

from app.services.source_health import classify_health

HOME = "https://example.org/"


def test_plain_2xx_same_site_is_ok():
    assert classify_health(error=None, status_code=200, requested_url=HOME, final_url=HOME) == "ok"


def test_redirect_within_same_host_is_ok():
    # Sites reorganise paths; a path-only redirect is not a "move".
    assert (
        classify_health(
            error=None, status_code=200, requested_url=HOME, final_url="https://example.org/welcome"
        )
        == "ok"
    )


def test_http_to_https_upgrade_is_ok():
    assert (
        classify_health(
            error=None, status_code=200, requested_url="http://example.org/", final_url=HOME
        )
        == "ok"
    )


def test_www_prefix_difference_is_ok():
    assert (
        classify_health(
            error=None, status_code=200, requested_url=HOME, final_url="https://www.example.org/"
        )
        == "ok"
    )


def test_redirect_to_different_domain_is_moved():
    assert (
        classify_health(
            error=None, status_code=200, requested_url=HOME, final_url="https://newsite.com/"
        )
        == "moved"
    )


def test_4xx_is_degraded():
    for code in (403, 404, 410):
        assert (
            classify_health(error=None, status_code=code, requested_url=HOME, final_url=HOME)
            == "degraded"
        )


def test_5xx_is_unreachable():
    for code in (500, 502, 503):
        assert (
            classify_health(error=None, status_code=code, requested_url=HOME, final_url=HOME)
            == "unreachable"
        )


def test_ssl_error_is_cert_invalid():
    assert (
        classify_health(error="ssl", status_code=None, requested_url=HOME, final_url=None)
        == "cert_invalid"
    )


def test_timeout_and_connect_errors_are_unreachable():
    for err in ("timeout", "connect", "redirect_loop", "other"):
        assert (
            classify_health(error=err, status_code=None, requested_url=HOME, final_url=None)
            == "unreachable"
        )


def test_moved_classification_ignores_error_status_codes():
    # A cross-domain redirect that lands on a 404 is still primarily "moved":
    # the domain change is the more actionable signal for an editor.
    assert (
        classify_health(
            error=None, status_code=404, requested_url=HOME, final_url="https://newsite.com/gone"
        )
        == "moved"
    )


@pytest.mark.parametrize("status", [200, 301, 302, 399])
def test_2xx_3xx_range_treated_as_reachable(status):
    assert classify_health(
        error=None, status_code=status, requested_url=HOME, final_url=HOME
    ) == "ok"
