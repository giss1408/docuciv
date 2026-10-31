import uuid

import jwt
import pytest

from app.core.auth import Principal, Role, decode_principal
from app.core.config import settings


def _token(**claims) -> str:
    return jwt.encode(claims, settings.secret_key, algorithm="HS256")


def test_decode_valid_tenant_principal() -> None:
    tenant_id = uuid.uuid4()
    subject_id = uuid.uuid4()
    token = _token(sub=str(subject_id), role="issuer_agent", tenant_id=str(tenant_id))

    principal = decode_principal(token)

    assert principal.role is Role.issuer_agent
    assert principal.tenant_id == tenant_id


def test_decode_valid_owner_principal_has_no_tenant() -> None:
    token = _token(sub=str(uuid.uuid4()), role="owner")

    principal = decode_principal(token)

    assert principal.role is Role.owner
    assert principal.tenant_id is None


def test_decode_rejects_invalid_signature() -> None:
    bad_token = jwt.encode(
        {"sub": str(uuid.uuid4()), "role": "owner"},
        "wrong-secret-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        algorithm="HS256",
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        decode_principal(bad_token)
    assert exc_info.value.status_code == 401


def test_decode_rejects_unknown_role() -> None:
    from fastapi import HTTPException

    token = _token(sub=str(uuid.uuid4()), role="superuser", tenant_id=str(uuid.uuid4()))
    with pytest.raises(HTTPException) as exc_info:
        decode_principal(token)
    assert exc_info.value.status_code == 401


def test_tenant_role_without_tenant_id_is_rejected() -> None:
    """A non-owner role must always be bound to a tenant (docs/security.md §4)."""
    with pytest.raises(ValueError):
        Principal(subject_id=uuid.uuid4(), role=Role.issuer_agent, tenant_id=None)


def test_owner_role_with_tenant_id_is_rejected() -> None:
    """Owner must never carry a tenant_id — it's the cross-tenant role (docs/security.md §4/§6)."""
    with pytest.raises(ValueError):
        Principal(subject_id=uuid.uuid4(), role=Role.owner, tenant_id=uuid.uuid4())
