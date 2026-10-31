"""The only legitimate path for cross-tenant reads: Owner access, always
justified and always logged to PlatformAuditLog before the query runs
(docs/security.md §6, docs/data-model.md §1, AGENTS.md règle 8).

Deliberately separate from app.db.session.get_scoped_db so an Owner token
can never silently reuse a tenant-scoped code path.
"""

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, Role, get_current_principal
from app.db.session import SessionLocal
from app.models.owner import PlatformAuditLog


def owner_db(action: str):
    """Returns a FastAPI dependency for an Owner-only session with no RLS
    tenant filter applied (the Owner DB role is expected to bypass the
    `admin_agents` policy etc. — see alembic/versions/0001). The endpoint
    itself supplies `action`; the caller (via the request body/query) must
    still supply a non-empty `justification`, logged before the query runs.
    """

    async def _dependency(
        justification: str,
        principal: Principal = Depends(get_current_principal),
    ) -> AsyncGenerator[AsyncSession, None]:
        if principal.role is not Role.owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Owner role required"
            )
        if not justification.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="justification is required for any Owner cross-tenant access",
            )

        async with SessionLocal() as session:
            session.add(
                PlatformAuditLog(
                    owner_user_id=principal.subject_id,
                    action=action,
                    justification=justification,
                )
            )
            await session.commit()
            yield session

    return _dependency
