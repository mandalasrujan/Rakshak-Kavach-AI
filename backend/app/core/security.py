"""Password hashing (argon2id) and access tokens (HS256 JWT)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings
from app.core.errors import NotAuthenticatedError

TOKEN_ISSUER = "rakshak-kavach-api"  # noqa: S105 (issuer name, not a secret)
PATIENT_AUDIENCE = "rakshak-kavach:patient"
_REQUIRED_CLAIMS = ["sub", "jti", "iss", "aud", "iat", "exp"]


class PasswordService:
    """argon2id hashing. All methods are CPU-bound; call them via a worker thread."""

    def __init__(self) -> None:
        self._hasher = PasswordHasher()
        # Verified against when an email is unknown so response time does not reveal accounts.
        self._dummy_hash = self._hasher.hash(uuid.uuid4().hex)

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def verify_dummy(self, password: str) -> None:
        self.verify(self._dummy_hash, password)

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)


@dataclass(frozen=True)
class AccessToken:
    token: str
    jti: str
    expires_at: datetime


@dataclass(frozen=True)
class TokenClaims:
    patient_id: uuid.UUID
    jti: str
    expires_at: datetime


class TokenService:
    def __init__(self, settings: Settings) -> None:
        self._key = settings.jwt_secret_key.get_secret_value()
        self._algorithm = settings.jwt_algorithm
        self._ttl = timedelta(seconds=settings.access_token_ttl_seconds)

    def create_access_token(self, patient_id: uuid.UUID) -> AccessToken:
        now = datetime.now(UTC)
        expires_at = now + self._ttl
        jti = uuid.uuid4().hex
        claims = {
            "sub": str(patient_id),
            "jti": jti,
            "iss": TOKEN_ISSUER,
            "aud": PATIENT_AUDIENCE,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(claims, self._key, algorithm=self._algorithm)
        return AccessToken(token=token, jti=jti, expires_at=expires_at)

    def decode(self, token: str) -> TokenClaims:
        """Validate signature, algorithm, issuer, audience and expiry. Any failure is a 401."""
        try:
            claims = jwt.decode(
                token,
                self._key,
                algorithms=[self._algorithm],
                audience=PATIENT_AUDIENCE,
                issuer=TOKEN_ISSUER,
                options={"require": _REQUIRED_CLAIMS},
            )
            return TokenClaims(
                patient_id=uuid.UUID(claims["sub"]),
                jti=str(claims["jti"]),
                expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC),
            )
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise NotAuthenticatedError() from exc
