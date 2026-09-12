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
    assert SayariClient._backoff(exc, attempt=0) == 30.0


def test_backoff_falls_back_to_exponential():
    exc = ApiError(status_code=500, body=None)
    assert SayariClient._backoff(exc, attempt=0) == 0.5
    assert SayariClient._backoff(exc, attempt=3) == 4.0


def test_missing_credentials_raise_clearly(monkeypatch):
    monkeypatch.delenv("SAYARI_CLIENT_ID", raising=False)
    monkeypatch.delenv("SAYARI_CLIENT_SECRET", raising=False)
    monkeypatch.setattr("pipeline.client.load_dotenv", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="SAYARI_CLIENT_ID"):
        SayariClient()
