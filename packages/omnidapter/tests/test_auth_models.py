"""
Unit tests for auth models.
"""
from datetime import datetime, timedelta, timezone

from omnidapter.auth.models import ApiKeyCredentials, BasicCredentials, OAuth2Credentials


class TestOAuth2Credentials:
    def test_not_expired_when_no_expiry(self):
        creds = OAuth2Credentials(access_token="tok")
        assert not creds.is_expired()

    def test_expired_when_past(self):
        past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        creds = OAuth2Credentials(access_token="tok", expires_at=past)
        assert creds.is_expired()

    def test_not_expired_when_future(self):
        future = datetime.now(tz=timezone.utc) + timedelta(hours=1)
        creds = OAuth2Credentials(access_token="tok", expires_at=future)
        assert not creds.is_expired()

    def test_expired_within_buffer(self):
        # Expires in 30 seconds, buffer is 60 — should be considered expired
        near_future = datetime.now(tz=timezone.utc) + timedelta(seconds=30)
        creds = OAuth2Credentials(access_token="tok", expires_at=near_future)
        assert creds.is_expired(buffer_seconds=60)

    def test_refreshable_with_refresh_token(self):
        creds = OAuth2Credentials(access_token="tok", refresh_token="ref")
        assert creds.is_refreshable()

    def test_not_refreshable_without_refresh_token(self):
        creds = OAuth2Credentials(access_token="tok")
        assert not creds.is_refreshable()


class TestApiKeyCredentials:
    def test_defaults(self):
        creds = ApiKeyCredentials(api_key="my-key")
        assert creds.api_key == "my-key"
        assert creds.header_name == "X-API-Key"


class TestBasicCredentials:
    def test_fields(self):
        creds = BasicCredentials(username="user", password="pass")
        assert creds.username == "user"
        assert creds.password == "pass"
