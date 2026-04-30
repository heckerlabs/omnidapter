"""CRM capability enumeration."""

from __future__ import annotations

from enum import Enum


class CrmCapability(str, Enum):
    """Capabilities that a CRM provider may or may not support."""

    LIST_CONTACTS = "list_contacts"
    GET_CONTACT = "get_contact"
    CREATE_CONTACT = "create_contact"
    UPDATE_CONTACT = "update_contact"
    DELETE_CONTACT = "delete_contact"
    SEARCH_CONTACTS = "search_contacts"

    LIST_COMPANIES = "list_companies"
    GET_COMPANY = "get_company"
    CREATE_COMPANY = "create_company"
    UPDATE_COMPANY = "update_company"
    DELETE_COMPANY = "delete_company"

    LIST_DEALS = "list_deals"
    GET_DEAL = "get_deal"
    CREATE_DEAL = "create_deal"
    UPDATE_DEAL = "update_deal"
    DELETE_DEAL = "delete_deal"

    LIST_ACTIVITIES = "list_activities"
    CREATE_ACTIVITY = "create_activity"
    UPDATE_ACTIVITY = "update_activity"
    DELETE_ACTIVITY = "delete_activity"

    TAGS = "tags"
    WEBHOOKS = "webhooks"  # reserved — not supported in v1
