"""Stockage objet S3-compatible. Les binaires ne transitent jamais par l'API en entrée:
le client envoie directement vers S3 via un POST pré-signé (docs/security.md §2bis)."""

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import boto3  # type: ignore[import-untyped]
from botocore.client import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from app.config import get_settings


@dataclass(frozen=True)
class PresignedUpload:
    url: str
    fields: dict[str, str]


class ObjectStorage(Protocol):
    async def presign_upload(
        self, key: str, content_type: str, max_bytes: int, ttl_seconds: int
    ) -> PresignedUpload: ...

    async def presign_download(self, key: str, ttl_seconds: int) -> str: ...

    async def size(self, key: str) -> int | None: ...

    async def read(self, key: str) -> bytes: ...

    async def write(self, key: str, data: bytes, content_type: str) -> None: ...

    async def delete(self, key: str) -> None: ...


class S3Storage:
    def __init__(self) -> None:
        s = get_settings()
        self._bucket = s.s3_bucket
        self._kms = s.s3_kms_key_id
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url,
            region_name=s.s3_region,
            aws_access_key_id=s.s3_access_key_id,
            aws_secret_access_key=s.s3_secret_access_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def _sse_put_args(self) -> dict[str, str]:
        if not self._kms:
            return {}
        return {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self._kms}

    def _sse_post_fields(self) -> dict[str, str]:
        if not self._kms:
            return {}
        return {
            "x-amz-server-side-encryption": "aws:kms",
            "x-amz-server-side-encryption-aws-kms-key-id": self._kms,
        }

    async def presign_upload(
        self, key: str, content_type: str, max_bytes: int, ttl_seconds: int
    ) -> PresignedUpload:
        # POST pré-signé (et non PUT): S3 applique content-length-range et le Content-Type exact.
        fields = {"Content-Type": content_type, **self._sse_post_fields()}
        conditions: list[Any] = [{k: v} for k, v in fields.items()]
        conditions.append(["content-length-range", 1, max_bytes])
        post = await asyncio.to_thread(
            self._client.generate_presigned_post,
            self._bucket,
            key,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=ttl_seconds,
        )
        return PresignedUpload(url=post["url"], fields=post["fields"])

    async def presign_download(self, key: str, ttl_seconds: int) -> str:
        url = await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )
        return str(url)

    async def size(self, key: str) -> int | None:
        try:
            head = await asyncio.to_thread(self._client.head_object, Bucket=self._bucket, Key=key)
        except ClientError as e:
            if e.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return int(head["ContentLength"])

    async def read(self, key: str) -> bytes:
        obj = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket, Key=key)
        return bytes(await asyncio.to_thread(obj["Body"].read))

    async def write(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            **self._sse_put_args(),
        )

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)


@lru_cache
def _s3() -> S3Storage:
    return S3Storage()


def get_storage() -> ObjectStorage:
    return _s3()
