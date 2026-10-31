from dataclasses import dataclass
from functools import lru_cache
import hmac

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .settings import get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Identity:
    tenant_id: str
    user_id: str


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, timeout=4)


def current_identity(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Identity:
    settings = get_settings()
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer authentication required", headers={"WWW-Authenticate": "Bearer"})

    token = credentials.credentials
    if settings.app_env == "development":
        if not settings.dev_auth_token or not hmac.compare_digest(token, settings.dev_auth_token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid development token", headers={"WWW-Authenticate": "Bearer"})
        return Identity(tenant_id=settings.dev_tenant_id, user_id=settings.dev_user_id)

    if not all((settings.oidc_issuer, settings.oidc_audience, settings.oidc_jwks_url)):
        raise HTTPException(status_code=503, detail="OIDC authentication is not configured")

    try:
        signing_key = _jwks_client(settings.oidc_jwks_url).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except (jwt.PyJWTError, jwt.PyJWKClientError, jwt.PyJWKClientConnectionError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"}) from exc

    tenant_id = claims.get(settings.oidc_tenant_claim)
    subject = claims.get("sub")
    if not isinstance(tenant_id, str) or not tenant_id.strip() or not isinstance(subject, str) or not subject.strip():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token is missing tenant or subject claims")
    return Identity(tenant_id=tenant_id, user_id=subject)
