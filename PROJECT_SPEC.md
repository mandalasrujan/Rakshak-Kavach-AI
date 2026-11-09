# Rakshak Kavach AI: Project Specification (v2)

> This document is the source of truth for all development. Working rules for contributors and coding agents are in [`AGENTS.md`](AGENTS.md).

## 1. Overview

A patient uploads digital medical PDFs (lab reports, imaging reports, prescriptions, doctor notes) and chats with one Medical History Agent. The agent answers only from that patient's records, with page-level citations. The patient can share a read-only, scoped view with a doctor using a QR code plus a PIN they read out. The doctor sees a summary the patient has already previewed and approved.

**Design principle:** the LLM handles language: understanding questions, explaining results and writing narrative. Numbers, units, access control and safety rules are plain, testable code.

**Positioning:** a patient records assistant. It does not diagnose, predict or prescribe.

**What changed from v1:**

- pgvector replaces Chroma, and Postgres row-level security (RLS) is added.
- Extraction is table-aware, and lab values are normalized (test names, units, dates).
- The doctor summary is a snapshot the patient approves, not something generated on scan.
- Doctor access is QR plus PIN, exchanged for a short session.
- Navigator and intake move to stretch goals.
- Deployment moves to week 1.
- Every safety eval now measures both sides (catches and false alarms).
- The worker library is fixed as ARQ.

## 2. Scope

### 2.1 Patient features (v1)

| Area | Features |
|---|---|
| Account | Register, log in (JWT in an httpOnly cookie), log out |
| Consent | Grant or revoke a versioned consent notice that states data is sent to Google's Gemini API. Revoking stops chat and uploads and revokes all active shares. |
| Documents | Upload digital PDFs; see status (queued, processing, ready, failed with reason); delete with full cascade |
| Chat | Ask about own records; cited answers; "not found in your records" fallback; lab trends computed in code; red-flag alert on urgent symptoms |
| Dashboard | Five panels: documents, current medications, latest labs vs previous, consent status, sharing and access log. Every value links to its source page. |
| Sharing | Create a share (scope, expiry), preview and approve the summary snapshot, see the PIN, revoke, view the access log |
| Chat history | View and delete conversations |

### 2.2 Doctor view (no account)

The doctor scans the QR code, enters the PIN, and optionally gives a name and registration number (self-declared). They then get a read-only session that lasts 30 minutes and never outlives the share's expiry.

| Item | summary_only | full_records |
|---|---|---|
| Patient-approved summary snapshot | Yes | Yes |
| Current medications (from SQL) | Yes | Yes |
| Latest labs with previous comparison | Yes | Yes |
| Document list | No | Yes |
| Source page behind each value | No | Yes |

The doctor cannot:

- chat or see chat history
- edit or delete anything
- manage consent or shares
- call any patient endpoint
- see a summary the patient hasn't approved
- keep access after expiry or revocation

### 2.3 Background behavior

- **Ingestion (ARQ worker):** validate, extract text and tables, chunk, extract labs and medications, normalize, validate against source, embed. Jobs are idempotent, retried on failure and record failure reasons.
- **Platform:** per-patient deduplication, rate limiting, PHI-free logs, masked traces, and per-node latency and token counts.

### 2.4 Stretch goals (only after M17)

- **S1:** a mock `book_appointment` tool with LangGraph `interrupt()` confirmation.
- **S2:** SOCRATES guided intake.
- **S3:** a timeline panel.
- **S4:** true hybrid search (keyword plus vector), only if the retrieval eval shows exact-term misses.

### 2.5 Not in v1

OCR (scans or handwriting), vitals, multiple agents, real ABHA login, HIS integration, voice, multilingual intake, FHIR export, doctor-side chat, hospital and pharmacy finders.

## 3. Architecture

