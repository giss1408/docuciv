"""Scan antivirus (docs/security.md §2bis) via clamd, protocole INSTREAM."""

import asyncio
import struct
from typing import Protocol

from app.config import get_settings


class ScanUnavailableError(Exception):
    """Le scanner n'a pas répondu: l'upload n'est ni accepté ni rejeté définitivement."""


class Scanner(Protocol):
    async def is_clean(self, data: bytes) -> bool: ...


class DisabledScanner:
    """Dev uniquement (la config refuse `disabled` hors dev)."""

    async def is_clean(self, data: bytes) -> bool:
        return True


class ClamAVScanner:
    def __init__(self, host: str, port: int, timeout: float = 30) -> None:
        self._host, self._port, self._timeout = host, port, timeout

    async def is_clean(self, data: bytes) -> bool:
        try:
            return await asyncio.wait_for(self._scan(data), self._timeout)
        except (OSError, TimeoutError) as e:
            raise ScanUnavailableError from e

    async def _scan(self, data: bytes) -> bool:
        reader, writer = await asyncio.open_connection(self._host, self._port)
        try:
            writer.write(b"zINSTREAM\0")
            for i in range(0, len(data), 64 * 1024):
                chunk = data[i : i + 64 * 1024]
                writer.write(struct.pack(">I", len(chunk)) + chunk)
            writer.write(struct.pack(">I", 0))
            await writer.drain()
            reply = (await reader.read(1024)).rstrip(b"\0\n")
        finally:
            writer.close()
        if reply.endswith(b"OK"):
            return True
        if reply.endswith(b"FOUND"):
            return False
        raise ScanUnavailableError(reply.decode(errors="replace"))  # ex: "...ERROR"


def get_scanner() -> Scanner:
    s = get_settings()
    if s.antivirus == "clamav":
        return ClamAVScanner(s.clamd_host, s.clamd_port)
    return DisabledScanner()
