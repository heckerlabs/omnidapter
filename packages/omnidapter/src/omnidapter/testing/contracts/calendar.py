from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from omnidapter.services.calendar.models import EventTime, EventUpsertRequest


async def calendar_provider_contract(factory: Callable[[], Awaitable[object]]) -> None:
    service = await factory()
    calendars = await service.list_calendars()
    assert calendars
    now = datetime.now(timezone.utc)
    created = await service.create_event(
        EventUpsertRequest(
            calendar_id=calendars[0].id,
            summary="contract",
            start=EventTime(date_time=now),
            end=EventTime(date_time=now),
        )
    )
    loaded = await service.get_event(created.id)
    assert loaded.id == created.id
