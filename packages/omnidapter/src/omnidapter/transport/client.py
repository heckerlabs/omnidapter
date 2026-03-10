from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from omnidapter.core.errors import ProviderAPIError, RateLimitError, TransportError
from omnidapter.transport.correlation import new_correlation_id


class TransportResponse:
    def __init__(self, status_code: int, body: str = "", headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}


Sender = Callable[[str, str, dict[str, str] | None, str | None], Awaitable[TransportResponse]]


class TransportClient:
    def __init__(self, provider_key: str, sender: Sender):
        self.provider_key = provider_key
        self.sender = sender

    async def request(self, method: str, url: str, headers: dict[str, str] | None = None, body: str | None = None) -> TransportResponse:
        correlation_id = new_correlation_id()
        try:
            response = await self.sender(method, url, headers, body)
        except Exception as exc:  # noqa: BLE001
            raise TransportError(str(exc)) from exc

        if response.status_code == 429:
            reset = response.headers.get("X-RateLimit-Reset")
            reset_dt = datetime.fromtimestamp(float(reset), tz=timezone.utc) if reset else None
            raise RateLimitError(
                "Provider rate limited request",
                provider_key=self.provider_key,
                correlation_id=correlation_id,
                retry_after=float(response.headers.get("Retry-After", "0")) if response.headers.get("Retry-After") else None,
                rate_limit_remaining=int(response.headers.get("X-RateLimit-Remaining", "0")) if response.headers.get("X-RateLimit-Remaining") else None,
                rate_limit_reset=reset_dt,
                response_body=response.body[:2000],
                provider_request_id=response.headers.get("X-Request-Id"),
            )

        if response.status_code >= 400:
            raise ProviderAPIError(
                "Provider API error",
                provider_key=self.provider_key,
                correlation_id=correlation_id,
                status_code=response.status_code,
                response_body=response.body[:2000],
                provider_request_id=response.headers.get("X-Request-Id"),
            )

        return response
