import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings
from app.db import tenant_session
from app.demo import read_token
from app.models import AdminAgent, Administration, AdministrationRole, AgentRole, TenantStatus


@dataclass(frozen=True)
class Principal:
    """Citoyen/entreprise authentifié. L'identité vient toujours du jeton, jamais du corps."""

    user_id: uuid.UUID


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


async def get_principal(
    settings: Annotated[Settings, Depends(get_settings)],
    x_dev_user_id: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    token = _bearer(authorization)
    if token and settings.demo_mode:
        claims = read_token(settings, token)
        if claims is not None and claims.kind == "citizen":
            return Principal(user_id=claims.user_id)
    # OIDC (docs/architecture.md §1) n'est pas encore implémenté. Fail closed: hors dev, aucune
    # requête n'est authentifiée; l'en-tête de dev n'est honoré qu'en environnement dev.
    if settings.environment != "dev" or x_dev_user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication_required")
    try:
        return Principal(user_id=uuid.UUID(x_dev_user_id))
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication_required") from None


@dataclass(frozen=True)
class AgentPrincipal:
    """Agent d'une administration. Le tenant vient du jeton, jamais du chemin ni du corps."""

    agent_id: uuid.UUID
    tenant_id: uuid.UUID
    role: AgentRole


async def get_issuer_agent(
    settings: Annotated[Settings, Depends(get_settings)],
    x_dev_agent_id: Annotated[str | None, Header()] = None,
    x_dev_tenant_id: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> AgentPrincipal:
    """Agent habilité à instruire les demandes (issuer_agent ou tenant_admin) d'un tenant actif.

    Fail closed comme `get_principal`: l'OIDC remplacera les en-têtes de dev.
    """
    token = _bearer(authorization)
    claims = read_token(settings, token) if token and settings.demo_mode else None
    if claims is not None and claims.kind == "agent" and claims.tenant_id is not None:
        agent_id, tenant_id = claims.user_id, claims.tenant_id
    else:
        if settings.environment != "dev" or not x_dev_agent_id or not x_dev_tenant_id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication_required")
        try:
            agent_id, tenant_id = uuid.UUID(x_dev_agent_id), uuid.UUID(x_dev_tenant_id)
        except ValueError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication_required") from None

    async with tenant_session(
        tenant_id
    ) as session:  # RLS: un agent d'un autre tenant est invisible
        agent = await session.get(AdminAgent, agent_id)
        tenant = await session.get(Administration, tenant_id)
    if agent is None or tenant is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication_required")
    if (
        tenant.status != TenantStatus.active
        or tenant.role == AdministrationRole.verifier
        or agent.role == AgentRole.verifier_agent
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")
    return AgentPrincipal(agent_id=agent.id, tenant_id=tenant_id, role=agent.role)
