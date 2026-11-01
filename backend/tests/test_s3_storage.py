"""Smoke test de l'adaptateur S3 contre un vrai MinIO (DOCUCIV_TEST_S3=1)."""

import os
import uuid

import httpx
import pytest

from app.config import get_settings
from app.services.storage import S3Storage

pytestmark = pytest.mark.skipif(
    os.environ.get("DOCUCIV_TEST_S3") != "1", reason="DOCUCIV_TEST_S3=1 requis (MinIO)"
)


@pytest.fixture
def storage() -> S3Storage:
    s = S3Storage()
    try:
        s._client.create_bucket(Bucket=get_settings().s3_bucket)
    except s._client.exceptions.BucketAlreadyOwnedByYou:
        pass
    return s


async def test_presigned_post_enforces_size_and_type(storage: S3Storage) -> None:
    key = f"test/{uuid.uuid4()}/raw"
    post = await storage.presign_upload(key, "image/jpeg", max_bytes=100, ttl_seconds=60)
    async with httpx.AsyncClient() as c:
        ok = await c.post(
            post.url, data=post.fields, files={"file": ("f", b"x" * 50, "image/jpeg")}
        )
        assert ok.status_code == 204
        too_big = await c.post(
            post.url, data=post.fields, files={"file": ("f", b"x" * 500, "image/jpeg")}
        )
        assert too_big.status_code == 400  # content-length-range appliqué par S3
        wrong_type = await c.post(
            post.url,
            data={**post.fields, "Content-Type": "text/html"},
            files={"file": ("f", b"x", "text/html")},
        )
        assert wrong_type.status_code == 403
    assert await storage.size(key) == 50
    assert await storage.read(key) == b"x" * 50
    await storage.delete(key)
    assert await storage.size(key) is None


async def test_write_read_roundtrip(storage: S3Storage) -> None:
    key = f"test/{uuid.uuid4()}/clean"
    await storage.write(key, b"abc", "image/png")
    assert await storage.read(key) == b"abc"
    await storage.delete(key)
