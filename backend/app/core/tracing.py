"""Deterministic PHI-masked Langfuse tracing.

Observability for the LangGraph agent and LLM execution path.
Guarantees:
1. No PHI, secrets, raw medical document contents, or credentials reach Langfuse.
2. Tracing failures never break or degrade the patient turn (fail-safe).
3. Configuration is loaded strictly from environment variables.
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from app.core.config import Settings

log = structlog.get_logger(__name__)

# Patterns to scrub from any string
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
UUID_REGEX = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
PHONE_REGEX = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
DATE_REGEX = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b")
JWT_REGEX = re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}")
API_KEY_REGEX = re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")
PIN_REGEX = re.compile(r"\b\d{6}\b")
AUTH_TOKEN_REGEX = re.compile(r"(?:Bearer\s+|rk_access=|rk_share=)[^\s;]+")
NUMERIC_VALUE_REGEX = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg/dL|mmol/L|µmol/L|%|g/dL|U/L|cells/µL|fl|pg|ng/mL|IU/mL|bpm|mmHg)\b",
    re.IGNORECASE,
)
XML_TAG_REGEX = re.compile(
    r"<(?:evidence|history|turn)[^>]*>.*?</(?:evidence|history|turn)>", re.DOTALL | re.IGNORECASE
)

# Keys whose values are stripped/redacted entirely
PHI_KEYS = frozenset(
    {
        "patient_id",
        "email",
        "password",
        "password_hash",
        "pin",
        "token",
        "access_token",
        "jwt",
        "cookie",
        "cookies",
        "authorization",
        "secret",
        "jwt_secret_key",
        "gemini_api_key",
        "body",
        "raw_name",
        "value",
        "canonical_value",
        "dose",
        "frequency",
        "duration",
        "text",
        "excerpt",
        "content",
        "content_json",
        "messages",
        "evidence",
        "citations",
        "declared_name",
        "declared_reg_no",
        "date_of_birth",
        "dob",
        "address",
        "phone",
        "name",
        "document",
        "documents",
        "results",
        "medications",
        "labs",
    }
)


def pseudonymize_id(val: Any) -> str:
    """One-way truncated hash for correlating turns without exposing raw UUIDs."""
    if val is None:
        return "none"
    return f"anon_{hashlib.sha256(str(val).encode('utf-8')).hexdigest()[:12]}"


def mask_phi(data: Any) -> Any:
    """Recursively scrub PHI, secrets, auth tokens, and raw clinical content from data."""
    if isinstance(data, dict):
        masked: dict[str, Any] = {}
        for key, val in data.items():
            if str(key).lower() in PHI_KEYS:
                if isinstance(val, (list, tuple)):
                    masked[key] = {"count": len(val), "redacted": True}
                else:
                    masked[key] = "[REDACTED]"
            else:
                masked[key] = mask_phi(val)
        return masked
    if isinstance(data, (list, tuple)):
        return [mask_phi(item) for item in data]
    if isinstance(data, str):
        s = XML_TAG_REGEX.sub("[EVIDENCE_REDACTED]", data)
        s = JWT_REGEX.sub("[TOKEN_REDACTED]", s)
        s = AUTH_TOKEN_REGEX.sub("[AUTH_REDACTED]", s)
        s = API_KEY_REGEX.sub("[API_KEY_REDACTED]", s)
        s = EMAIL_REGEX.sub("[EMAIL_REDACTED]", s)
        s = PHONE_REGEX.sub("[PHONE_REDACTED]", s)
        s = DATE_REGEX.sub("[DATE_REDACTED]", s)
        s = UUID_REGEX.sub("[ID_REDACTED]", s)
        s = NUMERIC_VALUE_REGEX.sub("[VALUE_REDACTED]", s)
        s = PIN_REGEX.sub("[PIN_REDACTED]", s)
        return s
    return data


class TurnTrace:
    """Manages active spans and observations for a single agent turn."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        patient_id: Any = None,
        chat_id: Any = None,
        question: str = "",
    ) -> None:
        self._client = client
        self._patient_pseudonym = pseudonymize_id(patient_id)
        self._chat_pseudonym = pseudonymize_id(chat_id) if chat_id else None
        self._question_len = len(question)
        self._root_obs: Any = None
        self.recorded_events: list[dict[str, Any]] = []

        if self._client is not None:
            try:
                self._root_obs = self._client.start_observation(
                    name="medical_history_agent",
                    as_type="agent",
                    input={"query_length": self._question_len, "has_chat": bool(chat_id)},
                    metadata={
                        "patient_anon": self._patient_pseudonym,
                        "chat_anon": self._chat_pseudonym,
                    },
                )
            except Exception as exc:
                log.debug("tracing.start_observation_failed", error=str(exc))
                self._root_obs = None

    def record_node(
        self,
        *,
        name: str,
        duration_ms: float,
        outcome: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        safe_meta = mask_phi(metadata or {})
        safe_meta.update({"duration_ms": duration_ms, "outcome": outcome})
        self.recorded_events.append({"type": "node", "name": name, "metadata": safe_meta})

        if self._root_obs is not None:
            try:
                node_obs = self._root_obs.start_observation(
                    name=f"node.{name}",
                    as_type="span",
                    metadata=safe_meta,
                )
                node_obs.end()
            except Exception as exc:
                log.debug("tracing.record_node_failed", node=name, error=str(exc))

    def record_tools(
        self,
        *,
        tool_names: list[str],
        evidence_count: int,
        duration_ms: float,
    ) -> None:
        safe_info = {
            "tools": tool_names,
            "evidence_count": evidence_count,
            "duration_ms": duration_ms,
        }
        self.recorded_events.append({"type": "tools", "data": safe_info})

        if self._root_obs is not None:
            try:
                tool_obs = self._root_obs.start_observation(
                    name="tools.execution",
                    as_type="tool",
                    input={"tools": tool_names},
                    output={"evidence_count": evidence_count},
                    metadata={"duration_ms": duration_ms},
                )
                tool_obs.end()
            except Exception as exc:
                log.debug("tracing.record_tools_failed", error=str(exc))

    def record_generation(
        self,
        *,
        model: str,
        duration_ms: float,
        found: bool,
        citations_count: int,
    ) -> None:
        safe_info = {
            "model": model,
            "duration_ms": duration_ms,
            "found": found,
            "citations_count": citations_count,
        }
        self.recorded_events.append({"type": "generation", "data": safe_info})

        if self._root_obs is not None:
            try:
                gen_obs = self._root_obs.start_observation(
                    name="llm.generation",
                    as_type="generation",
                    model=model,
                    output={"found": found, "citations_count": citations_count},
                    metadata={"duration_ms": duration_ms},
                )
                gen_obs.end()
            except Exception as exc:
                log.debug("tracing.record_generation_failed", error=str(exc))

    def record_error(self, error_type: str, message: str | None = None) -> None:
        safe_error = {"error_type": error_type, "message": mask_phi(message or "")}
        self.recorded_events.append({"type": "error", "data": safe_error})

        if self._root_obs is not None:
            try:
                err_obs = self._root_obs.start_observation(
                    name="agent.error",
                    as_type="span",
                    level="ERROR",
                    status_message=error_type,
                    metadata=safe_error,
                )
                err_obs.end()
            except Exception as exc:
                log.debug("tracing.record_error_failed", error=str(exc))

    def end(
        self,
        *,
        outcome: str,
        found: bool | None = None,
        cited: int | None = None,
        duration_ms: float | None = None,
    ) -> None:
        safe_output = {
            "outcome": outcome,
            "found": found,
            "cited": cited,
            "duration_ms": duration_ms,
        }
        self.recorded_events.append({"type": "end", "data": safe_output})

        if self._root_obs is not None:
            try:
                self._root_obs.update(
                    output={"outcome": outcome, "found": found, "cited": cited},
                    metadata={"duration_ms": duration_ms},
                )
                self._root_obs.end()
            except Exception as exc:
                log.debug("tracing.end_failed", error=str(exc))


class LangfuseTracer:
    """Manages the Langfuse client and initiates masked traces for agent executions."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    @property
    def is_enabled(self) -> bool:
        return self._client is not None

    def start_turn(
        self,
        *,
        patient_id: Any,
        chat_id: Any = None,
        question: str = "",
    ) -> TurnTrace:
        return TurnTrace(
            client=self._client,
            patient_id=patient_id,
            chat_id=chat_id,
            question=question,
        )

    def flush(self) -> None:
        if self._client is not None:
            try:
                self._client.flush()
            except Exception as exc:
                log.debug("tracing.flush_failed", error=str(exc))

    def shutdown(self) -> None:
        if self._client is not None:
            try:
                self._client.shutdown()
            except Exception as exc:
                log.debug("tracing.shutdown_failed", error=str(exc))


_cached_tracer: LangfuseTracer | None = None


def get_tracer(settings: Settings) -> LangfuseTracer:
    """Factory creating or returning a cached LangfuseTracer instance based on Settings."""
    global _cached_tracer
    if not settings.langfuse_enabled:
        return LangfuseTracer(client=None)

    if _cached_tracer is not None and _cached_tracer.is_enabled:
        return _cached_tracer

    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=(
                settings.langfuse_secret_key.get_secret_value()
                if settings.langfuse_secret_key
                else ""
            ),
            host=settings.langfuse_host,
        )
        _cached_tracer = LangfuseTracer(client=client)
        return _cached_tracer
    except Exception as exc:
        log.warning("tracing.init_failed", error=str(exc))
        return LangfuseTracer(client=None)
