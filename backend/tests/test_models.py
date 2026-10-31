from app.db.base import TenantMixin
from app.models import AdminAgent, Administration, OwnerUser, PlatformAuditLog


def test_admin_agent_has_tenant_id_column() -> None:
    """Every business table must carry tenant_id (AGENTS.md règle 8)."""
    assert isinstance(AdminAgent(), TenantMixin)
    assert "tenant_id" in AdminAgent.__table__.columns


def test_administration_is_the_tenant_not_tenanted() -> None:
    assert "tenant_id" not in Administration.__table__.columns


def test_owner_tables_have_no_tenant_id() -> None:
    """OwnerUser/PlatformAuditLog are cross-tenant by design (docs/data-model.md §1)."""
    assert "tenant_id" not in OwnerUser.__table__.columns
    assert "tenant_id" not in PlatformAuditLog.__table__.columns
