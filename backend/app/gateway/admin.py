"""Shared administrator authorization helpers for server-wide resources."""

from fastapi import HTTPException, Request, status

from app.gateway.config import get_gateway_config


async def require_admin_user(request: Request, *, resource: str) -> None:
    """Allow server-wide mutations only to admins in authenticated mode."""
    user = getattr(request.state, "user", None)
    if user is not None:
        if getattr(user, "system_role", None) != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Admin privileges required to manage {resource}.",
            )
        return

    if not get_gateway_config().enable_local_auth:
        return

    from app.gateway.deps import get_current_user_from_request

    user = await get_current_user_from_request(request)
    if getattr(user, "system_role", None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Admin privileges required to manage {resource}.",
        )
