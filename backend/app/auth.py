import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings


@dataclass(frozen=True)
class Principal:
    """Citoyen/entreprise authentifié. L'identité vient toujours du jeton, jamais du corps."""

    user_id: uuid.UUID


async def get_principal(
    settings: Annotated[Settings, Depends(get_settings)],
    x_dev_user_id: Annotated[str | None, Header()] = None,
) -> Principal:
    # OIDC (docs/architecture.md §1) n'est pas encore implémenté. Fail closed: hors dev, aucune
    # requête n'est authentifiée; l'en-tête de dev n'est honoré qu'en environnement dev.
    if settings.environment != "dev" or x_dev_user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication_required")
    try:
        return Principal(user_id=uuid.UUID(x_dev_user_id))
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication_required") from None
