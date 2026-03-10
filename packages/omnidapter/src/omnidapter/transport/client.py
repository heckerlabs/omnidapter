"""
Shared async HTTP transport client for all provider implementations.

Providers use this client rather than managing their own httpx instances.
Handles:
- Retry with backoff
- Rate limit detection
- Correlation ID injection
- Structured logging
- Hook invocations
- Error normalization
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from omnidapter.core.errors import ProviderAPIError, RateLimitError, TransportError
from omnidapter.core.logging import transport_logger
from omnidapter.transport.correlation import new_correlation_id
from omnidapter.transport.hooks import RequestHookContext, ResponseHookContext, TransportHooks
from omnidapter.transport.retry import RetryPolicy


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a Retry-After header value (seconds or HTTP-date)."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        pass
    # Try HTTP-date format
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(value)
        delta = (dt - datetime.now(tz=timezone.utc)).total_seconds()
        return max(0.0, delta)
    except Exception:
        return None


def _parse_rate_limit_reset(value: str | None) -> datetime | None:
    """Parse a rate limit reset header (Unix timestamp or HTTP-date)."""
    if value is None:
        return None
    try:
        ts = float(value)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, TypeError):
        pass
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(value)
    except Exception:
        return None


class OmnidapterHttpClient:
    """Shared async HTTP client with retry, rate-limit handling, and observability.

    One instance per provider connection (or shared across connections for the same provider).
    """

    def __init__(
        self,
        provider_key: str,
        retry_policy: RetryPolicy | None = None,
        hooks: TransportHooks | None = None,
        base_url: str = "",
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self._provider_key = provider_key
        self._retry_policy = retry_policy or RetryPolicy.default()
        self._hooks = hooks or TransportHooks()
        self._base_url = base_url
        self._default_headers = default_headers or {}

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._default_headers,
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
        )

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any = None,
        data: Any = None,
        correlation_id: str | None = None,
    ) -> httpx.Response:
        """Execute an HTTP request with retry and observability.

        Args:
            method: HTTP method.
            url: Full URL or path (if base_url is set).
            headers: Additional request headers.
            params: Query parameters.
            json: JSON body.
            data: Form or raw body.
            correlation_id: Optional correlation ID (generated if not provided).

        Returns:
            httpx.Response on success.

        Raises:
            RateLimitError: On 429 responses after retries exhausted.
            ProviderAPIError: On non-retried error responses.
            TransportError: On network failures.
        """
        corr_id = correlation_id or new_correlation_id()
        merged_headers = {**self._default_headers, **(headers or {})}
        merged_headers["X-Correlation-ID"] = corr_id

        policy = self._retry_policy
        last_exception: Exception | None = None

        async with self._build_client() as client:
            for attempt in range(policy.max_retries + 1):
                start = time.monotonic()

                # Fire request hook
                await self._hooks.fire_request(RequestHookContext(
                    method=method,
                    url=url,
                    headers={k: v for k, v in merged_headers.items()
                              if k.lower() not in ("authorization", "x-api-key")},
                    correlation_id=corr_id,
                    provider_key=self._provider_key,
                ))

                transport_logger.debug(
                    "Outbound request: method=%s url=%s correlation_id=%s provider=%s attempt=%d",
                    method, url, corr_id, self._provider_key, attempt,
                )

                try:
                    response = await client.request(
                        method,
                        url,
                        headers=merged_headers,
                        params=params,
                        json=json,
                        data=data,
                    )
                except httpx.TransportError as exc:
                    elapsed = (time.monotonic() - start) * 1000
                    last_exception = TransportError(
                        f"Network error: {exc}",
                        cause=exc,
                    )
                    transport_logger.warning(
                        "Transport error: correlation_id=%s attempt=%d error=%s",
                        corr_id, attempt, exc,
                    )
                    if policy.retry_on_network_error and attempt < policy.max_retries:
                        backoff = policy.get_backoff(attempt)
                        transport_logger.warning("Retrying in %.2fs...", backoff)
                        await asyncio.sleep(backoff)
                        continue
                    raise last_exception from exc

                elapsed = (time.monotonic() - start) * 1000

                # Fire response hook
                await self._hooks.fire_response(ResponseHookContext(
                    method=method,
                    url=url,
                    status_code=response.status_code,
                    correlation_id=corr_id,
                    provider_key=self._provider_key,
                    elapsed_ms=elapsed,
                ))

                transport_logger.debug(
                    "Response: status=%d correlation_id=%s elapsed_ms=%.1f",
                    response.status_code, corr_id, elapsed,
                )

                # Success
                if response.is_success:
                    return response

                # Rate limit
                if response.status_code == 429:
                    retry_after = _parse_retry_after(
                        response.headers.get("Retry-After")
                    )
                    rate_limit_remaining_str = response.headers.get("X-RateLimit-Remaining")
                    rate_limit_remaining = (
                        int(rate_limit_remaining_str)
                        if rate_limit_remaining_str is not None
                        else None
                    )
                    rate_limit_reset = _parse_rate_limit_reset(
                        response.headers.get("X-RateLimit-Reset")
                    )
                    provider_request_id = (
                        response.headers.get("X-Request-ID")
                        or response.headers.get("Request-Id")
                    )
                    transport_logger.warning(
                        "Rate limited: provider=%s retry_after=%s correlation_id=%s",
                        self._provider_key, retry_after, corr_id,
                    )

                    if attempt < policy.max_retries:
                        backoff = retry_after if retry_after is not None else policy.get_backoff(attempt)
                        await asyncio.sleep(backoff)
                        last_exception = RateLimitError(
                            f"Rate limited by {self._provider_key}",
                            provider_key=self._provider_key,
                            status_code=429,
                            response_body=response.text[:4096],
                            provider_request_id=provider_request_id,
                            correlation_id=corr_id,
                            retry_after=retry_after,
                            rate_limit_remaining=rate_limit_remaining,
                            rate_limit_reset=rate_limit_reset,
                        )
                        continue
                    raise RateLimitError(
                        f"Rate limited by {self._provider_key}",
                        provider_key=self._provider_key,
                        status_code=429,
                        response_body=response.text[:4096],
                        provider_request_id=provider_request_id,
                        correlation_id=corr_id,
                        retry_after=retry_after,
                        rate_limit_remaining=rate_limit_remaining,
                        rate_limit_reset=rate_limit_reset,
                    )

                # Retryable 5xx
                if response.status_code in policy.retry_on_status and attempt < policy.max_retries:
                    transport_logger.warning(
                        "Retryable error: status=%d correlation_id=%s attempt=%d",
                        response.status_code, corr_id, attempt,
                    )
                    backoff = policy.get_backoff(attempt)
                    await asyncio.sleep(backoff)
                    last_exception = ProviderAPIError(
                        f"Provider error: {response.status_code}",
                        provider_key=self._provider_key,
                        status_code=response.status_code,
                        response_body=response.text[:4096],
                        provider_request_id=(
                            response.headers.get("X-Request-ID")
                            or response.headers.get("Request-Id")
                        ),
                        correlation_id=corr_id,
                    )
                    continue

                # Non-retried error
                provider_request_id = (
                    response.headers.get("X-Request-ID")
                    or response.headers.get("Request-Id")
                )

                transport_logger.error(
                    "Provider API error: status=%d provider=%s correlation_id=%s",
                    response.status_code, self._provider_key, corr_id,
                )

                raise ProviderAPIError(
                    f"Provider {self._provider_key!r} returned {response.status_code}",
                    provider_key=self._provider_key,
                    status_code=response.status_code,
                    response_body=response.text[:4096],
                    provider_request_id=provider_request_id,
                    correlation_id=corr_id,
                )

        # Should not reach here, but handle exhausted retries
        if last_exception is not None:
            raise last_exception
        raise TransportError("Request failed after retries")  # pragma: no cover
