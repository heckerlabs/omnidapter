"""Omnidapter Python SDK — top-level client and connection-scoped helpers.

Architecture — connection-scoped API
-------------------------------------
Every service added to Omnidapter (calendar, booking, …) follows a three-part
convention that keeps ``client.py`` minimal and zero-maintenance:

1. **Router operationIds are domain-prefixed.**
   Every route in a service router carries a ``<domain>_`` prefix on its
   ``operation_id``, e.g. ``booking_cancel_booking``, ``calendar_list_events``.
   This guarantees global uniqueness across the OpenAPI spec without any manual
   collision management.

2. **The generated SDK method names mirror the operationId.**
   The generator produces ``BookingApi.booking_cancel_booking``,
   ``CalendarApi.calendar_list_events``, etc.

3. **The prefix is stripped at access time — on both the flat and scoped APIs.**
   :class:`PrefixStrippingApi` strips ``<domain>_`` so callers never see the
   redundant prefix.  :class:`BoundServiceApi` extends it to also bake in a
   ``connection_id``::

       # Flat — connection_id passed explicitly
       omni.booking.cancel_booking(connection_id, appt_id)
       # → BookingApi.booking_cancel_booking(connection_id, appt_id)

       # Scoped — connection_id baked in
       conn.booking.cancel_booking(appt_id)
       # → BookingApi.booking_cancel_booking(connection_id, appt_id)

Adding a new service
--------------------
1. Add routes to the new service router with ``operation_id="<domain>_<name>"``.
2. Re-export the OpenAPI spec and regenerate the SDK.
3. Add **one line** to :class:`OmnidapterClient.__init__` (flat API)::

       self.<domain> = PrefixStrippingApi(<Domain>Api(client), "<domain>")

4. Add **one line** to :class:`ConnectionClient.__init__` (scoped API)::

       self.<domain> = BoundServiceApi(connection_id, <domain>_api, "<domain>")

That's it. No rename maps, no per-service classes.
"""

from __future__ import annotations

import functools
from typing import Any

from omnidapter_sdk.api.booking_api import BookingApi
from omnidapter_sdk.api.calendar_api import CalendarApi
from omnidapter_sdk.api.connections_api import ConnectionsApi
from omnidapter_sdk.api.link_tokens_api import LinkTokensApi
from omnidapter_sdk.api.providers_api import ProvidersApi
from omnidapter_sdk.api_client import ApiClient
from omnidapter_sdk.configuration import Configuration


class PrefixStrippingApi:
    """A proxy for a generated service API that strips the domain prefix from method names.

    All operationIds in the spec are prefixed with ``<domain>_`` (e.g.
    ``booking_cancel_booking``, ``calendar_list_events``) to ensure global
    uniqueness.  This class strips that prefix so callers use the short name
    instead, while still passing ``connection_id`` explicitly::

        omni.booking.cancel_booking(connection_id, appt_id)
        omni.calendar.list_events(connection_id, calendar_id="primary")

    :class:`BoundServiceApi` extends this to also bake in ``connection_id``.

    Args:
        api: The generated ``*Api`` instance to proxy.
        prefix: The domain prefix to strip (e.g. ``"booking"`` or ``"calendar"``).
    """

    def __init__(self, api: Any, prefix: str) -> None:
        self._api = api
        self._prefix = f"{prefix}_"

    def __getattr__(self, name: str) -> Any:
        method = (
            getattr(self._api, f"{self._prefix}{name}", None)
            or getattr(self._api, name, None)
        )
        if method is None or not callable(method):
            raise AttributeError(
                f"{type(self).__name__!r} ({self._prefix[:-1]!r}) has no attribute {name!r}"
            )
        return method

    def __dir__(self) -> list[str]:
        return sorted(
            n[len(self._prefix):] if n.startswith(self._prefix) else n
            for n in dir(self._api)
            if not n.startswith("_")
        )


class BoundServiceApi(PrefixStrippingApi):
    """A connection-scoped proxy that strips the domain prefix and bakes in ``connection_id``.

    Extends :class:`PrefixStrippingApi` so that ``connection_id`` is prepended
    automatically on every call::

        conn.booking.cancel_booking(appt_id)   # booking_cancel_booking → cancel_booking
        conn.calendar.list_events("primary")   # calendar_list_events → list_events

    When a new service type is added (e.g. ``crm``), add one line to
    :class:`ConnectionClient` — no changes needed here.

    Args:
        connection_id: Baked into every call as the first positional argument.
        api: The generated ``*Api`` instance to proxy.
        prefix: The domain prefix to strip (e.g. ``"booking"`` or ``"calendar"``).
    """

    def __init__(self, connection_id: str, api: Any, prefix: str) -> None:
        super().__init__(api, prefix)
        self._connection_id = connection_id

    def __getattr__(self, name: str) -> Any:
        method = super().__getattr__(name)

        @functools.wraps(method)
        def bound(*args: Any, **kwargs: Any) -> Any:
            return method(self._connection_id, *args, **kwargs)

        bound.__name__ = name
        return bound


