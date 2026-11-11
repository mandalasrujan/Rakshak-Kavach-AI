# ADR 0008: Doctor share access via hashed token + PIN and an RLS owner lookup

- **Status:** Accepted
- **Date:** 2026-11-11

**Context.** A doctor without an account must see one patient-approved summary for a limited time. A photographed QR code alone must not be enough, and doctor access must not weaken patient isolation.

**Decision.**
- **Credentials:** a 32-byte random token (stored as SHA-256) carried in the URL *fragment*, plus a 6-digit PIN (argon2id). Five wrong PINs, counted under a row lock, lock the share permanently.
- **Session:** a successful exchange creates a 30-minute session (never longer than the share) in an httpOnly, `SameSite=Strict` cookie path-scoped to `/api/v1/share`.
- **Owner lookup:** two `SECURITY DEFINER` SQL functions map a token hash to its owner's `patient_id`. Every later read runs under that patient's RLS context, so `share_grants` and `doctor_sessions` stay under RLS.
- **What the doctor sees:** the frozen, approved snapshot, cut down by scope. Doctor code may not import patient services; a test enforces this.

**Rejected alternatives.** Patient ID or token in the query string (logged and shared via Referer). No RLS on share tables, which would leave a pre-auth lookup path outside RLS. Live queries for the doctor view, which would show unapproved data and widen the attack surface.

**Consequences.** Scanning the QR again needs the PIN again; each exchange is audited. Revoking or locking the share, revoking consent, or deleting a source document ends every session at once. Doctor identity is self-declared and unverified.
