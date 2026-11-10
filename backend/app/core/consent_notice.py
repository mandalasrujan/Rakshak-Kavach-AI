"""Versioned consent notice. Bump the version whenever the text changes: every patient must
consent again to the new version before uploads or chat are allowed."""

CONSENT_NOTICE_VERSION = "2026-11-10"

CONSENT_NOTICE_TEXT = (
    "Rakshak Kavach AI stores the medical documents you upload and extracts their text so it "
    "can answer questions about your own records. To do this, excerpts of your documents and "
    "your questions are sent to Google's Gemini API for processing. Your data is used only to "
    "provide this records assistant to you; it does not diagnose, predict or prescribe. "
    "You can revoke consent at any time. Revoking stops new uploads and chat and revokes any "
    "active shares with doctors; documents you have already uploaded are kept until you delete "
    "them. Data handling is modeled on DPDP principles."
)
