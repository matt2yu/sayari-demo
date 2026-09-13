"""Tests for the rate limiter and retry logic.

These are the parts that exist because the SDK's own behaviour is wrong, so they
need to be pinned. No network access.
"""

import time
import typing

import pytest
from sayari.core.api_error import ApiError

from pipeline.client import RETRY_STATUS, SayariClient, _TokenBucket


def test_bucket_allows_up_to_budget_without_blocking():
    bucket = _TokenBucket(budget=5, window=10.0)
    start = time.monotonic()
    for _ in range(5):
        bucket.acquire()
    assert time.monotonic() - start < 0.1


def test_bucket_blocks_once_budget_is_spent():
    bucket = _TokenBucket(budget=2, window=0.3)
    for _ in range(2):
        bucket.acquire()
    start = time.monotonic()
    bucket.acquire()  # must wait for the window to roll over
    assert time.monotonic() - start >= 0.2


def test_retry_status_excludes_client_errors():
    # Retrying a malformed request just burns quota; it will never succeed.
    for status in (400, 401, 403, 404, 422):
        assert status not in RETRY_STATUS
    for status in (429, 500, 502, 503):
        assert status in RETRY_STATUS


def test_backoff_honours_retry_after_header():
    class _Resp:
        headers: typing.ClassVar = {"Retry-After": "7"}

    exc = ApiError(status_code=429, body=None)
    exc.response = _Resp()
    assert SayariClient._backoff(exc, attempt=0) == 7.0


def test_backoff_caps_absurd_retry_after():
    class _Resp:
        headers: typing.ClassVar = {"Retry-After": "9999"}

    exc = ApiError(status_code=429, body=None)
    exc.response = _Resp()
    # Capped at MAX_BACKOFF_SECONDS, which must exceed the 60s standard-tier block
    # so a legitimate Retry-After of ~60 is honoured in full rather than truncated.
    assert SayariClient._backoff(exc, attempt=0) == 75.0


def test_backoff_falls_back_to_exponential():
    exc = ApiError(status_code=500, body=None)
    assert SayariClient._backoff(exc, attempt=0) == 0.5
    assert SayariClient._backoff(exc, attempt=3) == 4.0


def test_429_without_retry_after_waits_out_the_tier_block():
    """Exponential backoff tops out around 8s; the standard block is a full minute,
    so backing off exponentially burns every attempt inside the block and reports a
    failure that was only ever a wait. This regression cost us a whole pipeline run.
    """
    exc = ApiError(status_code=429, body=None)
    assert SayariClient._backoff(exc, attempt=0, tier="standard") == 60.0
    assert SayariClient._backoff(exc, attempt=4, tier="standard") == 60.0
    assert SayariClient._backoff(exc, attempt=0, tier="advanced") == 10.0


def test_html_error_page_is_treated_as_transient():
    """Under load the edge answers with a Cloudflare interstitial instead of JSON.
    An HTML body from a JSON API is always infrastructure, never a real answer."""
    exc = ApiError(status_code=403, body="<!doctype html><html>Cloudflare</html>")
    assert SayariClient._is_transient(exc) is True


def test_genuine_client_errors_are_not_transient():
    assert SayariClient._is_transient(ApiError(status_code=404, body={"messages": ["Not Found"]})) is False
    assert SayariClient._is_transient(ApiError(status_code=422, body={"messages": ["bad"]})) is False


def test_missing_credentials_raise_clearly(monkeypatch):
    monkeypatch.delenv("SAYARI_CLIENT_ID", raising=False)
    monkeypatch.delenv("SAYARI_CLIENT_SECRET", raising=False)
    monkeypatch.setattr("pipeline.client.load_dotenv", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="SAYARI_CLIENT_ID"):
        SayariClient()
