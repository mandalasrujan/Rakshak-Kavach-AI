import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import Settings
from app.core.errors import NotAuthenticatedError
from app.core.security import PATIENT_AUDIENCE, TOKEN_ISSUER, PasswordService, TokenService
from tests.conftest import TEST_JWT_SECRET

SETTINGS = Settings(  # type: ignore[call-arg]
    _env_file=None,
    database_url="postgresql+asyncpg://u:p@localhost/db",
    redis_url="redis://localhost:6379/0",
    jwt_secret_key=TEST_JWT_SECRET,
)


@pytest.fixture(scope="module")
def passwords() -> PasswordService:
    return PasswordService()


def test_password_hash_is_argon2id_and_verifies(passwords: PasswordService) -> None:
    hashed = passwords.hash("a-very-long-password")
    assert hashed.startswith("$argon2id$")
    assert "a-very-long-password" not in hashed
    assert passwords.verify(hashed, "a-very-long-password")
    assert not passwords.verify(hashed, "wrong-password-value")
    assert not passwords.verify("not-a-hash", "anything")


def _claims(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": str(uuid.uuid4()),
        "jti": uuid.uuid4().hex,
        "iss": TOKEN_ISSUER,
        "aud": PATIENT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    claims.update(overrides)
    return claims


def test_token_round_trip() -> None:
    tokens = TokenService(SETTINGS)
    patient_id = uuid.uuid4()
    issued = tokens.create_access_token(patient_id)
    claims = tokens.decode(issued.token)
    assert claims.patient_id == patient_id
    assert claims.jti == issued.jti
    assert claims.expires_at > datetime.now(UTC)


@pytest.mark.parametrize(
    ("overrides", "key"),
    [
        ({"exp": int((datetime.now(UTC) - timedelta(seconds=1)).timestamp())}, TEST_JWT_SECRET),
        ({"aud": "rakshak-kavach:doctor"}, TEST_JWT_SECRET),
        ({"iss": "someone-else"}, TEST_JWT_SECRET),
        ({"sub": "not-a-uuid"}, TEST_JWT_SECRET),
        ({}, "a-different-secret-that-is-also-long-enough-123"),
    ],
    ids=["expired", "wrong-audience", "wrong-issuer", "bad-subject", "wrong-key"],
)
def test_invalid_tokens_rejected(overrides: dict[str, object], key: str) -> None:
    token = jwt.encode(_claims(**overrides), key, algorithm="HS256")
    with pytest.raises(NotAuthenticatedError):
        TokenService(SETTINGS).decode(token)


@pytest.mark.parametrize("missing", ["jti", "exp", "sub", "aud", "iss", "iat"])
def test_tokens_missing_required_claims_rejected(missing: str) -> None:
    claims = _claims()
    claims.pop(missing)
    token = jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS256")
    with pytest.raises(NotAuthenticatedError):
        TokenService(SETTINGS).decode(token)


def _b64(data: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def test_alg_none_and_tampered_tokens_rejected() -> None:
    tokens = TokenService(SETTINGS)
    unsigned = f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(_claims())}."
    with pytest.raises(NotAuthenticatedError):
        tokens.decode(unsigned)

    header, _payload, signature = tokens.create_access_token(uuid.uuid4()).token.split(".")
    forged = f"{header}.{_b64(_claims())}.{signature}"
    with pytest.raises(NotAuthenticatedError):
        tokens.decode(forged)
