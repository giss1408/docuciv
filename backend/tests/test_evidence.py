"""Smoke tests upload de pièce justificative (docs/security.md §2bis, roadmap Phase 2)."""

import io
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import select

from app.config import Settings, get_settings
from app.db import tenant_session, user_session
from app.main import app
from app.models import (
    Administration,
    AdministrationRole,
    NotificationChannel,
    NotificationEvent,
    ReferenceCheckResult,
    SourceEvidence,
    UploadStatus,
    User,
    UserType,
)
from app.services.antivirus import ScanUnavailableError, get_scanner
from app.services.reference_check import get_reference_checker
from app.services.storage import PresignedUpload, get_storage

pytestmark = pytest.mark.usefixtures("migrated_db")


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.presigned: list[tuple[str, str, int]] = []

    async def presign_upload(
        self, key: str, content_type: str, max_bytes: int, ttl_seconds: int
    ) -> PresignedUpload:
        self.presigned.append((key, content_type, max_bytes))
        return PresignedUpload(url="https://s3.test/bucket", fields={"key": key})

    async def size(self, key: str) -> int | None:
        return len(self.objects[key]) if key in self.objects else None

    async def read(self, key: str) -> bytes:
        return self.objects[key]

    async def write(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)


class StubScanner:
    def __init__(self, clean: bool = True, down: bool = False) -> None:
        self.clean, self.down = clean, down

    async def is_clean(self, data: bytes) -> bool:
        if self.down:
            raise ScanUnavailableError
        return self.clean


class _Found:
    async def check(self, *_: object) -> ReferenceCheckResult:
        return ReferenceCheckResult.found


@pytest.fixture
def storage() -> MemoryStorage:
    s = MemoryStorage()
    app.dependency_overrides[get_storage] = lambda: s
    app.dependency_overrides[get_scanner] = lambda: StubScanner()
    app.dependency_overrides[get_reference_checker] = lambda: _Found()
    yield s  # type: ignore[misc]
    app.dependency_overrides.clear()


def jpeg_with_exif(size: tuple[int, int] = (32, 32)) -> bytes:
    img = Image.new("RGB", size, "white")
    exif = Image.Exif()
    exif[0x010F] = "SecretPhoneMaker"  # Make
    exif[0x8825] = {1: "N", 2: (5.0, 20.0, 0.0), 3: "W", 4: (4.0, 1.0, 0.0)}  # GPS
    out = io.BytesIO()
    img.save(out, "JPEG", exif=exif)
    return out.getvalue()


def png_bytes() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(out, "PNG")
    return out.getvalue()


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _setup() -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    """Demande déjà en pending_payment (référence trouvée). Retourne (request, user, headers)."""
    tid, uid = uuid.uuid4(), uuid.uuid4()
    async with tenant_session(tid) as s:
        s.add(Administration(id=tid, name="Mairie", role=AdministrationRole.issuer))
    async with user_session(uid) as s:
        s.add(User(id=uid, type=UserType.citizen, full_name="Awa", phone="+2250100000000"))
    headers = {"X-Dev-User-Id": str(uid)}
    async with await _client() as c:
        r = await c.post(
            "/requests",
            json={
                "administration_id": str(tid),
                "document_type": "acte_naissance",
                "reference_document_id": "AN-1998-004512",
            },
            headers=headers,
        )
    return uuid.UUID(r.json()["id"]), uid, headers


async def _upload_url(
    rid: uuid.UUID, headers: dict[str, str], mime: str = "image/jpeg", size: int = 1000
):  # type: ignore[no-untyped-def]
    async with await _client() as c:
        return await c.post(
            f"/requests/{rid}/evidence/upload-url",
            json={"mime_type": mime, "file_size_bytes": size},
            headers=headers,
        )


async def _complete(rid: uuid.UUID, eid: str, headers: dict[str, str]):  # type: ignore[no-untyped-def]
    async with await _client() as c:
        return await c.post(f"/requests/{rid}/evidence/{eid}/complete", headers=headers)


async def _put_and_complete(
    storage: MemoryStorage,
    rid: uuid.UUID,
    headers: dict[str, str],
    data: bytes,
    mime: str = "image/jpeg",
):  # type: ignore[no-untyped-def]
    eid = (await _upload_url(rid, headers, mime, len(data))).json()["evidence_id"]
    key = storage.presigned[-1][0]
    storage.objects[key] = data
    return eid, await _complete(rid, eid, headers)


