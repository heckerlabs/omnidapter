"""
Transport hooks for logging, tracing, metrics, and request/response inspection.

Hooks are optional and leave room for future middleware extensions.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequestHookContext:
    """Context passed to request hooks."""

    method: str
    url: str
    headers: dict[str, str]
    correlation_id: str
    provider_key: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResponseHookContext:
    """Context passed to response hooks."""

    method: str
    url: str
    status_code: int
    correlation_id: str
    provider_key: str
    elapsed_ms: float
    extra: dict[str, Any] = field(default_factory=dict)


# Type aliases for hook callables
RequestHook = Callable[[RequestHookContext], None | Awaitable[None]]
ResponseHook = Callable[[ResponseHookContext], None | Awaitable[None]]


class TransportHooks:
    """Collection of transport hooks."""

    def __init__(
        self,
        on_request: list[RequestHook] | None = None,
        on_response: list[ResponseHook] | None = None,
    ) -> None:
        self.on_request: list[RequestHook] = on_request or []
        self.on_response: list[ResponseHook] = on_response or []

    async def fire_request(self, ctx: RequestHookContext) -> None:
        import inspect

        for hook in self.on_request:
            result = hook(ctx)
            if inspect.isawaitable(result):
                await result

    async def fire_response(self, ctx: ResponseHookContext) -> None:
        import inspect

        for hook in self.on_response:
            result = hook(ctx)
            if inspect.isawaitable(result):
                await result
