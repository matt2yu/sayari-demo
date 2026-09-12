"""Sayari SDK wrapper: rate limiting, retry, and call accounting.

Two things here exist because the SDK does not provide them:

1. Retry. The docs state the SDK "will automatically wait and retry requests if a
   429 is received". It does not. In sayari/core/http_client.py the internal
   `retries` counter starts at 2 while `max_retries` defaults to 0, so the guard
   `if max_retries > retries` is `0 > 2` -- false -- and nothing is ever retried.
   Passing max_retries=N yields only N-2 retries, which is its own trap.

2. Rate limiting. Sayari enforces two per-endpoint tiers and returns 429 with a
   Retry-After header on breach. Staying under the limit is cheaper than backing
   off from it, so every call goes through a token bucket for its tier.

Call counts are tracked so the writeup can report real API cost rather than an
estimate.
"""

from __future__ import annotations

import os
import pathlib
import threading
import time
from collections import Counter, deque
from typing import Any, Callable, Literal

from dotenv import load_dotenv
from sayari.client import Sayari
from sayari.core.api_error import ApiError

Tier = Literal["standard", "advanced"]

# Documented at /api/key-concepts/rate-limits. Budgets are per endpoint; we apply
# them per tier, which is stricter than required and therefore safe.
TIER_BUDGET: dict[Tier, tuple[int, float]] = {
    "standard": (200, 60.0),   # 200 requests / 60s
    "advanced": (15, 10.0),    # 15 requests / 10s
}

# Retried regardless of tier. 429 is rate limiting; the 5xx family and 408/409 are
# transient. Everything else (400/401/404/422) is a bug in our request -- retrying
# it just burns quota.
RETRY_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504, 520})

MAX_ATTEMPTS = 5
MAX_BACKOFF_SECONDS = 30.0


class _TokenBucket:
    """Sliding-window limiter. Blocks until a slot is free."""

    def __init__(self, budget: int, window: float) -> None:
        self._budget = budget
        self._window = window
        self._hits: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._hits and now - self._hits[0] >= self._window:
                    self._hits.popleft()
                if len(self._hits) < self._budget:
                    self._hits.append(now)
                    return
                sleep_for = self._window - (now - self._hits[0])
            time.sleep(max(sleep_for, 0.01))


