"""Connexion jetable de démonstration (à remplacer par l'OIDC).

Sûreté: inactive tant que `demo_mode` est faux (le routeur répond 404), refusée en production
(validateur de config), protégée par un code d'accès, et les jetons sont signés (HMAC-SHA256) et
expirent. Les comptes sont des comptes de démo fixes: aucune donnée réelle.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.db import tenant_session, user_session
from app.models import (
    AdminAgent,
    Administration,
    AdministrationRole,
    AgentRole,
    User,
    UserType,
)

log = structlog.get_logger()

_NS = uuid.UUID("5f0c1a2e-0d3c-4a55-9d7e-d0c0c1d1e000")
DEMO_TENANT_ID = uuid.uuid5(_NS, "tenant")
DEMO_AGENT_ID = uuid.uuid5(_NS, "agent")
DEMO_CITIZEN_ID = uuid.uuid5(_NS, "citizen")


@dataclass(frozen=True)
class Claims:
    kind: Literal["citizen", "agent"]
    user_id: uuid.UUID
    tenant_id: uuid.UUID | None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret: str, body: str) -> str:
    return _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())


def make_token(settings: Settings, claims: Claims, now: float | None = None) -> tuple[str, int]:
    exp = int((now or time.time()) + settings.demo_token_ttl_minutes * 60)
    body = _b64(
        json.dumps(
            {
                "k": claims.kind,
                "u": str(claims.user_id),
                "t": str(claims.tenant_id) if claims.tenant_id else None,
                "exp": exp,
            },
            separators=(",", ":"),
        ).encode()
    )
    assert settings.demo_token_secret is not None
    return f"{body}.{_sign(settings.demo_token_secret, body)}", exp


def read_token(settings: Settings, token: str, now: float | None = None) -> Claims | None:
    """Claims si le jeton est authentique et non expiré, sinon None (jamais d'exception)."""
    if not settings.demo_mode or not settings.demo_token_secret:
        return None
    try:
        body, signature = token.split(".", 1)
        if not hmac.compare_digest(signature, _sign(settings.demo_token_secret, body)):
            return None
        data = json.loads(_unb64(body))
        if data["exp"] < (now or time.time()) or data["k"] not in ("citizen", "agent"):
            return None
        tenant = uuid.UUID(data["t"]) if data.get("t") else None
        return Claims(data["k"], uuid.UUID(data["u"]), tenant)
    except (ValueError, KeyError, TypeError):
        return None


async def seed_demo(settings: Settings) -> None:
    """Crée (idempotent) l'administration, l'agent et le citoyen de démonstration."""
    async with tenant_session(DEMO_TENANT_ID) as s:
        if await s.get(Administration, DEMO_TENANT_ID) is None:
            s.add(
                Administration(
                    id=DEMO_TENANT_ID,
                    name="Mairie de Cocody (démo)",
                    role=AdministrationRole.issuer,
                )
            )
            await s.flush()
        if await s.get(AdminAgent, DEMO_AGENT_ID) is None:
            s.add(
                AdminAgent(
                    id=DEMO_AGENT_ID,
                    tenant_id=DEMO_TENANT_ID,
                    full_name="Agent Démo",
                    email="agent.demo@docuciv.invalid",
                    role=AgentRole.issuer_agent,
                )
            )
    async with user_session(DEMO_CITIZEN_ID) as s:
        citizen = await s.get(User, DEMO_CITIZEN_ID)
        if citizen is None:
            s.add(
                User(
                    id=DEMO_CITIZEN_ID,
                    type=UserType.citizen,
                    full_name="Citoyen Démo",
                    phone=settings.demo_citizen_phone,
                )
            )
        else:
            citizen.phone = settings.demo_citizen_phone
    log.info("demo_seeded")


router = APIRouter(prefix="/demo", tags=["demo"])


class LoginIn(BaseModel):
    role: Literal["citizen", "agent"]
    access_code: str


class LoginOut(BaseModel):
    token: str
    role: str
    expires_at: datetime


@router.post("/login", response_model=LoginOut)
async def demo_login(
    body: LoginIn, settings: Annotated[Settings, Depends(get_settings)]
) -> LoginOut:
    if not settings.demo_mode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")  # n'existe pas hors démo
    assert settings.demo_access_code is not None
    if not hmac.compare_digest(body.access_code.encode(), settings.demo_access_code.encode()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid_access_code")
    await seed_demo(settings)
    claims = (
        Claims("citizen", DEMO_CITIZEN_ID, None)
        if body.role == "citizen"
        else Claims("agent", DEMO_AGENT_ID, DEMO_TENANT_ID)
    )
    token, exp = make_token(settings, claims)
    return LoginOut(token=token, role=body.role, expires_at=datetime.fromtimestamp(exp, UTC))


if __name__ == "__main__":
    asyncio.run(seed_demo(get_settings()))
