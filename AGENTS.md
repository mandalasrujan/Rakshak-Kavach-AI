# AGENTS.md

Permanent instructions for anyone (human or coding agent) working on this repository.

## Source of truth

- `PROJECT_SPEC.md` is the source of truth. If a request conflicts with it, stop and ask.

## Scope discipline

- Work on one milestone at a time.
- Never implement future milestones unless explicitly requested.
- Do not add unrequested features.
- Do not replace specified technologies without approval.
- Keep changes minimal and reviewable.
- Inspect only relevant files; don't repeatedly dump the whole repository.

## Non-negotiable rules

- Never hardcode secrets. Configuration comes from environment variables; `.env.example` holds placeholders only.
- Preserve the `LLMProvider` abstraction. No direct LLM SDK calls from business logic.
- Keep deterministic medical calculations, validation, safety rules and access control outside the LLM.
- Preserve patient scoping and PostgreSQL RLS requirements.
- Never bypass authentication, authorization, consent, sharing, expiry or revocation.

## Testing

- Write tests together with the implementation.
- Run relevant tests after implementation.

## End-of-milestone report

At the end of each milestone, report:

1. Files changed
2. What was implemented
3. Tests added
4. Test results
5. Remaining issues