class SayariClient:
    """Thin, rate-limited facade over the endpoints this project actually uses.

    Methods are deliberately explicit rather than a generic passthrough so the set
    of endpoints we depend on is readable in one place.
    """

    def __init__(self, client_id: str | None = None, client_secret: str | None = None) -> None:
        if client_id is None or client_secret is None:
            # Walk up to the repo root so this works from backend/ or the root.
            for parent in pathlib.Path(__file__).resolve().parents:
                candidate = parent / ".env"
                if candidate.exists():
                    load_dotenv(candidate)
                    break
            client_id = client_id or os.environ.get("SAYARI_CLIENT_ID")
            client_secret = client_secret or os.environ.get("SAYARI_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise RuntimeError(
                "Missing SAYARI_CLIENT_ID / SAYARI_CLIENT_SECRET. "
                "Copy .env.example to .env and fill them in."
            )
        # The SDK refreshes the OAuth token on its own (2 minute buffer).
        self._sdk = Sayari(client_id=client_id, client_secret=client_secret)
        self._buckets = {t: _TokenBucket(*TIER_BUDGET[t]) for t in TIER_BUDGET}
        self.calls: Counter[str] = Counter()
        self.retries: Counter[str] = Counter()

    # ---------------------------------------------------------------- plumbing

    def _guard(self, label: str, tier: Tier, fn: Callable[[], Any]) -> Any:
        """Rate limit, invoke, and retry transient failures."""
        for attempt in range(MAX_ATTEMPTS):
            self._buckets[tier].acquire()
            self.calls[label] += 1
            try:
                return fn()
            except ApiError as exc:
                status = getattr(exc, "status_code", None)
                if status not in RETRY_STATUS or attempt == MAX_ATTEMPTS - 1:
                    raise
                self.retries[label] += 1
                time.sleep(self._backoff(exc, attempt))
        raise RuntimeError("unreachable")

    @staticmethod
    def _backoff(exc: ApiError, attempt: int) -> float:
        """Honour Retry-After when present, else exponential backoff."""
        headers = getattr(getattr(exc, "response", None), "headers", None) or {}
        raw = headers.get("Retry-After") or headers.get("retry-after")
        if raw:
            try:
                return min(float(raw), MAX_BACKOFF_SECONDS)
            except (TypeError, ValueError):
                pass
        return min(0.5 * (2 ** attempt), MAX_BACKOFF_SECONDS)

    # ------------------------------------------------------------ standard tier

    def resolve(self, **kwargs: Any) -> Any:
        """GET /v1/resolution. `limit` max is 10 -- larger values are rejected."""
        return self._guard("resolution", "standard", lambda: self._sdk.resolution.resolution(**kwargs))

    def entity_summary(self, entity_id: str) -> Any:
        """GET /v1/entity_summary/{id}. Cheaper than get_entity and still carries
        the full `risk` object with traversal_path metadata."""
        return self._guard(
            "entity_summary", "standard", lambda: self._sdk.entity.entity_summary(entity_id)
        )

    def get_entity(self, entity_id: str, **kwargs: Any) -> Any:
        """GET /v1/entity/{id}. Needed only when relationship edges are required."""
        return self._guard(
            "entity", "standard", lambda: self._sdk.entity.get_entity(entity_id, **kwargs)
        )

    def risk_factors(self) -> Any:
        """GET /v1/ontology/risk_factors -- the glossary we render flags with.

        Note this is /v1/ontology/risk_factors, not /v1/risk_factors (which 404s).
        """
        return self._guard("ontology", "standard", lambda: self._sdk.ontology.get_risk_factors())

    def usage(self, **kwargs: Any) -> Any:
        """GET /v1/usage. Note the trailing underscore on `from_`."""
        return self._guard("usage", "standard", lambda: self._sdk.info.get_usage(**kwargs))

    # ------------------------------------------------------------ advanced tier

    def traversal(self, entity_id: str, **kwargs: Any) -> Any:
        """GET /v1/traversal/{id}. `limit` max is 50; 50+ returns 422, and traversal
        does not map 422 to a typed exception, so it surfaces as a bare ApiError."""
        return self._guard(
            "traversal", "advanced", lambda: self._sdk.traversal.traversal(entity_id, **kwargs)
        )

    def ubo(self, entity_id: str, **kwargs: Any) -> Any:
        """GET /v1/ubo/{id}."""
        return self._guard("ubo", "advanced", lambda: self._sdk.traversal.ubo(entity_id, **kwargs))

    def ownership(self, entity_id: str, **kwargs: Any) -> Any:
        """GET /v1/downstream/{id}.

        Named `ownership` in the SDK. There is no `traversal.downstream`.
        """
        return self._guard(
            "downstream", "advanced", lambda: self._sdk.traversal.ownership(entity_id, **kwargs)
        )

    def search_entity(self, **kwargs: Any) -> Any:
        """POST /v1/search/entity. Only the POST form accepts `filter`."""
        return self._guard(
            "search_entity", "advanced", lambda: self._sdk.search.search_entity(**kwargs)
        )

    # --------------------------------------------------------------------- trade

    def search_suppliers(self, **kwargs: Any) -> Any:
        """POST /v1/trade/search/suppliers."""
        return self._guard(
            "trade_suppliers", "standard", lambda: self._sdk.trade.search_suppliers(**kwargs)
        )

    def search_shipments(self, **kwargs: Any) -> Any:
        """POST /v1/trade/search/shipments -- the dated, product-level evidence."""
        return self._guard(
            "trade_shipments", "standard", lambda: self._sdk.trade.search_shipments(**kwargs)
        )

    # ----------------------------------------------------------------- reporting

    def call_report(self) -> dict[str, Any]:
        return {
            "total_calls": sum(self.calls.values()),
            "by_endpoint": dict(self.calls),
            "retries": dict(self.retries),
        }
