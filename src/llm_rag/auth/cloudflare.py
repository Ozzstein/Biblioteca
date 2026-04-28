from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import Header, HTTPException

from llm_rag.config import Settings, get_settings

_JWKS_CACHE_TTL_SECONDS = 3600


@dataclass(frozen=True)
class CloudflarePrincipal:
    """Authenticated Cloudflare Access principal."""

    name: str
    claims: dict[str, Any]


@dataclass
class _JwksCache:
    team_domain: str
    jwks: dict[str, Any]
    fetched_at: float


_jwks_cache: _JwksCache | None = None


def clear_jwks_cache() -> None:
    """Clear the JWKS cache. Intended for tests."""
    global _jwks_cache
    _jwks_cache = None


async def _fetch_jwks(team_domain: str) -> dict[str, Any]:
    url = f"https://{team_domain}/cdn-cgi/access/certs"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        data: Any = response.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=401, detail="Invalid Cloudflare JWKS")
    return data


async def _get_jwks(settings: Settings) -> dict[str, Any]:
    global _jwks_cache

    now = time.time()
    if (
        _jwks_cache is not None
        and _jwks_cache.team_domain == settings.cf_access_team_domain
        and now - _jwks_cache.fetched_at < _JWKS_CACHE_TTL_SECONDS
    ):
        return _jwks_cache.jwks

    try:
        jwks = await _fetch_jwks(settings.cf_access_team_domain)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 -- auth failures should not leak transport detail
        raise HTTPException(status_code=401, detail="Unable to verify Cloudflare JWT") from exc

    _jwks_cache = _JwksCache(
        team_domain=settings.cf_access_team_domain,
        jwks=jwks,
        fetched_at=now,
    )
    return jwks


def _select_jwk(jwks: dict[str, Any], token: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Malformed Cloudflare JWT") from exc

    keys = jwks.get("keys")
    if not isinstance(keys, list) or not keys:
        raise HTTPException(status_code=401, detail="Invalid Cloudflare JWKS")

    kid = header.get("kid")
    if kid is not None:
        for key in keys:
            if isinstance(key, dict) and key.get("kid") == kid:
                return key
        raise HTTPException(status_code=401, detail="Cloudflare JWT key not found")

    if len(keys) == 1 and isinstance(keys[0], dict):
        return keys[0]
    raise HTTPException(status_code=401, detail="Cloudflare JWT missing key id")


async def require_cloudflare_access(
    cf_access_jwt_assertion: str | None = Header(default=None, alias="Cf-Access-Jwt-Assertion"),
    cf_access_authenticated_user_email: str | None = Header(
        default=None,
        alias="Cf-Access-Authenticated-User-Email",
    ),
    cf_access_service_token_name: str | None = Header(
        default=None,
        alias="Cf-Access-Service-Token-Name",
    ),
) -> CloudflarePrincipal:
    """Validate Cloudflare Access JWT headers and return the caller principal."""
    settings = get_settings()
    if not settings.cf_access_team_domain or not settings.cf_access_aud_tag:
        raise HTTPException(status_code=503, detail="Cloudflare Access is not configured")

    if not cf_access_jwt_assertion:
        raise HTTPException(status_code=401, detail="Missing Cloudflare Access JWT")

    jwks = await _get_jwks(settings)
    jwk = _select_jwk(jwks, cf_access_jwt_assertion)

    try:
        signing_key = jwt.PyJWK.from_dict(jwk).key
        claims_raw: Any = jwt.decode(
            cf_access_jwt_assertion,
            signing_key,
            algorithms=["RS256", "ES256"],
            audience=settings.cf_access_aud_tag,
            options={"require": ["exp", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Expired Cloudflare JWT") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid Cloudflare JWT") from exc

    if not isinstance(claims_raw, dict):
        raise HTTPException(status_code=401, detail="Invalid Cloudflare JWT claims")

    principal = cf_access_authenticated_user_email or cf_access_service_token_name
    if not principal:
        principal = str(claims_raw.get("email") or claims_raw.get("sub") or "")
    if not principal:
        raise HTTPException(status_code=401, detail="Missing Cloudflare principal")

    return CloudflarePrincipal(name=principal, claims=claims_raw)
