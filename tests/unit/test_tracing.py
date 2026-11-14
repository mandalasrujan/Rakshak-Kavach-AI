"""Unit tests for Langfuse tracing and deterministic PHI masking layer.

Verifies:
1. Tracing is invoked for the AI execution path.
2. PHI is strictly masked before Langfuse receives any data.
3. Secrets, API keys, JWTs, cookies, and PINs are never traced.
4. Raw medical records, XML tags, and clinical values are never traced.
5. Langfuse failures do not break the user request path.
6. Configuration comes from environment variables.
"""

import uuid
from typing import Any
from unittest.mock import MagicMock

from app.core.config import Settings
from app.core.tracing import (
    LangfuseTracer,
    get_tracer,
    mask_phi,
    pseudonymize_id,
)


def test_mask_phi_scrubs_identifiers() -> None:
    raw_payload = {
        "patient_id": str(uuid.uuid4()),
        "email": "patient.test@example.com",
        "phone": "+1-555-234-5678",
        "dob": "15/08/1985",
        "address": "123 Health Ave, City, Country",
        "name": "Jane Doe",
        "notes": (
            "Patient Jane Doe (DOB: 15/08/1985, email: jane@clinic.org, "
            "phone: (555) 987-6543) visited."
        ),
    }
    masked = mask_phi(raw_payload)

    assert masked["patient_id"] == "[REDACTED]"
    assert masked["email"] == "[REDACTED]"
    assert masked["phone"] == "[REDACTED]"
    assert masked["dob"] == "[REDACTED]"
    assert masked["address"] == "[REDACTED]"
    assert masked["name"] == "[REDACTED]"
    assert "jane@clinic.org" not in masked["notes"]
    assert "[EMAIL_REDACTED]" in masked["notes"]
    assert "[DATE_REDACTED]" in masked["notes"]
    assert "[PHONE_REDACTED]" in masked["notes"]


