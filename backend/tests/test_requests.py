"""Smoke tests de POST /requests (docs/roadmap.md Phase 2, première tâche)."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.db import tenant_session, user_session
from app.main import app
from app.models import (
    Administration,
    AdministrationRole,
    DocumentRequest,
    DocumentRequestStatusHistory,
    ReferenceCheckResult,
    RequestStatus,
    TenantStatus,
    User,
    UserType,
)
from app.services.reference_check import get_reference_checker

pytestmark = pytest.mark.usefixtures("migrated_db")


class _DownChecker:
    """Vérificateur indisponible: la demande reste en pending_reference_check (état initial)."""

    async def check(self, *_: object) -> ReferenceCheckResult:
        raise ConnectionError


@pytest.fixture(autouse=True)
def _checker_down():  # type: ignore[no-untyped-def]
    app.dependency_overrides[get_reference_checker] = lambda: _DownChecker()
    yield
    app.dependency_overrides.clear()


BODY = {
    "document_type": "acte_naissance",
    "reference_document_id": "AN-1998-004512",
    "payload": {"motif": "renouvellement"},
}


async def _tenant(
    role: AdministrationRole = AdministrationRole.issuer,
    status: TenantStatus = TenantStatus.active,
) -> uuid.UUID:
    tid = uuid.uuid4()
    async with tenant_session(tid) as s:
        s.add(Administration(id=tid, name="Mairie", role=role, status=status))
    return tid


async def _user() -> uuid.UUID:
    uid = uuid.uuid4()
    async with user_session(uid) as s:
        s.add(User(id=uid, type=UserType.citizen, full_name="Awa", phone="+2250100000000"))
    return uid


async def _post(user: uuid.UUID | None, body: dict) -> object:  # type: ignore[type-arg]
    headers = {"X-Dev-User-Id": str(user)} if user else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.post("/requests", json=body, headers=headers)


async def test_create_request_returns_pending_reference_check() -> None:
    tenant, user = await _tenant(), await _user()
    r = await _post(user, {**BODY, "administration_id": str(tenant)})
    assert r.status_code == 201  # type: ignore[attr-defined]
    data = r.json()  # type: ignore[attr-defined]
    assert data["status"] == "pending_reference_check"
    assert data["amount_due"] == 1000

    async with user_session(user) as s:
        req = await s.get(DocumentRequest, uuid.UUID(data["id"]))
        assert req is not None and req.user_id == user and req.administration_id == tenant
        history = (await s.scalars(select(DocumentRequestStatusHistory))).all()
        assert [(h.from_status, h.to_status) for h in history] == [
            (None, RequestStatus.pending_reference_check)
        ]


async def test_requires_authentication() -> None:
    tenant = await _tenant()
    assert (await _post(None, {**BODY, "administration_id": str(tenant)})).status_code == 401  # type: ignore[attr-defined]
    # utilisateur inconnu en base
    r = await _post(uuid.uuid4(), {**BODY, "administration_id": str(tenant)})
    assert r.status_code == 401  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("role", "status"),
    [
        (AdministrationRole.verifier, TenantStatus.active),
        (AdministrationRole.issuer, TenantStatus.suspended),
    ],
)
async def test_unavailable_administration_is_404(
    role: AdministrationRole, status: TenantStatus
) -> None:
    tenant, user = await _tenant(role, status), await _user()
    r = await _post(user, {**BODY, "administration_id": str(tenant)})
    assert r.status_code == 404  # type: ignore[attr-defined]
    missing = await _post(user, {**BODY, "administration_id": str(uuid.uuid4())})
    assert missing.status_code == 404  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "patch",
    [
        {"reference_document_id": "x"},
        {"reference_document_id": "AN 1998; DROP TABLE"},
        {"document_type": "passeport"},
        {"payload": {"blob": "x" * 20_000}},
    ],
)
async def test_invalid_body_is_422(patch: dict) -> None:  # type: ignore[type-arg]
    tenant, user = await _tenant(), await _user()
    r = await _post(user, {**BODY, "administration_id": str(tenant), **patch})
    assert r.status_code == 422  # type: ignore[attr-defined]


async def test_isolation_between_users_and_tenants() -> None:
    t1, t2 = await _tenant(), await _tenant()
    u1, u2 = await _user(), await _user()
    req_id = uuid.UUID((await _post(u1, {**BODY, "administration_id": str(t1)})).json()["id"])  # type: ignore[attr-defined]

    async with user_session(u2) as s:  # autre citoyen
        assert await s.get(DocumentRequest, req_id) is None
        assert (await s.scalars(select(DocumentRequestStatusHistory))).all() == []
    async with tenant_session(t2) as s:  # autre tenant
        assert await s.get(DocumentRequest, req_id) is None
    async with tenant_session(t1) as s:  # tenant émetteur
        assert await s.get(DocumentRequest, req_id) is not None


async def test_cannot_forge_request_for_another_user() -> None:
    t, u1, u2 = await _tenant(), await _user(), await _user()
    with pytest.raises(DBAPIError, match="row-level security"):
        async with user_session(u1) as s:
            s.add(
                DocumentRequest(
                    user_id=u2,
                    administration_id=t,
                    document_type="car",  # type: ignore[arg-type]
                    reference_document_id="CAR-001",
                    status=RequestStatus.pending_reference_check,
                )
            )
            await s.flush()


async def test_status_history_is_append_only() -> None:
    t, u = await _tenant(), await _user()
    req_id = uuid.UUID((await _post(u, {**BODY, "administration_id": str(t)})).json()["id"])  # type: ignore[attr-defined]
    with pytest.raises(DBAPIError, match="permission denied"):
        async with user_session(u) as s:
            h = (await s.scalars(select(DocumentRequestStatusHistory))).one()
            assert h.document_request_id == req_id
            h.reason = "tamper"
            await s.flush()
