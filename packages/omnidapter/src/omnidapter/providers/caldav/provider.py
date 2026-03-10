from omnidapter.auth.kinds import AuthKind
from omnidapter.core.metadata import OAuthSupport, ProviderMetadata
from omnidapter.providers.base import InMemoryCalendarService
from omnidapter.services.calendar.capabilities import CalendarCapability


class CaldavProvider:
    key = "caldav"

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            key=self.key,
            display_name="CalDAV",
            services=["calendar"],
            auth_kinds=[AuthKind.BASIC],
            capabilities={"calendar": [CalendarCapability.LIST_CALENDARS, CalendarCapability.LIST_EVENTS, CalendarCapability.GET_EVENT]},
            oauth=OAuthSupport(supported=False),
            config_requirements=["server_url"],
        )

    def calendar_service(self, connection_id, credential):
        return InMemoryCalendarService(self.key)

    def oauth_adapter(self):
        return None
