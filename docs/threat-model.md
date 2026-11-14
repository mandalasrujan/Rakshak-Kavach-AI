# Threat Model (one page)

Scope: Rakshak Kavach AI v1 as specified in `PROJECT_SPEC.md`. Wording: controls are "modeled on DPDP principles", not "DPDP compliant". Test data is synthetic only.

**Assets.** Patient account credentials and sessions; uploaded medical documents and extracted values (PHI); chat history and LangGraph checkpoints; share tokens, PINs and doctor sessions; consent and audit records; secrets (`JWT_SECRET_KEY`, database password, Gemini API key).

**Actors.** Patient (owner of their data); doctor holding a QR code and PIN (read-only, scoped, time-limited); unauthenticated internet attacker; another patient (curious or malicious); a malicious document author (prompt injection inside a PDF); operator with infrastructure access; third-party LLM provider (Gemini).

**Trust boundaries.** Browser to API; API and worker to PostgreSQL and Redis; API and worker to Gemini; patient routes vs share routes.

| # | Threat | Mitigation | Milestone |
|---|---|---|---|
| 1 | Credential stuffing or brute force against login | argon2 hashes, generic error message, per-email and per-IP rate limits in Redis, dummy hash on unknown email | M2 |
| 2 | Session theft via XSS or CSRF | JWT only in `httpOnly`, `Secure`, `SameSite=Lax` cookie; Origin and `Sec-Fetch-Site` checks; custom CSRF header on unsafe methods; logout denylist | M2 |
| 3 | Cross-patient data leakage | Scoped repositories with mandatory `patient_id`, PostgreSQL RLS, non-owner app role, leakage tests at both layers | M6 |
| 4 | Prompt injection in uploaded PDFs or questions | Retrieved text escaped and treated as data; deterministic read-only tools (no LLM tool choice); input injection guard; citation grounding; output guard; doctor-facing sections built from SQL (M13) | M10, M11, M13 |
| 5 | Photographed or leaked QR code | 32-byte SHA-256-hashed token in the URL fragment plus argon2id 6-digit PIN; 5 wrong PINs lock permanently; per-IP exchange limit; 30-min path-scoped session; expiry, revocation (also via consent revoke or source deletion); token stripped from the address bar; doctor sees only the approved snapshot cut by scope | M14 |
| 6 | PHI leaking through logs or traces | IDs and metadata only, key-based log redaction, no request bodies or query strings logged, SQL parameters hidden, masked traces | M1, M11 |
| 7 | Malicious or oversized uploads | Magic-byte check, 12 MB proxy body limit plus API size limit, page limits in the worker, random storage keys, per-patient dedup | M4, M17 |
| 8 | Unsafe medical output (diagnosis, wrong numbers, missed urgency) | Deterministic YAML red-flag rules with negation/history (urgent guidance cannot be overridden), output guard (no diagnosis/treatment/prediction, numbers must appear in evidence), lab math in Python | M9, M11 |

**Accepted risks (updated after M17).** Doctor identity in the access log is self-declared and unverified. Anyone holding both the QR code and the PIN within the expiry window can open the share (by design: it is a bearer credential with a second factor). The Compose API trusts `X-Forwarded-For` from any source because its port is bound to localhost behind nginx; real deployments must set `FORWARDED_ALLOW_IPS` to the proxy address. Deleted data persists in database backups until they rotate; queued jobs for deleted documents are left to no-op. Registration returns 409 for an existing email (account enumeration; mitigated only by per-IP rate limiting; no email verification yet). Data processed by Gemini leaves our infrastructure; the consent notice (M3) must say so. The offline `fake` LLM provider exists for keyless development and is refused when `APP_ENV=production`. RAG answers depend on the model following the system prompt; deterministic guards limit the damage (citation check, no tools), and the full output guard is M11. Not production-grade: no encryption at rest, no full RBAC, no formal compliance review.