```
Patient (React) ──JWT cookie──► FastAPI /api/v1/patient/* ──► LangGraph
                                      │                       consent → red-flag rules → agent → output guard
                                      │ enqueue               tools: search_records · get_labs · get_medications
                                      ▼
                               Redis (ARQ queue, rate limits)
                                      ▼
                               Ingestion worker
                               validate → extract text + tables → chunk
                               → extract labs/meds → normalize → validate → embed

Doctor (browser) ─QR + PIN─► FastAPI /api/v1/share/*   read-only: snapshot + scoped SQL views

All of the above read/write:
PostgreSQL 16 + pgvector  (row-level security on patient_id)

Object storage: local volume now, S3-compatible later
Gemini: LLM + embeddings, behind LLMProvider
```

### 3.1 Key decisions

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Agents | One agent, 3 tools | Several agents + router | Fewer LLM calls, reliable tool choice, easier evals |
| Retrieval | Semantic search (pgvector) + structured SQL tools | Vector-only RAG | Exact numbers and medication lists are unreliable from text chunks |
| Vector store | pgvector in the main Postgres | Chroma server | One datastore, transactional deletes, RLS covers vectors, SQL joins |
| Isolation | Scoped repositories + Postgres RLS | App-level filter only | A forgotten filter fails closed instead of leaking |
| Lab math | Python + canonical test dictionary + unit conversions | LLM compares values | Deterministic and testable; handles renamed tests and differing units |
| Extraction | Table-aware (`find_tables`), one lab row per record | Plain text, token-window chunks | Lab reports are tables, and plain text scrambles rows |
| Safety | Deterministic rules with negation + output guard | Prompt-only safety | Testable; urgency never depends on LLM obedience |
| Doctor summary | Patient-approved snapshot built when the share is created | Generated on each scan | No doctor-side LLM calls, exact audit trail, injection can't alter the medication list |
| Share access | Hashed token + PIN, exchanged for a session; token stripped from URL | Patient ID or bare token in the QR | A photographed QR alone isn't enough; tokens don't sit in history or logs |
| Queue | ARQ on Redis | Celery, RQ | Async-native, fits FastAPI, small |
| Caching | No response cache | Redis response cache | Avoids health data in cache and keeps deletion simple; little gain at this scale |
| Streaming | v1 returns the full guarded answer | Token streaming | The guard must see the whole answer; sentence-buffered streaming can come later |

## 4. Data model

| Table | Key columns | Notes |
|---|---|---|
| `patients` | id, email, password_hash, created_at | argon2 hashing |
| `consent_records` | id, patient_id, notice_version, granted_at, revoked_at | Notice text versioned in code |
| `documents` | id, patient_id, storage_key, file_hash, status, failure_reason, pages, uploaded_at | Unique on (patient_id, file_hash) |
| `chunks` | id, patient_id, document_id, page, kind (narrative / lab_row), text, embedding, embedding_model | btree index on patient_id |
| `lab_results` | id, patient_id, document_id, page, raw_name, test_code, value, unit, canonical_value, canonical_unit, ref_low, ref_high, collected_on, reported_on, validation_status | Reference range stored per result |
| `medications` | id, patient_id, document_id, page, name, dose, frequency, start_date, validation_status | |
| `chats` | id, patient_id, created_at | Used as thread_id for the checkpointer |
| `message_citations` | chat_id, document_id | Lets deletion find chats that cited a document |
| `summary_snapshots` | id, patient_id, content_json, source_document_ids, model, generated_at, approved_at | Immutable once approved |
| `share_grants` | id, patient_id, token_hash, pin_hash, scope, snapshot_id, expires_at, revoked_at, failed_pin_attempts | SHA-256 hash of a 32-byte token |
| `doctor_sessions` | id, share_grant_id, declared_name, declared_reg_no, expires_at | Declared fields are unverified |
| `audit_log` | id, patient_id, actor_type, action, target_id, metadata, created_at | IDs and metadata only, no PHI |

### 4.1 Test dictionary and unit conversions