async def _events(rid: uuid.UUID, uid: uuid.UUID) -> set[tuple[str, NotificationChannel]]:
    async with user_session(uid) as s:
        rows = await s.scalars(
            select(NotificationEvent).where(NotificationEvent.document_request_id == rid)
        )
        return {(e.event_type, e.channel) for e in rows}


async def test_upload_url_creates_evidence_with_size_cap(storage: MemoryStorage) -> None:
    rid, uid, h = await _setup()
    r = await _upload_url(rid, h)
    assert r.status_code == 201
    body = r.json()
    assert body["upload_url"].startswith("https://") and body["expires_in"] == 300
    key, mime, cap = storage.presigned[0]
    assert key.endswith("/raw") and mime == "image/jpeg" and cap == 10 * 1024 * 1024
    async with user_session(uid) as s:
        ev = await s.get(SourceEvidence, uuid.UUID(body["evidence_id"]))
        assert ev is not None and ev.upload_status == UploadStatus.awaiting_upload
        assert ev.review_status is None


@pytest.mark.parametrize(
    ("mime", "size"),
    [
        ("text/html", 100),
        ("application/x-msdownload", 100),
        ("image/jpeg", 11 * 1024 * 1024),
        ("image/jpeg", 0),
    ],
)
async def test_upload_url_rejects_bad_declaration(
    storage: MemoryStorage, mime: str, size: int
) -> None:
    rid, _, h = await _setup()
    assert (await _upload_url(rid, h, mime, size)).status_code == 422
    assert storage.presigned == []


async def test_upload_url_requires_accepting_status_and_limits(storage: MemoryStorage) -> None:
    rid, _, h = await _setup()
    for _ in range(5):
        assert (await _upload_url(rid, h)).status_code == 201
    assert (await _upload_url(rid, h)).status_code == 409  # plafond par demande

    app.dependency_overrides[get_reference_checker] = lambda: type(
        "Down", (), {"check": staticmethod(lambda *a: (_ for _ in ()).throw(OSError))}
    )()
    rid2, _, h2 = await _setup()  # reste en pending_reference_check
    assert (await _upload_url(rid2, h2)).status_code == 409


async def test_other_user_gets_404_on_foreign_request(storage: MemoryStorage) -> None:
    rid, _, h = await _setup()
    _, _, other = await _setup()
    assert (await _upload_url(rid, other)).status_code == 404
    eid = (await _upload_url(rid, h)).json()["evidence_id"]
    assert (await _complete(rid, eid, other)).status_code == 404


async def test_complete_valid_jpeg_strips_exif_and_hashes(storage: MemoryStorage) -> None:
    rid, uid, h = await _setup()
    raw = jpeg_with_exif()
    assert b"SecretPhoneMaker" in raw
    eid, r = await _put_and_complete(storage, rid, h, raw)
    assert r.status_code == 200
    body = r.json()
    assert body["review_status"] == "pending" and body["content_hash"].startswith("sha256:")

    async with user_session(uid) as s:
        ev = await s.get(SourceEvidence, uuid.UUID(eid))
        assert ev is not None and ev.upload_status == UploadStatus.validated
        stored = storage.objects[ev.file_storage_key]
        assert ev.file_storage_key.endswith("/clean")
    import hashlib

    assert body["content_hash"] == "sha256:" + hashlib.sha256(stored).hexdigest()
    assert b"SecretPhoneMaker" not in stored
    assert not Image.open(io.BytesIO(stored)).getexif()
    assert not any(k.endswith("/raw") for k in storage.objects)  # brut supprimé
    assert ("evidence_received", NotificationChannel.in_app) in await _events(rid, uid)

    again = await _complete(rid, eid, h)  # rejeu idempotent
    assert again.status_code == 200 and again.json() == body


async def test_complete_before_upload_is_409(storage: MemoryStorage) -> None:
    rid, _, h = await _setup()
    eid = (await _upload_url(rid, h)).json()["evidence_id"]
    assert (await _complete(rid, eid, h)).status_code == 409


