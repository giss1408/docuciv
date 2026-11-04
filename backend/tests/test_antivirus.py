import asyncio
import struct

import pytest

from app.services.antivirus import ClamAVScanner, ScanUnavailableError


async def _fake_clamd(reply: bytes):  # type: ignore[no-untyped-def]
    received = bytearray()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        assert await reader.readexactly(10) == b"zINSTREAM\0"
        while True:
            (n,) = struct.unpack(">I", await reader.readexactly(4))
            if n == 0:
                break
            received.extend(await reader.readexactly(n))
        writer.write(reply)
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1], received


@pytest.mark.parametrize(
    ("reply", "clean"), [(b"stream: OK\0", True), (b"stream: Eicar-Test FOUND\0", False)]
)
async def test_instream_protocol(reply: bytes, clean: bool) -> None:
    server, port, received = await _fake_clamd(reply)
    async with server:
        data = b"x" * 150_000  # plusieurs chunks
        assert await ClamAVScanner("127.0.0.1", port).is_clean(data) is clean
    assert bytes(received) == data


async def test_error_reply_and_unreachable_are_unavailable() -> None:
    server, port, _ = await _fake_clamd(b"INSTREAM size limit exceeded. ERROR\0")
    async with server:
        with pytest.raises(ScanUnavailableError):
            await ClamAVScanner("127.0.0.1", port).is_clean(b"x")
    with pytest.raises(ScanUnavailableError):
        await ClamAVScanner("127.0.0.1", 1).is_clean(b"x")  # port fermé
