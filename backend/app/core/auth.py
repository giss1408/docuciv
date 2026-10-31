"""Authn/authz scaffolding for Phase 0.

Real OIDC token issuance (Keycloak/Auth0-like) is out of scope until the
identity provider is wired up in Phase 2+. What's implemented now is the
*shape* every endpoint must depend on, so no future endpoint can skip it:
JWT verification, per-tenant scoping, and an explicit, logged Owner path
that never reuses a tenant-scoped token (docs/security.md §4/§6).
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

_bearer_scheme = HTTPBearer(auto_error=True)

_ALGORITHM = "HS256"  # placeholder; production uses the OIDC provider's RS256 keys


class Role(StrEnum):
    issuer_agent = "issuer_agent"
    verifier_agent = "verifier_agent"
    tenant_admin = "tenant_admin"
    owner = "owner"


@dataclass(frozen=True)
class Principal:
    """The authenticated caller. `tenant_id` is None only for role=owner —
    every other role is bound to exactly one tenant, and that binding is
    re-checked on every request, not just at login (docs/security.md §4)."""

    subject_id: uuid.UUID
    role: Role
    tenant_id: uuid.UUID | None

    def __post_init__(self) -> None:
        if self.role is Role.owner and self.tenant_id is not None:
            raise ValueError("Owner principal must never carry a tenant_id")
        if self.role is not Role.owner and self.tenant_id is None:
            raise ValueError(f"Role {self.role} must be bound to a tenant_id")


def decode_principal(token: str) -> Principal:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc

    try:
        role = Role(payload["role"])
        subject_id = uuid.UUID(payload["sub"])
        tenant_id_raw = payload.get("tenant_id")
        tenant_id = uuid.UUID(tenant_id_raw) if tenant_id_raw else None
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token claims"
        ) from exc

    try:
        return Principal(subject_id=subject_id, role=role, tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Inconsistent token claims"
        ) from exc


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> Principal:
    return decode_principal(credentials.credentials)


def require_role(*allowed: Role):
    """Function-level authorization dependency (docs/security.md §2 "Broken
    function level authorization") — checked server-side on every call, never
    only enforced by hiding a button in the Flutter client."""

    async def _check(principal: Principal = Depends(get_current_principal)) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return principal

    return _check


require_owner = require_role(Role.owner)
require_tenant_admin = require_role(Role.tenant_admin, Role.owner)
require_issuer_agent = require_role(Role.issuer_agent, Role.tenant_admin)
require_verifier_agent = require_role(Role.verifier_agent, Role.tenant_admin)