Keep these in versioned YAML config rather than the database. Cover about 40 common tests: CBC, lipid profile, HbA1c, fasting glucose, kidney panel, liver panel and thyroid. Write conversions as functions, not just multipliers:

- Glucose: mmol/L × 18.0 → mg/dL
- Cholesterol: mmol/L × 38.67 → mg/dL
- Triglycerides: mmol/L × 88.57 → mg/dL
- Creatinine: µmol/L ÷ 88.4 → mg/dL
- HbA1c: IFCC mmol/mol → NGSP % = 0.0915 × value + 2.15 (this one isn't a simple factor)

Tests not in the dictionary are stored but never compared.

### 4.2 RLS setup

- The app's database role must not own the tables, because owners bypass RLS unless you set `FORCE ROW LEVEL SECURITY`. Run migrations as a separate owner role.
- Every request and every worker job runs `SET LOCAL app.patient_id = ...` inside its transaction.
- Policies compare each row's patient_id against `current_setting('app.patient_id')`.

### 4.3 Vector index

Each patient has a few hundred chunks at most. An exact search filtered by patient_id is fast and has perfect recall. Skip HNSW in v1, because approximate indexes combined with a selective filter can return too few results.

### 4.4 Dates

Parse DD/MM/YYYY explicitly. Prefer the collection date over the report date. When a date is ambiguous, flag it instead of guessing.

## 5. Tech stack

| Layer | Choice |
|---|---|
| Frontend | React, Tailwind CSS |
| Backend | Python, FastAPI, Pydantic |
| Database | PostgreSQL 16 + pgvector, SQLAlchemy, Alembic |
| Queue | Redis + ARQ |
| Auth | argon2, JWT in an httpOnly SameSite=Lax cookie, CSRF header check |
| Document processing | PyMuPDF (text + `find_tables`), no OCR |
| LLM and embeddings | Gemini API behind `LLMProvider` |
| Agent | LangGraph with Postgres checkpointer (LangChain only for text splitting) |
| Testing | pytest, Testcontainers, mocked LLM in CI |
| Observability | structlog JSON logs with request IDs; Langfuse with a masking function |
| DevOps | Docker multi-stage builds, Compose, GitHub Actions (CI + deploy on merge) |

**Learning order:**

1. FastAPI and Pydantic
2. SQLAlchemy, Alembic and Postgres RLS
3. Embeddings and retrieval
4. LangGraph
5. Security and evals

## 6. Milestones

| # | Milestone | Deliverable | Done when |
|---|---|---|---|
| M0 | Repo and tooling | Repo, `.env.example`, Compose (API, Postgres+pgvector, Redis, worker), ruff, pytest, ADR folder with first 5 ADRs, synthetic PDF generator, one-page threat model | `docker compose up` starts all services healthy |
| M1 | Skeleton + live deploy | Layered app (router → service → repository), config, Alembic, `/api/v1`, error schema, request-ID logging, `/health`, CI and deploy on merge | Public `/health` returns 200; a test creates a row through every layer |
| M2 | Auth | Register and login, argon2, JWT cookie, `get_current_patient`, CSRF check, login rate limit | Protected route rejects unauthenticated and cross-site calls |
| M3 | Consent and audit | Versioned consent, grant and revoke, `require_consent` dependency, audit log | Revoked consent blocks upload and chat; events appear in `audit_log` |
| M4 | Upload and queue | 202 upload, storage interface, document status, ARQ worker with retries and idempotent jobs, magic-byte check, size and page limits, per-patient dedup | Upload goes queued → ready; the same file from a second patient is accepted |
| M5 | Table-aware extraction | PyMuPDF text + `find_tables`, one record per lab row, narrative chunks with page metadata | Synthetic lab PDFs produce one row per test with correct page numbers |
| M6 | Embeddings and isolation | `LLMProvider`, `VectorStore` (pgvector), scoped repositories, RLS policies, non-owner app role, embedding model stored per chunk | Leakage tests pass, including a query with the patient filter deliberately removed |
| M7 | Baseline RAG | `/ask` with citations and not-found fallback, minimal React chat, 20-question retrieval set, long-context baseline | Hit rate and baseline comparison recorded in the README |
| M8 | Extraction and normalization | Gemini extraction into Pydantic schemas, test dictionary, unit conversions, same-row validation, plausibility bounds, date parsing | Mismatches rejected and logged; precision and recall measured on 10 labeled reports |
| M9 | Lab comparison | Plain-Python previous-vs-latest comparison, no LLM imports | Tests pass for rising, falling, unchanged, missing, convertible units, unconvertible units, renamed test, ambiguous date |
| **✓** | **Week-4 checkpoint** | **Interview-ready: upload, cited chat, normalized lab trends, leakage tests, live URL** | |
| M10 | Agent | LangGraph state and nodes, three tools, Postgres checkpointer, retrieved text treated as data, injection test cases | Correct tool chosen on 10 hand-written questions |
| M11 | Safety nodes | Consent and red-flag nodes, output guard (phrasing + numeric check), streaming ADR, per-node latency | Negated phrasing not flagged; red-flag precision/recall and guard false-block rate recorded |
| M12 | Deletion | One cascade service: file, rows, chunks, labs, medications, citing chats and their checkpoints; invalidates affected snapshots and their shares | A deleted document can't be reached through chat, dashboard, history or any share |
| M13 | Summary snapshots | Medication and lab sections built from SQL, plus a short guard-checked narrative labeled AI-generated; preview and approve UI | Schema-valid snapshot; an injection PDF can't change the medication section |
| M14 | Scoped sharing | Tokens, PIN, scope, expiry, revoke, token-to-session exchange, declared name, per-view audit, rate limits, share router isolated from patient services | Expired or revoked → 401; 5 wrong PINs lock the share; scope limits data; token absent from the final URL |
| M15 | Dashboard | Five read-only panels | Every value links to its source page |
| M16 | Evals and CI | 25 to 30 golden cases, CI with mocked LLM, manual or nightly live-LLM eval job | CI fails if leakage, red-flag, guard or recall tests regress |
| M17 | Load test and polish | k6 run, restart-persistence test, backup and restore note, tracing screenshot, seeded demo patient, README with diagram and measured numbers | Real p50/p95 latency recorded; demo runs from a fresh deploy |

### 6.1 Pacing (full-time, 8 weeks)

| Week | Milestones |
|---|---|
| 1 | M0–M2 (live URL by end of week) |
| 2 | M3–M5 |
| 3 | M6–M7 |
| 4 | M8–M9 → checkpoint |
| 5 | M10–M11 |
| 6 | M12–M13 |
| 7 | M14–M15 |
| 8 | M16–M17 |

If working alongside classes, expect about 1.5× this, with the checkpoint around week 6.

### 6.2 Never cut

M3 (consent), M6 (leakage tests and RLS), M11 (safety), M12 (deletion), M14 (share scoping), M16 (evals).

### 6.3 Cut order if time runs short

1. Stretch goals.
2. Shrink the dashboard to three panels (documents, labs, sharing).
3. Drop the LLM narrative from snapshots and keep only the SQL-built sections.

## 7. Safety, security and privacy

**Wording rules:** write "modeled on DPDP principles", never "DPDP compliant". Write "based on commonly documented warning signs", never "clinically validated".

| Area | Controls |
|---|---|
| Red flags | Rules in YAML: patterns plus a negation window. Run on the patient's own messages only, never on retrieved document text. On a match, return a fixed urgent message (emergency numbers 112 or 108) and skip the agent; record this choice in an ADR. |
| Output guard | Blocks diagnostic and prescriptive phrasing. Numeric check: every number in the answer must appear in tool results or cited chunks. Trend wording is limited to "discuss with your doctor". |
| Prompt injection | Retrieved text is wrapped and labeled as data. No action tools in v1. Doctor-facing medication and lab sections come from SQL. Injection PDFs are in the eval set. |
| Isolation | Scoped repositories (patient_id required in the constructor) plus RLS; leakage tests at both layers |
| Share access | 32-byte token (SHA-256 hashed); 6-digit PIN (hashed, locks after 5 failed attempts); scope, expiry, revoke; token-to-session exchange with redirect; `Referrer-Policy: no-referrer`; audit entry per view; failed attempts logged |
| Doctor session | Separate router and dependency. The share module must not import patient services; enforce with an import-linter rule or a test. |
| Uploads | Magic-byte type check, size and page limits, random storage keys, per-patient dedup |
| Deletion | One service covers the file, rows, chunks, derived labs and medications, and citing chats with their checkpoints. It invalidates snapshots built from the document and revokes their shares. The UI warns the patient that chats citing the document will also be deleted. |
| Consent | Versioned notice. Revoking blocks chat and uploads and revokes shares. |
| Logging | IDs and metadata only; traces masked; a redaction test checks this |
| Auth | argon2, httpOnly SameSite=Lax cookie, CSRF header on state-changing requests, login rate limit |
| Test data | Synthetic reports only, never real patient documents |
| Threat model | One page: assets, actors, top 8 threats, mitigations |

## 8. Evaluation plan

| Eval | What it measures | Runs in |
|---|---|---|
| Retrieval hit rate@k | Right chunk in top-k on 20 known-answer questions | Live job |
| Long-context baseline | Accuracy, latency, cost and citation precision vs putting the whole record in the prompt | Live, once |
| Extraction | Precision and recall of lab values on 10 hand-labeled reports | Live job |
| Normalization | Test aliases, unit conversions, date parsing | CI |
| Lab comparison | Rising, falling, unchanged, missing, unit cases | CI |
| Red flags | Recall on urgent phrasings; precision on benign and negated phrasings | CI |
| Guard | Block rate on diagnostic phrasing; false-block rate on factual answers | CI |
| Numeric consistency | Answers with altered numbers get blocked | CI |
| Tool selection | Correct tool on 10 to 15 questions | Live job |
| Injection | Malicious PDFs don't change tool calls or snapshots | CI + live |
| Leakage | Cross-patient queries return nothing, at both repository and RLS layers | CI |
| Deletion | Deleted document gone from chat, dashboard, history and snapshots | CI |
| Share access | Expiry, revoke, PIN lockout, scope limits, token not in URL | CI |
| Groundedness | Claims map to cited chunks, checked on a sample | Manual |

## 9. Engineering practices

**ADRs.** Write one ADR per row of the key decisions table (10 lines each: context, decision, rejected alternative). Write the first five in M0: pgvector, ARQ, one agent, JWT storage, and streaming vs guard.

**Code structure:**

- Provider interfaces (`LLMProvider`, `VectorStore`) so Gemini or the vector store can be swapped.
- Thin tools, with logic in services so it's testable without an LLM.
- One error schema, pagination and OpenAPI descriptions.

**Process:**

- CI deploys on every merge.
- Commit after every passing milestone.
- Keep a bug log from day one.

**Working with Antigravity or any coding agent:**

- Give it one milestone per task, and ask for a plan before code.
- Require tests in the same task.
- Review every diff for missing patient scoping, RLS bypasses, hardcoded providers and secrets.

## 10. Interview prep

### 10.1 60-second pitch (fill in measured numbers)

> "Rakshak Kavach is a health records assistant. Patients upload lab reports and prescriptions and ask questions in plain language. A single LangGraph agent answers only from their own records, with page-level citations. The interesting part is what isn't the LLM. Lab values are extracted, normalized across units and test names, and compared in plain Python. Urgent symptoms are caught by deterministic rules. Patient isolation is enforced by Postgres row-level security and tested in CI. Patients can share a read-only summary with a doctor through a QR code and PIN, and the doctor sees exactly the snapshot the patient approved. I measured [X]% retrieval hit rate, [X]% red-flag recall at [X]% precision, and [X]s p50 latency."

### 10.2 End-to-end trace for "Is my HbA1c getting worse?"

1. React posts the question with the session cookie.
2. `get_current_patient` validates the JWT, and the rate limiter checks Redis.
3. A transaction opens and runs `SET LOCAL app.patient_id`.
4. The consent node confirms active consent.
5. The red-flag rules run on the message text; nothing urgent is found.
6. Gemini picks `get_labs(test="HbA1c")`.
7. The lab service resolves the alias to a canonical code, queries SQL (RLS applies), computes the comparison in Python, and returns values with document and page IDs.
8. Gemini writes the answer with citations.
9. The output guard checks phrasing and confirms every number matches the tool output.
10. The checkpoint is saved, an audit row is written, a masked trace is recorded, and the answer is returned.

### 10.3 Viva question bank (v1 bank reconciled with v2 decisions, plus v2 additions)

**Architecture**

| Question | Answer direction |
|---|---|
| Why one agent instead of several? | Fewer LLM calls, more reliable tool selection, easier evaluation; the old agents were mostly different prompts over the same data |
| Why LangGraph? | Explicit state, checkpointer, fixed node order (consent, rules, agent, guard); be honest that it pays off as the graph grows |
| Why semantic search plus structured SQL tools? | Vector search is good for narrative text but weak for exact numbers and medication lists |
| Why a background worker? | Extraction and embedding would block or time out the API |
| Why pgvector over Chroma? | One store, transactional deletes, RLS, joins; move to Qdrant only if vectors outgrow Postgres |
| Why RAG if the records fit in context? | Your measured long-context baseline numbers |

**RAG**

| Question | Answer direction |
|---|---|
| How did you choose chunk size? | Describe what you tested and why you kept your choice |
| How do you reduce hallucination? | Citations, patient-only data, not-found fallback, output guard with numeric check |
| How did you evaluate retrieval? | Describe your hit-rate set; do not overclaim |
| Why no ANN index? | Small per-patient sets; filtered ANN can lose recall |

**Safety and security**

| Question | Answer direction |
|---|---|
| Why rules for red flags? | Deterministic and testable; urgency should not depend on prompt obedience |
| How do you handle "no chest pain"? | Negation window, and its limits |
| What are the guard's limits? | It can miss subtle phrasing; say so |
| What does the numeric check catch and miss? | Catches invented or altered numbers; misses wrong wording around correct numbers |
| How do you stop cross-patient leakage? | Scoped repositories plus Postgres RLS, verified by leakage tests at both layers |
| How does RLS work, and what's the catch? | Session variable and policies; table owners bypass RLS without `FORCE` |
| Why not put the patient ID in the QR? | A photographed QR would expose records permanently |
| Why strip the token from the URL? | History, logs and referrer headers |
| Why snapshot summaries? | Exact audit, no doctor-side LLM calls, injection can't alter the medication list |
| How do you handle prompt injection through uploads? | Retrieved text treated as data, no action tools in v1, doctor-facing medication and lab sections built from SQL |
| Why per-patient dedup? | Global dedup reveals that someone else uploaded the same file |
| What happens on document delete or consent revoke? | Walk through the cascade |
| Is it production secure? | No; list what is missing |

**Data**

| Question | Answer direction |
|---|---|
| What if the LLM misreads a lab value? | Validation against the source row and plausibility bounds, plus a dashboard link to the source page |
| Why compute differences in Python? | Deterministic, testable, no LLM miscalculation |
| How do you handle scans? | Not supported; OCR is the next step |

**Engineering**

| Question | Answer direction |
|---|---|
| What breaks first at 10x users? | Embedding calls and the single Postgres instance; path is more workers, and Qdrant only if vectors outgrow Postgres |
| Biggest bug you hit? | Prepare one real story from your build |
| What would you do differently? | Real auth and RBAC, bigger eval set, Alembic discipline from day one |

### 10.4 Scope honesty

| Not built | What to say |
|---|---|
| Real ABHA auth, HIS integration | "I designed the identity seam but did not integrate the ABDM sandbox." |
| OCR for scans or handwriting | "Digital PDFs only. PaddleOCR plus validation against source text is the next step." |
| Vitals tracking | "Scoped to document-based records; vitals would be the next module." |
| Clinical validation of red flags | "Based on commonly documented warning signs; needs clinician review." |
| Production-grade security | "Missing encryption at rest, full RBAC and formal compliance review." |
| Doctor identity | "Self-declared and unverified; real verification would go through ABDM's Healthcare Professionals Registry." |
| Lab dictionary | "Covers [N] common tests; unknown tests are stored but never compared." |

**OCR status:** the core build uses PyMuPDF text extraction, which is not OCR. Do not write "OCR" on the resume unless OCR is actually added.

## 11. Resume bullets

**Rakshak Kavach AI | AI Health Records Assistant | [GitHub] | [Live Demo]**

- Built a full-stack health records assistant in which a single LangGraph agent answers questions over a patient's own medical PDFs with page-level citations, combining pgvector semantic search with structured SQL tools; measured [X]% retrieval hit rate on [N] questions against a long-context baseline.
- Designed an async ingestion pipeline (FastAPI, Redis/ARQ, PyMuPDF table extraction, Gemini embeddings) that extracts lab values, normalizes test names and units, validates them against source rows, and computes trends in plain Python with no LLM arithmetic.
- Implemented safety and privacy controls: rule-based red-flag triage with negation handling ([X]% recall, [X]% precision), a no-diagnosis output guard with numeric consistency checks, consent and audit logging, and patient isolation via Postgres row-level security verified by leakage tests in CI.
- Built QR-plus-PIN scoped sharing for clinicians with hashed, expiring, revocable tokens and patient-approved summary snapshots; containerized with Docker and deployed via GitHub Actions at [URL] with p50 chat latency of [X] s.

**Tech:** React, Tailwind, FastAPI, LangGraph, Gemini API, PostgreSQL + pgvector, Redis/ARQ, PyMuPDF, Docker, GitHub Actions.

Replace each [X] with a measured number, or delete it.

## 12. Future work

| Area | Item | Notes |
|---|---|---|
| Documents | OCR for scans (PaddleOCR or a vision model) | Needs source-text validation; measure and report the misread rate |
| Retrieval | True hybrid search and reranking | Only if evals show exact-term misses |
| Features | Navigator and intake | From the stretch list |
| Health data | Vitals tracking | Deterministic trend engine, no LLM math |
| Interoperability | FHIR export, ABHA and HPR integration | Maps from structured tables; needs ABDM sandbox registration |
| Intake | Telugu and Hindi | Needs a multilingual eval set |
| Infrastructure | Encryption at rest with KMS, backups and restore drills | Needed before any real use |
| Compliance | Clinician review of red-flag rules, formal privacy review | Required before real patient use |
| Agents | Specialized agents | Only if evals show the single agent underperforms |

## 13. Start here

**Day 1.** Create the repo and a Compose file using the `pgvector/pgvector:pg16` image. Write ADRs 1 to 5.

**Day 2.** Write the one-page threat model. Build a synthetic PDF generator (reportlab works well for tables) and generate 10 to 15 reports, including:

- at least two labs that report in mmol/L
- one test under a different name (for example "Glycated Haemoglobin")
- one DD/MM date that's ambiguous
- one PDF containing a prompt-injection attempt

**Day 3.** Build the M1 skeleton, set up CI, and get `/health` live on a public URL.

From then on, one milestone at a time, and don't start M10 until the M6 leakage tests pass.
