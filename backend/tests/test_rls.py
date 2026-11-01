"""Smoke test d'isolation inter-tenants (BOLA) au niveau base: deux tenants factices."""

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db import tenant_session
from app.models import AdminAgent, Administration, AdministrationRole, AgentRole

pytestmark = pytest.mark.usefixtures("migrated_db")


async def _seed(tenant_id: uuid.UUID, name: str) -> uuid.UUID:
    async with tenant_session(tenant_id) as s:
        s.add(Administration(id=tenant_id, name=name, role=AdministrationRole.issuer))
        await s.flush()
        agent = AdminAgent(
            tenant_id=tenant_id, full_name=name, email=f"{name}@x.ci", role=AgentRole.tenant_admin
        )
        s.add(agent)
        await s.flush()
        return agent.id


async def test_tenant_cannot_read_other_tenant() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    agent_a = await _seed(a, "a")
    await _seed(b, "b")

    async with tenant_session(b) as s:
        agents = (await s.scalars(select(AdminAgent))).all()
        assert {x.tenant_id for x in agents} == {b}
        assert await s.get(AdminAgent, agent_a) is None
        assert (await s.scalars(select(Administration.id))).all() == [b]


async def test_tenant_cannot_write_into_other_tenant() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed(a, "a2")
    await _seed(b, "b2")
    with pytest.raises(DBAPIError):
        async with tenant_session(b) as s:
            s.add(
                AdminAgent(tenant_id=a, full_name="x", email="x@x.ci", role=AgentRole.tenant_admin)
            )
            await s.flush()


async def test_no_tenant_context_sees_nothing() -> None:
    await _seed(uuid.uuid4(), "c")
    async with tenant_session(uuid.uuid4()) as s:
        await s.execute(text("SELECT set_config('app.tenant_id', '', true)"))
        assert (await s.scalars(select(AdminAgent))).all() == []