def test_mask_phi_scrubs_secrets_tokens_and_pins() -> None:
    # Build dynamically to avoid literal secret patterns in repository static analysis
    sample_jwt = (
        "ey"
        + "JhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        + "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        + "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    sample_api_key = "AI" + "zaSyD-0123456789abcdefghijklmnopqrst"
    sample_pin = "852963"

    raw_data = {
        "jwt": sample_jwt,
        "token": "secret-session-token-xyz",
        "secret": "top-secret-signing-key",
        "pin": sample_pin,
        "cookie": "rk_access=secret_cookie_val; rk_share=share_val",
        "prompt_injection_attempt": (
            f"My API key is {sample_api_key} and my PIN is {sample_pin} "
            "with cookie rk_access=abc123456789."
        ),
    }
    masked = mask_phi(raw_data)

    assert masked["jwt"] == "[REDACTED]"
    assert masked["token"] == "[REDACTED]"
    assert masked["secret"] == "[REDACTED]"
    assert masked["pin"] == "[REDACTED]"
    assert masked["cookie"] == "[REDACTED]"

    untrusted_str = masked["prompt_injection_attempt"]
    assert sample_api_key not in untrusted_str
    assert sample_pin not in untrusted_str
    assert "[API_KEY_REDACTED]" in untrusted_str
    assert "[PIN_REDACTED]" in untrusted_str
    assert "[AUTH_REDACTED]" in untrusted_str


def test_mask_phi_scrubs_raw_medical_records_and_lab_values() -> None:
    raw_document_xml = (
        '<turn role="user">What was my HbA1c?</turn>\n'
        '<evidence id="E1" kind="lab_row" pages="1">'
        "HbA1c was 7.6 % and glucose 140 mg/dL.</evidence>"
    )
    payload = {
        "evidence": [{"chunk_id": str(uuid.uuid4()), "text": "Raw report excerpt text"}],
        "medications": [{"name": "Metformin", "dose": "500 mg", "frequency": "twice daily"}],
        "labs": [{"raw_name": "Hemoglobin", "value": "13.5 g/dL", "canonical_value": 13.5}],
        "citations": [{"document_id": str(uuid.uuid4()), "excerpt": "Private doctor note"}],
        "document_text": raw_document_xml,
    }
    masked = mask_phi(payload)

    # Collections are replaced by metadata summaries without content
    assert masked["evidence"] == {"count": 1, "redacted": True}
    assert masked["medications"] == {"count": 1, "redacted": True}
    assert masked["labs"] == {"count": 1, "redacted": True}
    assert masked["citations"] == {"count": 1, "redacted": True}

    doc_str = masked["document_text"]
    assert "<evidence" not in doc_str
    assert "7.6 %" not in doc_str
    assert "[EVIDENCE_REDACTED]" in doc_str


def test_pseudonymize_id_is_deterministic_and_non_reversible() -> None:
    test_uuid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    pseudo_1 = pseudonymize_id(test_uuid)
    pseudo_2 = pseudonymize_id(test_uuid)

    assert pseudo_1 == pseudo_2
    assert pseudo_1.startswith("anon_")
    assert str(test_uuid) not in pseudo_1
    assert len(pseudo_1) == 17  # anon_ + 12 hex chars


def test_tracing_invoked_along_execution_path() -> None:
    mock_client = MagicMock()
    mock_root = MagicMock()
    mock_child = MagicMock()
    mock_client.start_observation.return_value = mock_root
    mock_root.start_observation.return_value = mock_child

    patient_id = uuid.uuid4()
    chat_id = uuid.uuid4()

    tracer = LangfuseTracer(client=mock_client)
    turn = tracer.start_turn(
        patient_id=patient_id,
        chat_id=chat_id,
        question="What was my hemoglobin level?",
    )

    # 1. Root agent observation started
    mock_client.start_observation.assert_called_once()
    _, root_kwargs = mock_client.start_observation.call_args
    assert root_kwargs["name"] == "medical_history_agent"
    assert root_kwargs["as_type"] == "agent"
    assert "patient_anon" in root_kwargs["metadata"]
    assert str(patient_id) not in root_kwargs["metadata"]["patient_anon"]

    # 2. Record nodes
    turn.record_node(name="consent", duration_ms=1.2, outcome="consented")
    turn.record_node(name="red_flags", duration_ms=0.5, outcome="no_red_flag")

    # 3. Record tools
    turn.record_tools(tool_names=["get_labs"], evidence_count=2, duration_ms=15.0)

    # 4. Record generation
    turn.record_generation(
        model="gemini-1.5-flash", duration_ms=250.0, found=True, citations_count=1
    )

    # 5. End turn
    turn.end(outcome="answered", found=True, cited=1, duration_ms=300.0)

    # Verifications on mock calls
    assert mock_root.start_observation.call_count >= 4
    mock_root.update.assert_called_once()
    mock_root.end.assert_called_once()


def test_tracing_data_sent_to_mock_is_strictly_masked() -> None:
    mock_client = MagicMock()
    mock_root = MagicMock()
    mock_client.start_observation.return_value = mock_root

    raw_jwt = "ey" + "JhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-ID"
    raw_secret_question = f"My secret token is {raw_jwt} and email is patient@test.org"
    patient_id = uuid.uuid4()

    tracer = LangfuseTracer(client=mock_client)
    turn = tracer.start_turn(patient_id=patient_id, question=raw_secret_question)

    # Check root kwargs
    _, root_kwargs = mock_client.start_observation.call_args
    assert "patient@test.org" not in str(root_kwargs)
    assert "eyJhbG" not in str(root_kwargs)
    assert str(patient_id) not in str(root_kwargs)

    # Test node recording with potentially sensitive metadata
    turn.record_node(
        name="tools",
        duration_ms=10.0,
        outcome="retrieved",
        metadata={
            "patient_id": str(patient_id),
            "raw_name": "Hemoglobin A1c",
            "value": "7.6 %",
            "dose": "500 mg",
        },
    )

    child_calls = mock_root.start_observation.call_args_list
    assert len(child_calls) == 1
    _, child_kwargs = child_calls[0]
    meta = child_kwargs["metadata"]
    assert meta["patient_id"] == "[REDACTED]"
    assert meta["raw_name"] == "[REDACTED]"
    assert meta["value"] == "[REDACTED]"
    assert meta["dose"] == "[REDACTED]"
    assert str(patient_id) not in str(child_kwargs)


def test_langfuse_failure_does_not_break_execution() -> None:
    failing_client = MagicMock()
    failing_client.start_observation.side_effect = RuntimeError("Langfuse API connection timeout")

    tracer = LangfuseTracer(client=failing_client)

    # Must not raise
    turn = tracer.start_turn(patient_id=uuid.uuid4(), question="Check my report")
    turn.record_node(name="consent", duration_ms=1.0)
    turn.record_tools(tool_names=["search_records"], evidence_count=1, duration_ms=5.0)
    turn.record_generation(model="fake", duration_ms=10.0, found=True, citations_count=1)
    turn.record_error("LLMUnavailableError")
    turn.end(outcome="answered", duration_ms=50.0)

    # Tracer flush and shutdown also fail-safe
    failing_client.flush.side_effect = RuntimeError("Flush network error")
    tracer.flush()
    failing_client.shutdown.side_effect = RuntimeError("Shutdown error")
    tracer.shutdown()


def test_tracing_configuration_from_settings(monkeypatch: Any) -> None:
    # 1. Unconfigured settings -> tracer disabled
    disabled_settings = Settings(
        database_url="postgresql+asyncpg://rakshak:pw@localhost/test",
        redis_url="redis://localhost/0",
        jwt_secret_key="secret-key-at-least-32-characters-long",  # pragma: allowlist secret
    )
    assert disabled_settings.langfuse_enabled is False
    tracer_disabled = get_tracer(disabled_settings)
    assert tracer_disabled.is_enabled is False

    # 2. Configured settings with placeholders -> tracer disabled
    placeholder_settings = Settings(
        database_url="postgresql+asyncpg://rakshak:pw@localhost/test",
        redis_url="redis://localhost/0",
        jwt_secret_key="secret-key-at-least-32-characters-long",  # pragma: allowlist secret
        langfuse_public_key="<langfuse-public-key>",
        langfuse_secret_key="<langfuse-secret-key>",
        langfuse_host="<langfuse-host-url>",
    )
    assert placeholder_settings.langfuse_public_key is None
    assert placeholder_settings.langfuse_secret_key is None
    assert placeholder_settings.langfuse_host is None
    assert placeholder_settings.langfuse_enabled is False

    # 3. Valid environment variables -> tracer enabled
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-valid-12345")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-valid-67890")
    monkeypatch.setenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    enabled_settings = Settings(
        database_url="postgresql+asyncpg://rakshak:pw@localhost/test",
        redis_url="redis://localhost/0",
        jwt_secret_key="secret-key-at-least-32-characters-long",  # pragma: allowlist secret
    )
    assert enabled_settings.langfuse_enabled is True
    assert enabled_settings.langfuse_public_key == "pk-lf-valid-12345"
    assert enabled_settings.langfuse_host == "https://cloud.langfuse.com"
