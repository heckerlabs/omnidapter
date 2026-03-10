from omnidapter.auth.kinds import AuthKind
from omnidapter.core.metadata import OAuthSupport, ProviderMetadata
from omnidapter.providers.base import InMemoryCalendarService, SimpleOAuthAdapter
from omnidapter.services.calendar.capabilities import CalendarCapability


class GoogleProvider:
    key = "google"

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            key=self.key,
            display_name="Google Calendar",
            services=["calendar"],
            auth_kinds=[AuthKind.OAUTH2],
            capabilities={"calendar": [c for c in CalendarCapability if not c.name.startswith("BATCH_")]},
            oauth=OAuthSupport(supported=True, scope_groups={"calendar": ["calendar.read", "calendar.write"]}),
        )

    def calendar_service(self, connection_id, credential):
        return InMemoryCalendarService(self.key)

    def oauth_adapter(self):
        return SimpleOAuthAdapter(self.key)
