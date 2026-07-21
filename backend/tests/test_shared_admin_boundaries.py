"""Authorization boundaries for server-wide mutable resources."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from app.gateway.routers import channels


class _UserMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request.state.user = type("User", (), {"id": "alice", "system_role": "user"})()
        return await call_next(request)


def test_non_admin_cannot_restart_shared_channel_service():
    app = FastAPI()
    app.add_middleware(_UserMiddleware)
    app.include_router(channels.router)

    with TestClient(app) as client:
        response = client.post("/api/channels/feishu/restart")

    assert response.status_code == 403
