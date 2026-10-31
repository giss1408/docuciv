import hashlib

from app.core.config import settings


def hash_for_logs(value: str) -> str:
    """One-way, keyed digest for correlating log lines without exposing PII
    in clear text (docs/security.md §7). Never use this for anything
    security-sensitive (auth, signatures) — logging/correlation only.
    """
    digest = hashlib.sha256(f"{settings.secret_key}:{value}".encode()).hexdigest()
    return digest[:16]
