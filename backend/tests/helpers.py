"""Doubles de test partagés (stockage mémoire, scanner, images)."""

import io

from PIL import Image

from app.models import ReferenceCheckResult
from app.services.antivirus import ScanUnavailableError
from app.services.storage import PresignedUpload


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.presigned: list[tuple[str, str, int]] = []

    async def presign_upload(
        self, key: str, content_type: str, max_bytes: int, ttl_seconds: int
    ) -> PresignedUpload:
        self.presigned.append((key, content_type, max_bytes))
        return PresignedUpload(url="https://s3.test/bucket", fields={"key": key})

    async def presign_download(self, key: str, ttl_seconds: int) -> str:
        return f"https://s3.test/{key}?ttl={ttl_seconds}"

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


class Found:
    async def check(self, *_: object) -> ReferenceCheckResult:
        return ReferenceCheckResult.found


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