class ConnectionClient:
    """A connection-scoped client returned by :meth:`OmnidapterClient.connection`.

    Each service attribute has ``connection_id`` baked in and strips the
    domain prefix from method names (``booking_cancel_booking`` →
    ``cancel_booking``, ``calendar_list_events`` → ``list_events``).

    To add a new service, add one attribute here pointing at the new generated
    ``*Api`` class and its domain prefix — nothing else needs to change.

    Attributes:
        booking: Booking operations for this connection.
        calendar: Calendar operations for this connection.

    Example::

        conn = omni.connection("conn_abc123")

        # Booking
        services = conn.booking.list_services()
        slots    = conn.booking.availability("svc_1", start=..., end=...)
        appt     = conn.booking.create_booking(CreateBookingRequest(...))
        conn.booking.cancel_booking(appt.data.id)

        # Calendar
        events = conn.calendar.list_events("primary", start=..., end=...)
        conn.calendar.create_event("primary", CreateEventRequest(...))
    """

    def __init__(
        self,
        connection_id: str,
        booking_api: BookingApi,
        calendar_api: CalendarApi,
    ) -> None:
        # To add a new service:
        #   1. Prefix its router operationIds with "<domain>_".
        #   2. Re-export the spec and regenerate the SDK.
        #   3. Add one line here:
        #        self.<domain> = BoundServiceApi(connection_id, <domain>_api, "<domain>")
        self.booking = BoundServiceApi(connection_id, booking_api, "booking")
        self.calendar = BoundServiceApi(connection_id, calendar_api, "calendar")


class OmnidapterClient:
    """Top-level client for the Omnidapter REST API.

    Args:
        base_url: Base URL of your Omnidapter server
            (e.g. ``"http://localhost:8000"``).
        api_key: API key configured via ``OMNIDAPTER_API_KEY`` on the server.

    There are two usage styles:

    **Flat** — pass ``connection_id`` as the first argument to every call.
    Convenient when working with multiple connections in the same code path::

        omni = OmnidapterClient(base_url="http://localhost:8000", api_key="...")

        omni.booking.cancel_booking(connection_id, appointment_id)
        omni.calendar.list_events(connection_id, calendar_id="primary")

    **Connection-scoped** — call :meth:`connection` to get a bound client that
    omits ``connection_id`` and strips the domain prefix from method names::

        conn = omni.connection(connection_id)

        conn.booking.cancel_booking(appointment_id)
        conn.calendar.list_events("primary")

    Attributes:
        booking: Booking operations (prefix-stripped, ``connection_id`` required).
        calendar: Calendar operations (prefix-stripped, ``connection_id`` required).
        connections: :class:`ConnectionsApi` — create, list, get, delete, and
            reauthorize connections.
        link_tokens: :class:`LinkTokensApi` — create short-lived link tokens
            for the hosted Connect UI.
        providers: :class:`ProvidersApi` — inspect provider metadata and
            supported capabilities.
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        config = Configuration(host=base_url, access_token=api_key)
        client = ApiClient(configuration=config)
        # To add a new service:
        #   1. Prefix its router operationIds with "<domain>_".
        #   2. Re-export the spec and regenerate the SDK.
        #   3. Add one line here:
        #        self.<domain> = PrefixStrippingApi(<Domain>Api(client), "<domain>")
        self.booking = PrefixStrippingApi(BookingApi(client), "booking")
        self.calendar = PrefixStrippingApi(CalendarApi(client), "calendar")
        self.connections = ConnectionsApi(client)
        self.link_tokens = LinkTokensApi(client)
        self.providers = ProvidersApi(client)

    def connection(self, connection_id: str) -> ConnectionClient:
        """Return a connection-scoped client with *connection_id* baked in.

        Method names on ``conn.booking`` and ``conn.calendar`` have the domain
        prefix stripped (``booking_cancel_booking`` → ``cancel_booking``).

        Args:
            connection_id: The connection to scope operations to.

        Returns:
            :class:`ConnectionClient` with ``.booking`` and ``.calendar``
            pre-bound to *connection_id*.

        Example::

            conn = omni.connection("conn_abc123")
            conn.booking.cancel_booking(appt_id)
            conn.calendar.list_events("primary")
        """
        return ConnectionClient(
            connection_id,
            self.booking._api,
            self.calendar._api,
        )
