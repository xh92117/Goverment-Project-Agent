# Docker Auth Validation Notes

Local auth is optional in Agent Base. This note records the Docker-specific
checks to run only when a downstream project enables local auth with
`GATEWAY_ENABLE_LOCAL_AUTH=true`.

## Scope

These checks cover container packaging behavior that ordinary backend tests do
not prove:

| Area | What to verify |
| --- | --- |
| Runtime volume | `AGENT_BASE_HOME` is mounted and persists runtime data across container restarts. |
| Session secret | `AUTH_JWT_SECRET` is stable across `docker compose down && docker compose up`. |
| Worker model | Rate-limit state is understood for the configured worker count. |
| Channel dispatch | Retained channels attach internal Gateway auth headers when calling Gateway-compatible APIs. |
| Reset credentials | `reset_admin` writes credentials under `AGENT_BASE_HOME` without logging plaintext passwords. |
| Deploy topology | `scripts/deploy.sh` starts Gateway, frontend, and nginx with the embedded runtime topology. |

## Pre-Flight

```bash
docker --version
docker compose version

echo "GATEWAY_ENABLE_LOCAL_AUTH=true" >> .env
echo "AUTH_JWT_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" >> .env
echo "AGENT_BASE_HOME=$HOME/agent-base-data" >> .env
```

## Suggested Checks

1. Start the Docker topology with the same command used for deployment.
2. Create or reset an admin account with `python -m app.gateway.auth.reset_admin`.
3. Restart the containers and confirm the account/session behavior matches the
   configured local-auth expectations.
4. Confirm credential files are written under `AGENT_BASE_HOME` with restrictive
   permissions and that container logs do not include plaintext passwords.
5. For retained IM channels, inspect logs or integration tests to confirm
   internal Gateway auth headers are attached by channel workers.

## Default Base

When `GATEWAY_ENABLE_LOCAL_AUTH` is false, these checks are not required for the
default Agent Base runtime because the local auth router, middleware, admin
bootstrap, and users table are not mounted.
