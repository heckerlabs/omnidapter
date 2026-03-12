"""Unit tests for Microsoft calendar service payload handling."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.microsoft.calendar import MicrosoftCalendarService
from omnidapter.services.calendar.models import (
    ConferenceData,
    EventStatus,
    EventVisibility,
    Recurrence,
    Reminder,
    ReminderOverride,
)
from omnidapter.services.calendar.requests import CreateEventRequest, UpdateEventRequest
from omnidapter.stores.credentials import StoredCredential


def _stored(access_token: str = "ms-token") -> StoredCredential:
    return StoredCredential(
        provider_key="microsoft",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token=access_token),
    )


def _make_service() -> tuple[MicrosoftCalendarService, AsyncMock]:
    svc = MicrosoftCalendarService("conn-1", _stored())
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "id": "evt-1",
        "subject": "Updated",
        "start": {"dateTime": "2024-06-15T10:00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2024-06-15T11:00:00", "timeZone": "UTC"},
        "showAs": "normal",
    }
    svc._http.request = AsyncMock(return_value=mock_response)
    return svc, svc._http.request


class TestUpdateEventPayload:
    async def test_update_serializes_supported_fields(self):
        svc, mock_request = _make_service()
        recurrence = Recurrence(
            provider_data={"pattern": {"type": "daily", "interval": 1}, "range": {"type": "noEnd"}}
        )
        reminders = Reminder(
            use_default=False,
            overrides=[ReminderOverride(method="popup", minutes_before=30)],
        )

        await svc.update_event(
            UpdateEventRequest(
                calendar_id="cal-1",
                event_id="evt-1",
                all_day=True,
                status=EventStatus.TENTATIVE,
                visibility=EventVisibility.PRIVATE.value,
                recurrence=recurrence,
                conference_data=ConferenceData(),
                reminders=reminders,
            )
        )

        _, kwargs = mock_request.call_args
        body = kwargs["json"]
        assert body["isAllDay"] is True
        assert body["showAs"] == "tentative"
        assert body["sensitivity"] == "private"
        assert body["recurrence"]["pattern"]["type"] == "daily"
        assert body["isOnlineMeeting"] is True
        assert body["onlineMeetingProvider"] == "teamsForBusiness"
        assert body["isReminderOn"] is True
        assert body["reminderMinutesBeforeStart"] == 30


class TestCreateEventValidation:
    async def test_create_recurrence_without_provider_data_raises(self):
        svc, _ = _make_service()
        with pytest.raises(ValueError, match="provider_data"):
            await svc.create_event(
                CreateEventRequest(
                    calendar_id="cal-1",
                    summary="Recurring",
                    start=datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
                    end=datetime(2024, 6, 15, 11, 0, tzinfo=timezone.utc),
                    recurrence=Recurrence(rules=["RRULE:FREQ=DAILY"]),
                )
            )
