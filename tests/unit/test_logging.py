import json

import structlog

from app.core.logging import REDACTED, configure_logging, redact_sensitive


def test_redaction_masks_sensitive_keys() -> None:
    event = redact_sensitive(
        None, "info", {"event": "x", "password": "p", "Email": "a@b.c", "patient_id": "123"}
    )
    assert event["password"] == REDACTED
    assert event["Email"] == REDACTED
    assert event["patient_id"] == "123"


def test_logs_are_json_and_redacted(capsys) -> None:  # type: ignore[no-untyped-def]
    configure_logging("INFO")
    structlog.get_logger("test").info("demo.event", patient_id="p-1", token="secret-token")
    line = capsys.readouterr().out.strip().splitlines()[-1]
    record = json.loads(line)
    assert record["event"] == "demo.event"
    assert record["patient_id"] == "p-1"
    assert record["token"] == REDACTED
    assert "secret-token" not in line
