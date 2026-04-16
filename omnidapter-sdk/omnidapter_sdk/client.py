from omnidapter_sdk.api_client import ApiClient
from omnidapter_sdk.configuration import Configuration
from omnidapter_sdk.api.calendar_api import CalendarApi
from omnidapter_sdk.api.connections_api import ConnectionsApi
from omnidapter_sdk.api.link_tokens_api import LinkTokensApi
from omnidapter_sdk.api.providers_api import ProvidersApi


class OmnidapterClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        config = Configuration(host=base_url, access_token=api_key)
        client = ApiClient(configuration=config)
        self.calendar = CalendarApi(client)
        self.connections = ConnectionsApi(client)
        self.link_tokens = LinkTokensApi(client)
        self.providers = ProvidersApi(client)
