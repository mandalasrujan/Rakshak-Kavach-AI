from app.core.consent_notice import CONSENT_NOTICE_TEXT, CONSENT_NOTICE_VERSION


def test_notice_discloses_gemini_and_revocation_with_approved_wording() -> None:
    assert CONSENT_NOTICE_VERSION
    assert "Gemini" in CONSENT_NOTICE_TEXT
    assert "revoke" in CONSENT_NOTICE_TEXT.lower()
    assert "modeled on DPDP principles" in CONSENT_NOTICE_TEXT
    assert "compliant" not in CONSENT_NOTICE_TEXT.lower()
