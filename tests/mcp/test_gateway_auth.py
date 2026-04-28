from __future__ import annotations

import json
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from llm_rag.auth.cloudflare import clear_jwks_cache
from llm_rag.config import get_settings
from llm_rag.mcp.gateway import create_app
from tests.mcp.gateway_helpers import FakePool


@pytest.fixture()
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def cloudflare_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "team.cloudflareaccess.com")
    monkeypatch.setenv("CF_ACCESS_AUD_TAG", "expected-aud")
    get_settings.cache_clear()
    clear_jwks_cache()
    yield
    get_settings.cache_clear()
    clear_jwks_cache()


def _jwk_for_key(key: rsa.RSAPrivateKey) -> dict[str, Any]:
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk["kid"] = "test-key"
    jwk["alg"] = "RS256"
    return jwk


def _token(key: rsa.RSAPrivateKey, *, aud: str = "expected-aud", exp_delta: int = 3600) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": "user-1", "aud": aud, "exp": now + exp_delta},
        key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )


def _mock_jwks(
    monkeypatch: pytest.MonkeyPatch,
    key: rsa.RSAPrivateKey,
) -> None:
    async def fake_fetch(_team_domain: str) -> dict[str, Any]:
        return {"keys": [_jwk_for_key(key)]}

    monkeypatch.setattr("llm_rag.auth.cloudflare._fetch_jwks", fake_fetch)


def _client() -> TestClient:
    app = create_app(pool_factory=FakePool)
    return TestClient(app)


def test_valid_cloudflare_jwt_allows_request(
    monkeypatch: pytest.MonkeyPatch,
    rsa_key: rsa.RSAPrivateKey,
) -> None:
    _mock_jwks(monkeypatch, rsa_key)

    with _client() as client:
        response = client.get(
            "/mcp/health",
            headers={
                "Cf-Access-Jwt-Assertion": _token(rsa_key),
                "Cf-Access-Authenticated-User-Email": "user@example.com",
            },
        )

    assert response.status_code == 200


def test_missing_header_returns_401(
    monkeypatch: pytest.MonkeyPatch,
    rsa_key: rsa.RSAPrivateKey,
) -> None:
    _mock_jwks(monkeypatch, rsa_key)

    with _client() as client:
        response = client.get("/mcp/health")

    assert response.status_code == 401


def test_wrong_audience_returns_401(
    monkeypatch: pytest.MonkeyPatch,
    rsa_key: rsa.RSAPrivateKey,
) -> None:
    _mock_jwks(monkeypatch, rsa_key)

    with _client() as client:
        response = client.get(
            "/mcp/health",
            headers={
                "Cf-Access-Jwt-Assertion": _token(rsa_key, aud="other-aud"),
                "Cf-Access-Authenticated-User-Email": "user@example.com",
            },
        )

    assert response.status_code == 401


def test_expired_jwt_returns_401(
    monkeypatch: pytest.MonkeyPatch,
    rsa_key: rsa.RSAPrivateKey,
) -> None:
    _mock_jwks(monkeypatch, rsa_key)

    with _client() as client:
        response = client.get(
            "/mcp/health",
            headers={
                "Cf-Access-Jwt-Assertion": _token(rsa_key, exp_delta=-10),
                "Cf-Access-Authenticated-User-Email": "user@example.com",
            },
        )

    assert response.status_code == 401


def test_malformed_jwt_returns_401(
    monkeypatch: pytest.MonkeyPatch,
    rsa_key: rsa.RSAPrivateKey,
) -> None:
    _mock_jwks(monkeypatch, rsa_key)

    with _client() as client:
        response = client.get(
            "/mcp/health",
            headers={
                "Cf-Access-Jwt-Assertion": "not-a-jwt",
                "Cf-Access-Authenticated-User-Email": "user@example.com",
            },
        )

    assert response.status_code == 401
