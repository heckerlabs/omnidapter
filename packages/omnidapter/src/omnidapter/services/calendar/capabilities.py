from enum import Enum


class CalendarCapability(str, Enum):
    LIST_CALENDARS = "list_calendars"
    GET_AVAILABILITY = "get_availability"
    CREATE_EVENT = "create_event"
    UPDATE_EVENT = "update_event"
    DELETE_EVENT = "delete_event"
    GET_EVENT = "get_event"
    LIST_EVENTS = "list_events"
    CREATE_WATCH = "create_watch"
    PARSE_WEBHOOK = "parse_webhook"
    CONFERENCE_LINKS = "conference_links"
    RECURRENCE = "recurrence"
    ATTENDEES = "attendees"
    BATCH_CREATE = "batch_create"
    BATCH_UPDATE = "batch_update"
    BATCH_DELETE = "batch_delete"
