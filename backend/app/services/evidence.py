"""Validation et assainissement d'une pièce justificative (docs/security.md §2bis).

Le type est déterminé par la signature binaire, jamais par l'extension ni par le Content-Type
déclaré par le client. Les images sont ré-encodées (orientation appliquée puis EXIF/métadonnées
supprimés)."""

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_MIME = ("image/jpeg", "image/png", "application/pdf")
_PDF_FORBIDDEN = (b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile", b"/OpenAction", b"/AA")


class EvidenceRejectedError(Exception):
    """`code` est stocké; `citizen_reason` alimente le message 3a (notifications.md §2)."""

    def __init__(self, code: str, citizen_reason: str) -> None:
        super().__init__(code)
        self.code, self.citizen_reason = code, citizen_reason


@dataclass(frozen=True)
class CleanEvidence:
    data: bytes
    mime_type: str
    sha256: str


def detect_mime(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def sanitize(data: bytes, declared_mime: str, max_pixels: int) -> CleanEvidence:
    actual = detect_mime(data)
    if actual is None or actual != declared_mime:
        raise EvidenceRejectedError("mime_mismatch", "format de fichier non supporté (jpg/png/pdf)")

    if actual == "application/pdf":
        if any(token in data for token in _PDF_FORBIDDEN):
            raise EvidenceRejectedError("pdf_active_content", "PDF contenant du contenu actif")
        return CleanEvidence(data, actual, hashlib.sha256(data).hexdigest())

    Image.MAX_IMAGE_PIXELS = max_pixels  # au-delà de 2x: DecompressionBombError
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.width * img.height > max_pixels:
                raise EvidenceRejectedError("image_too_large", "image trop grande")
            img.load()
            oriented = ImageOps.exif_transpose(img) or img
            out = io.BytesIO()
            if actual == "image/jpeg":
                oriented.convert("RGB").save(out, "JPEG", quality=92)  # sans exif=
            else:
                oriented.save(out, "PNG")  # sans pnginfo: pas de chunks texte/eXIf
    except EvidenceRejectedError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise EvidenceRejectedError("image_corrupt", "image illisible ou corrompue") from None
    clean = out.getvalue()
    return CleanEvidence(clean, actual, hashlib.sha256(clean).hexdigest())
