"""Unit tests for hosted model structure."""

from __future__ import annotations

from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.membership import HostedMembership, MemberRole
from omnidapter_hosted.models.tenant import Tenant, TenantPlan
from omnidapter_hosted.models.usage import HostedUsageRecord
from omnidapter_hosted.models.user import HostedUser


def test_tenant_plan_values():
    assert TenantPlan.FREE == "free"
    assert TenantPlan.PAYG == "payg"


def test_member_role_values():
    assert MemberRole.OWNER == "owner"
    assert MemberRole.ADMIN == "admin"
    assert MemberRole.MEMBER == "member"


def test_tenant_tablename():
    assert Tenant.__tablename__ == "tenants"


def test_user_tablename():
    assert HostedUser.__tablename__ == "users"


def test_membership_tablename():
    assert HostedMembership.__tablename__ == "memberships"


def test_api_key_tablename():
    assert HostedAPIKey.__tablename__ == "hosted_api_keys"


def test_usage_record_tablename():
    assert HostedUsageRecord.__tablename__ == "hosted_usage_records"


def test_hosted_models_use_hosted_base():
    from omnidapter_hosted.database import HostedBase

    assert issubclass(Tenant, HostedBase)
    assert issubclass(HostedUser, HostedBase)
    assert issubclass(HostedMembership, HostedBase)
    assert issubclass(HostedAPIKey, HostedBase)
