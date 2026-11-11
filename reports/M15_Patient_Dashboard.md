# Milestone Report: M15 — Patient Dashboard

## Objective
A complete React + Tailwind patient frontend on the real backend, plus the doctor share page.

- **Spec "done when":** every value links to its source page.

## Implementation
- **Routing** (`react-router-dom` 6.28): `/login`, `/register`, a protected dashboard, and a public `/share` for doctors.
- **Auth context:** checks `/patient/me` on load; unauthenticated users are redirected to the login page.
- **API client:** same-origin with `credentials: same-origin`. It adds `X-CSRF-Protection: 1` to every POST, PUT, PATCH and DELETE automatically, and maps the API error schema to `ApiError`. Nothing is written to localStorage or sessionStorage.
- **Dashboard tabs:**
  - **Records:** upload, processing status with polling, readable failure reasons, open the PDF, delete with an explanation of what is removed.
  - **Assistant:** chats (new, open, delete, history). Answers show citations as links to the exact page. Urgent answers are shown as a red `role=alert`; not-found answers are muted.
  - **Labs:** trend cards (status, change, latest and previous values with source links) and an all-results table.
  - **Medications.**
  - **Summary:** versions, generate, preview, approve (the screen explains that approved summaries never change).
  - **Sharing:**
    - Create a share from an approved snapshot, with scope and expiry.
    - The QR code is drawn in the browser (`qrcode`), and the PIN is shown once.
    - Shares can be revoked, and an access log lists each doctor session (self-declared, unverified).
  - **Consent:** notice, grant and revoke.
- **States:** loading, empty, error and success throughout. A consent banner and gates pause features that need consent.
- **Doctor page `/share`:** reads the token from `#t=`, strips it from the address bar, and keeps it in a ref only. PIN form plus optional name and registration number, then a read-only snapshot view (sources only when the scope includes them), with an end-session button. An existing session resumes.
- **Source links:** every value links to `/api/v1/patient/documents/{id}/file#page=N`, a new owner-only endpoint serving the original PDF with `no-store` and `nosniff`.
- **New `GET /api/v1/patient/medications`.**
- **Responsive and accessible:** mobile-first Tailwind layout (stacked under `md`, tables scroll horizontally), visible focus rings, labelled inputs, `aria-live` chat log, `role=alert/status`; `index.html` sets `referrer=no-referrer`.

## Files
- **New:**
  - `frontend/src/{api.js,auth.jsx,index.css}`, `frontend/src/components/{ui,SnapshotView}.jsx`.
  - `frontend/src/pages/{Login,Dashboard,Records,Assistant,Labs,Medications,Summary,Sharing,Consent,DoctorShare}.jsx`.
  - `frontend/src/__tests__/{setup.js,helpers.js,api.test.js,routes.test.jsx,components.test.jsx,doctor.test.jsx,a11y.test.jsx}`.
  - `frontend/{tailwind.config.js,postcss.config.js}`.
  - `backend/app/api/v1/medications.py`, `tests/integration/test_dashboard_api.py`.
- **Modified:** `frontend/{package.json,package-lock.json,vite.config.js,index.html}`, `frontend/src/main.jsx`, `backend/app/services/document_service.py` (`read_file`), `backend/app/api/v1/{documents,router}.py`.
- **Removed:** the M7 minimal `frontend/src/App.jsx` and `styles.css` (replaced).
- **Dependencies:**
  - Runtime: `qrcode` 1.5.4, `react-router-dom` 6.28.0.
  - Dev: `tailwindcss` 3.4.17, `postcss` 8.4.49, `autoprefixer` 10.4.20, `vitest` 2.1.8, `@testing-library/*`, `jsdom` 25.0.1, `axe-core` 4.10.2.

## Tests
- **Frontend (Vitest):** 13 passed, 0 failed:
  - API client: CSRF header on every unsafe method and never on GET; error schema; source URLs.
  - Protected routes: redirect to login; consent prompt.
  - Answers: urgent rendered as an alert; citation link and `rel`.
  - Created share: QR code and PIN shown, no storage writes.
  - Doctor page: token stripped from the URL and never stored; exchange carries the CSRF header; `summary_only` shows no sources; wrong-PIN message.
  - axe-core: 3 screens with 0 violations. A sanity run confirmed axe does report `label` and `image-alt` violations.
- **Backend:** `test_dashboard_api.py` (1): medications and source PDF are owner-only (404 for another patient); `content-type`, `no-store` and `nosniff` headers.
- **Production build:** `vite build` passes (JS 221 KB / 72.9 KB gzip, CSS 15.5 KB).
- **Served through the production nginx config** in front of the API: `/`, the SPA fallback, CSP and other headers, and `/api` proxying verified (see M17).

## Known limitations
- Not exercised in a real browser here; there are no end-to-end browser tests (Playwright browsers can't be downloaded in this environment).
- Colour contrast was not machine-checked (jsdom); the palette uses Tailwind 700/800 text on light backgrounds.
- Chat history from the server has no stored citations; citations show for answers given in the current session.

## Status
**`M15: COMPLETED AND VERIFIED`** (component, integration and build level)
