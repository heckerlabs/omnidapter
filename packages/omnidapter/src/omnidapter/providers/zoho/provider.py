from omnidapter.auth.kinds import AuthKind
from omnidapter.core.metadata import OAuthSupport, ProviderMetadata
from omnidapter.providers.base import InMemoryCalendarService, SimpleOAuthAdapter
from omnidapter.services.calendar.capabilities import CalendarCapability


class ZohoProvider:
    key = "zoho"

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            key=self.key,
            display_name="Zoho Calendar",
            services=["calendar"],
            auth_kinds=[AuthKind.OAUTH2],
            capabilities={"calendar": [CalendarCapability.LIST_CALENDARS, CalendarCapability.LIST_EVENTS, CalendarCapability.GET_EVENT]},
            oauth=OAuthSupport(supported=True, scope_groups={"calendar": ["ZohoCalendar.calendar.ALL"]}),
        )

    def calendar_service(self, connection_id, credential):
        return InMemoryCalendarService(self.key)

    def oauth_adapter(self):
        return SimpleOAuthAdapter(self.key)
