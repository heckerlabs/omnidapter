"""
Calendar capability enumeration.
"""

from __future__ import annotations

from enum import Enum


class CalendarCapability(str, Enum):
    """Capabilities that a calendar provider may or may not support."""

    LIST_CALENDARS = "list_calendars"
    GET_AVAILABILITY = "get_availability"
    CREATE_EVENT = "create_event"
    UPDATE_EVENT = "update_event"
    DELETE_EVENT = "delete_event"
    GET_EVENT = "get_event"
    LIST_EVENTS = "list_events"
    CONFERENCE_LINKS = "conference_links"
    RECURRENCE = "recurrence"
    ATTENDEES = "attendees"

    # Reserved for future use — not implemented in v1
    BATCH_CREATE = "batch_create"
    BATCH_UPDATE = "batch_update"
    BATCH_DELETE = "batch_delete"
