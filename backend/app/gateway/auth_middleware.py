"""Global authentication middleware — fail-closed safety net.

Rejects unauthenticated requests to non-public paths with 401. When a
request passes the cookie check, resolves the JWT payload to a real
``User`` object and stamps it into both ``request.state.user`` and the
``deerflow.runtime.user_context`` contextvar so that repository-layer
owner filtering works automatically via the sentinel pattern.

Fine-grained permission checks remain in authz.py decorators.
"""

from collections.abc import Callable
from time import monotonic
from uuid import uuid4

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.gateway.auth.errors import AuthErrorCode, AuthErrorResponse
from app.gateway.authz import _ALL_PERMISSIONS, AuthContext
from app.gateway.internal_auth import (
    INTERNAL_AUTH_HEADER_NAME,
    LEGACY_INTERNAL_AUTH_HEADER_NAME,
    get_internal_user,
    is_valid_internal_auth_token,
)
from deerflow.runtime.tenant_logging import append_tenant_audit_event
from deerflow.runtime.user_context import reset_current_user, set_current_user

# Paths that never require authentication.
_PUBLIC_PATH_PREFIXES: tuple[str, ...] = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)

# Exact auth paths that are public (login/register/status check).
# /api/v1/auth/me, /api/v1/auth/change-password etc. are NOT public.
_PUBLIC_EXACT_PATHS: frozenset[str] = frozenset(
    {
        "/api/v1/auth/login/local",
        "/api/v1/auth/register",
        "/api/v1/auth/logout",
        "/api/v1/auth/setup-status",
        "/api/v1/auth/initialize",
    }
)


def _is_public(path: str) -> bool:
    stripped = path.rstrip("/")
    if stripped in _PUBLIC_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in _PUBLIC_PATH_PREFIXES)


class AuthMiddleware(BaseHTTPMiddleware):
    """Strict auth gate: reject requests without a valid session.

    Two-stage check for non-public paths:

    1. Cookie presence — return 401 NOT_AUTHENTICATED if missing
    2. JWT validation via ``get_optional_user_from_request`` — return 401
       TOKEN_INVALID if the token is absent, malformed, expired, or the
       signed user does not exist / is stale

    On success, stamps ``request.state.user`` and the
    ``deerflow.runtime.user_context`` contextvar so that repository-layer
    owner filters work downstream without every route needing a
    ``@require_auth`` decorator. Routes that need per-resource
    authorization (e.g. "user A cannot read user B's thread by guessing
    the URL") should additionally use ``@require_permission(...,
    owner_check=True)`` for explicit enforcement — but authentication
    itself is fully handled here.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if _is_public(request.url.path):
            return await call_next(request)

        internal_user = None
        internal_token = request.headers.get(INTERNAL_AUTH_HEADER_NAME) or request.headers.get(LEGACY_INTERNAL_AUTH_HEADER_NAME)
        if is_valid_internal_auth_token(internal_token):
            internal_user = get_internal_user()

        # Non-public path: require session cookie
        if internal_user is None and not request.cookies.get("access_token"):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": AuthErrorResponse(
                        code=AuthErrorCode.NOT_AUTHENTICATED,
                        message="Authentication required",
                    ).model_dump()
                },
            )

        # Strict JWT validation: reject junk/expired tokens with 401
        # right here instead of silently passing through. This closes
        # the "junk cookie bypass" gap (AUTH_TEST_PLAN test 7.5.8):
        # without this, non-isolation routes like /api/models would
        # accept any cookie-shaped string as authentication.
        #
        # We call the *strict* resolver so that fine-grained error
        # codes (token_expired, token_invalid, user_not_found, …)
        # propagate from AuthErrorCode, not get flattened into one
        # generic code. BaseHTTPMiddleware doesn't let HTTPException
        # bubble up, so we catch and render it as JSONResponse here.
        from app.gateway.deps import get_current_user_from_request

        if internal_user is not None:
            user = internal_user
        else:
            try:
                user = await get_current_user_from_request(request)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        # Stamp both request.state.user (for the contextvar pattern)
        # and request.state.auth (so @require_permission's "auth is
        # None" branch short-circuits instead of running the entire
        # JWT-decode + DB-lookup pipeline a second time per request).
        request.state.user = user
        request.state.auth = AuthContext(user=user, permissions=_ALL_PERMISSIONS)
        request_id = str(uuid4())
        request.state.request_id = request_id
        started_at = monotonic()
        token = set_current_user(user)
        try:
            try:
                response = await call_next(request)
            except Exception:
                self._write_audit_event(
                    user_id=user.id,
                    request=request,
                    request_id=request_id,
                    status_code=500,
                    started_at=started_at,
                )
                raise
            response.headers["X-Request-ID"] = request_id
            self._write_audit_event(
                user_id=user.id,
                request=request,
                request_id=request_id,
                status_code=response.status_code,
                started_at=started_at,
            )
            return response
        finally:
            reset_current_user(token)

    @staticmethod
    def _write_audit_event(
        *,
        user_id: str,
        request: Request,
        request_id: str,
        status_code: int,
        started_at: float,
    ) -> None:
        """Best-effort audit logging that never breaks a completed request."""
        try:
            append_tenant_audit_event(
                user_id=user_id,
                action="http_request",
                details={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round((monotonic() - started_at) * 1000, 3),
                },
            )
        except Exception:
            # Audit storage failure must not alter the HTTP result. Infrastructure
            # monitoring should alert on an unwritable runtime volume.
            return