@pytest.mark.parametrize(
    ("data", "mime", "code"),
    [
        (b"MZ\x90\x00" + b"\x00" * 200, "image/jpeg", "mime_mismatch"),  # exécutable déguisé
        (png_bytes(), "image/jpeg", "mime_mismatch"),  # type déclaré ≠ type réel
        (b"\xff\xd8\xff\xe0 not really a jpeg", "image/jpeg", "image_corrupt"),
        (b"%PDF-1.4\n/OpenAction << /S /JavaScript >>", "application/pdf", "pdf_active_content"),
    ],
)
async def test_complete_rejects_invalid_files(
    storage: MemoryStorage, data: bytes, mime: str, code: str
) -> None:
    rid, uid, h = await _setup()
    eid, r = await _put_and_complete(storage, rid, h, data, mime)
    assert r.status_code == 422 and r.json()["detail"]["code"] == code
    assert storage.objects == {}  # fichier rejeté supprimé
    async with user_session(uid) as s:
        ev = await s.get(SourceEvidence, uuid.UUID(eid))
        assert ev is not None
        assert ev.upload_status == UploadStatus.rejected and ev.upload_error == code
        assert ev.review_status is None  # jamais visible par l'agent
    events = await _events(rid, uid)
    assert {
        ("evidence_upload_failed", NotificationChannel.email),
        ("evidence_upload_failed", NotificationChannel.sms),
    } <= events
    assert (await _complete(rid, eid, h)).status_code == 409


async def test_each_failed_upload_notifies(storage: MemoryStorage) -> None:
    rid, uid, h = await _setup()
    for _ in range(2):
        await _put_and_complete(storage, rid, h, b"garbage")
    async with user_session(uid) as s:
        rows = (
            await s.scalars(
                select(NotificationEvent).where(
                    NotificationEvent.event_type == "evidence_upload_failed",
                    NotificationEvent.document_request_id == rid,
                    NotificationEvent.channel == NotificationChannel.sms,
                )
            )
        ).all()
    assert len(rows) == 2 and all(r.send_status.value == "pending" for r in rows)


async def test_clean_pdf_accepted(storage: MemoryStorage) -> None:
    rid, _, h = await _setup()
    _, r = await _put_and_complete(
        storage, rid, h, b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF", "application/pdf"
    )
    assert r.status_code == 200


async def test_malware_is_rejected(storage: MemoryStorage) -> None:
    app.dependency_overrides[get_scanner] = lambda: StubScanner(clean=False)
    rid, _, h = await _setup()
    _, r = await _put_and_complete(storage, rid, h, jpeg_with_exif())
    assert r.status_code == 422 and r.json()["detail"]["code"] == "malware_detected"
    assert storage.objects == {}


async def test_scanner_down_is_retryable_not_rejected(storage: MemoryStorage) -> None:
    app.dependency_overrides[get_scanner] = lambda: StubScanner(down=True)
    rid, uid, h = await _setup()
    eid, r = await _put_and_complete(storage, rid, h, jpeg_with_exif())
    assert r.status_code == 503
    async with user_session(uid) as s:
        ev = await s.get(SourceEvidence, uuid.UUID(eid))
        assert ev is not None and ev.upload_status == UploadStatus.awaiting_upload
    app.dependency_overrides[get_scanner] = lambda: StubScanner()
    assert (await _complete(rid, eid, h)).status_code == 200


async def test_oversized_object_rejected_without_reading(storage: MemoryStorage) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(evidence_max_bytes=500)
    rid, _, h = await _setup()
    eid = (await _upload_url(rid, h, size=400)).json()["evidence_id"]
    storage.objects[storage.presigned[-1][0]] = b"\xff\xd8\xff" + b"0" * 1000  # client a triché

    async def boom(_: str) -> bytes:
        raise AssertionError("ne doit pas lire un objet trop gros")

    storage.read = boom  # type: ignore[method-assign]
    r = await _complete(rid, eid, h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "file_too_large"


async def test_pixel_bomb_rejected(storage: MemoryStorage) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(evidence_max_pixels=1000)
    rid, _, h = await _setup()
    _, r = await _put_and_complete(storage, rid, h, jpeg_with_exif((200, 200)))
    assert r.status_code == 422 and r.json()["detail"]["code"] in {
        "image_too_large",
        "image_corrupt",
    }
