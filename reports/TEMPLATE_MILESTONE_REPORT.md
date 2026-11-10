# Milestone Report: [Milestone Code] — [Milestone Title]

> **Instructions for Authors & Coding Agents:**
> Use this template for all future milestones (M3 through M17). Fill in every section based on actual code, migrations, tests, and runtime verification. Do not claim features that are not implemented.

---

## 1. Milestone Title and Objective
- **Milestone:** M[X] — [Title]
- **Status:** [NOT STARTED / IN PROGRESS / COMPLETED]
- **Objective:** [High-level summary of what this milestone accomplishes and what problem it solves.]

---

## 2. Why This Milestone is Necessary
[Explain the business, medical, or architectural justification for this milestone. Detail why this capability cannot be omitted, how it contributes to patient safety, privacy, or determinism, and what architectural integrity it preserves.]

---

## 3. Requirements from `PROJECT_SPEC.md`
- **Core Deliverables:**
  - [List bullet points directly mapped from PROJECT_SPEC.md milestone deliverables]
- **Acceptance Criteria ("Done when"):**
  - [Quote or state the exact acceptance criteria from PROJECT_SPEC.md]

---

## 4. Architecture and Implementation
[Describe the technical design, component interactions, and state flow. Include an ASCII or Mermaid diagram where it improves clarity.]

### 4.1 Key Design Choices
- [List specific decisions and why alternatives were rejected, referencing ADRs where relevant]

### 4.2 Data & Component Flow
```
[Client / Caller] ───► [FastAPI Router] ───► [Service Layer] ───► [Repository / Engine]
```

---

## 5. Files and Folders Created or Modified
- `path/to/file1.py`: [Brief summary of purpose and changes]
- `path/to/file2.py`: [Brief summary of purpose and changes]
- `tests/.../test_xxx.py`: [Associated unit/integration tests]

---

## 6. Important Classes, Functions and APIs
- `module.submodule.ClassName`: [Responsibility, key methods, and thread/async considerations]
- `module.submodule.function_name(...)`: [Parameters, return types, and exceptions raised]
- `METHOD /api/v1/endpoint`: [Route specification, request body schema, response schema, error codes]

---

## 7. Database Changes (if applicable)
- **Migration Script:** `backend/alembic/versions/XXXX_migration_name.py`
- **Tables Created / Modified:**
  - `table_name`:
    - `column_name` (Type, Constraints, Defaults, Indices)
- **Row-Level Security (RLS) Policies:** [If applicable, describe policies comparing `current_setting('app.patient_id')`]

---

## 8. Security Considerations
- **Access Control & Authorization:** [How user/doctor permissions are enforced]
- **Data Isolation:** [How cross-patient leakage is prevented at application and database layers]
- **Adversarial Protections:** [Handling prompt injections, malicious inputs, boundary violations]
- **Audit & Privacy:** [What is logged and what is explicitly redacted/omitted]

---

## 9. Testing Methodology
- **Unit Testing Strategy:** [Mocking strategies, isolated function tests]
- **Integration Testing Strategy:** [Database/Redis fixtures, Testcontainers, transactional rollbacks]
- **Security / Evals Strategy:** [Adversarial inputs, leakage tests, negative test cases]

---

## 10. Test Cases and Actual Results

| Test File | Test Case Name | Purpose / Scenario Tested | Result |
|---|---|---|---|
| `tests/.../test_example.py` | `test_valid_scenario` | [Description] | **PASSED** |
| `tests/.../test_example.py` | `test_rejection_scenario` | [Description] | **PASSED** |

---

## 11. Problems Encountered and Fixes
1. **[Problem Summary]:**
   - **Context:** [What went wrong or broke during development/testing]
   - **Root Cause:** [Why the failure occurred]
   - **Resolution:** [Code or configuration changes made to resolve it]

---

## 12. Verification Results
- **Docker Compose Status:** [Containers built and healthy]
- **Pytest Output:** [X passed, Y failed, Z skipped]
- **Linter Status:** [`ruff check .` and `ruff format --check .` results]
- **Endpoint Probes:** [Example curl request and response output]

---

## 13. Limitations and Pending Work
- [What is explicitly deferred to later milestones]
- [Known edge cases or stretch goals not covered in this phase]

---

## 14. Final Milestone Status
**`M[X]: [COMPLETED AND VERIFIED / NOT COMPLETED]`**
- [Summary conclusion certifying completion against acceptance criteria.]

