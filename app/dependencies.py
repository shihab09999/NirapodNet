from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from .auth import get_current_user
from .models import User


USER_ROLE = "user"
RESCUE_ROLE = "rescue"
# The roadmap names this tier "Responder"; "rescue" is the original
# name for the same tier. Both are accepted everywhere "rescue" is,
# so existing accounts keep working.
RESPONDER_ROLE = "responder"
OPERATOR_ROLE = "operator"
ADMIN_ROLE = "admin"

ALL_ROLES = (
    USER_ROLE,
    RESCUE_ROLE,
    RESPONDER_ROLE,
    OPERATOR_ROLE,
    ADMIN_ROLE,
)

# NOTE: the old RESPONDER_TIER tuple was dead code (no caller used
# it) and is removed. Routes spell out their allowed roles in
# require_role(...) instead of hiding them behind a tier constant.


def require_role(*allowed_roles: str) -> Callable:
    """
    Return a FastAPI dependency that allows only users
    whose role is included in allowed_roles.
    """

    def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return current_user

    return role_checker