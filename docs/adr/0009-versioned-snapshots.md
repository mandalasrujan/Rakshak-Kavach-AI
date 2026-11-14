# ADR 0009: Versioned, approve-once summary snapshots built from SQL

- **Status:** Accepted
- **Date:** 2026-11-11

**Context.** A doctor-facing summary must be exactly what the patient approved, must not be alterable by prompt injection, and must disappear when its source data is deleted.

**Decision.**
- Every generation is a new version. Approval sets `approved_at` once, and the content is never edited afterwards.
- Medication, lab and document sections come straight from SQL with source references. The optional narrative is the only LLM output; it is grounded on those sections, labelled AI-generated, and guarded (M11).
- Deleting a source document invalidates the snapshot, purges its content and revokes its shares. The app role has no DELETE privilege on snapshots.

**Rejected alternatives.** Generating the summary when a doctor scans: no audit trail, LLM calls on the doctor's side, and injection could alter what the doctor reads. Overwriting the snapshot in place: loses history and breaks "the doctor sees what I approved".

**Consequences.** An empty or blocked narrative never blocks a snapshot. Invalidated rows keep their version history but none of their data.
