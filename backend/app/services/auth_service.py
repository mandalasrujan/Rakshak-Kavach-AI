"""Patient registration, login, logout and token-to-patient resolution.

Logs carry patient IDs and reason codes only; never emails, passwords or tokens.
"""

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    InvalidCredentialsError,
    NotAuthenticatedError,
    RateLimitedError,
    ServiceUnavailableError,
)
from app.core.security import AccessToken, PasswordService, TokenService
from app.models.patient import Patient
from app.repositories.patient_repository import PatientRepository
from app.services.rate_limiter import RateLimiter

log = structlog.get_logger(__name__)

_DENYLIST_PREFIX = "auth:denylist:"


def _email_key(email: str) -> str:
    # Hashed so raw emails never appear in Redis keys.
    return hashlib.sha256(email.encode()).hexdigest()


@dataclass(frozen=True)
class LoginResult:
    patient: Patient
    access_token: AccessToken


class AuthService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        redis: Redis,
        settings: Settings,
        passwords: PasswordService,
        tokens: TokenService,
    ) -> None:
        self._session = session
        self._repo = PatientRepository(session)
        self._redis = redis
        self._settings = settings
        self._passwords = passwords
        self._tokens = tokens
        self._limiter = RateLimiter(redis)

    async def _enforce_limit(self, key: str, *, limit: int, window_seconds: int) -> None:
        try:
            result = await self._limiter.hit(key, limit=limit, window_seconds=window_seconds)
        except RedisError as exc:
            log.error("auth.rate_limiter_unavailable", error_type=type(exc).__name__)
            raise ServiceUnavailableError() from exc  # fail closed
        if not result.allowed:
            log.warning("auth.rate_limited", limiter=key.split(":")[1])
            raise RateLimitedError(headers={"Retry-After": str(result.retry_after_seconds)})

    async def register(self, *, email: str, password: str, client_ip: str) -> Patient:
        s = self._settings
        await self._enforce_limit(
            f"rl:register:ip:{client_ip}",
            limit=s.register_max_attempts_per_ip,
            window_seconds=s.register_window_seconds,
        )
        if await self._repo.get_by_email(email) is not None:
            raise ConflictError("An account with this email already exists.")
        password_hash = await asyncio.to_thread(self._passwords.hash, password)
        try:
            patient = await self._repo.add(email=email, password_hash=password_hash)
            await self._session.commit()
        except IntegrityError as exc:  # concurrent registration with the same email
            await self._session.rollback()
            raise ConflictError("An account with this email already exists.") from exc
        log.info("auth.register.succeeded", patient_id=str(patient.id))
        return patient

    async def login(self, *, email: str, password: str, client_ip: str) -> LoginResult:
        s = self._settings
        email_limit_key = f"rl:login:email:{_email_key(email)}"
        await self._enforce_limit(
            f"rl:login:ip:{client_ip}",
            limit=s.login_max_attempts_per_ip,
            window_seconds=s.login_window_seconds,
        )
        await self._enforce_limit(
            email_limit_key,
            limit=s.login_max_attempts_per_email,
            window_seconds=s.login_window_seconds,
        )

        patient = await self._repo.get_by_email(email)
        if patient is None:
            await asyncio.to_thread(self._passwords.verify_dummy, password)
            log.info("auth.login.failed", reason="unknown_account")
            raise InvalidCredentialsError()
        if not await asyncio.to_thread(self._passwords.verify, patient.password_hash, password):
            log.info("auth.login.failed", reason="wrong_password", patient_id=str(patient.id))
            raise InvalidCredentialsError()

        if self._passwords.needs_rehash(patient.password_hash):
            new_hash = await asyncio.to_thread(self._passwords.hash, password)
            await self._repo.update_password_hash(patient, new_hash)
            await self._session.commit()

        try:
            await self._limiter.reset(email_limit_key)
        except RedisError:
            log.warning("auth.rate_limit_reset_failed")
        token = self._tokens.create_access_token(patient.id)
        log.info("auth.login.succeeded", patient_id=str(patient.id))
        return LoginResult(patient=patient, access_token=token)

    async def logout(self, token: str | None) -> None:
        """Revoke the token's jti until it would have expired. Idempotent."""
        if not token:
            return
        try:
            claims = self._tokens.decode(token)
        except NotAuthenticatedError:
            return
        remaining = int((claims.expires_at - datetime.now(UTC)).total_seconds())
        if remaining <= 0:
            return
        try:
            await self._redis.set(f"{_DENYLIST_PREFIX}{claims.jti}", "1", ex=remaining)
        except RedisError as exc:
            log.error("auth.logout_denylist_failed", error_type=type(exc).__name__)
            raise ServiceUnavailableError() from exc
        log.info("auth.logout.succeeded", patient_id=str(claims.patient_id))

    async def authenticate(self, token: str | None) -> Patient:
        """Resolve a cookie token to the patient. Fails closed on any doubt."""
        if not token:
            raise NotAuthenticatedError()
        claims = self._tokens.decode(token)
        try:
            revoked = await self._redis.exists(f"{_DENYLIST_PREFIX}{claims.jti}")
        except RedisError as exc:
            log.error("auth.denylist_unavailable", error_type=type(exc).__name__)
            raise ServiceUnavailableError() from exc
        if revoked:
            raise NotAuthenticatedError()
        patient = await self._repo.get_by_id(claims.patient_id)
        if patient is None:
            raise NotAuthenticatedError()
        return patient
