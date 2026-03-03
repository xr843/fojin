from fastapi import Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.user import User


def require_role(*roles: str):
    """Dependency that checks if the current user has one of the required roles."""

    async def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要角色: {', '.join(roles)}",
            )
        return user

    return _guard
