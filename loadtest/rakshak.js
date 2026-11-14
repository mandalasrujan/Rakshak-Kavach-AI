// k6 load test for Rakshak Kavach AI (M17). Synthetic data only.
//
// Phases run one after another so each workflow is measured on its own:
//   reads (documents, labs, trends, medications) → ask (agent) → login (argon2)
//   → upload (upload → worker processing → ready → delete) → share (doctor PIN exchange + view)
//
// The API must run with load-test rate limits (see loadtest/README.md); production limits would
// (correctly) answer 429 to a single load-generating IP. Over plain http (local runs) the API
// also needs the development-only COOKIE_SECURE=false: k6's cookie jar never sends Secure
// cookies over http, even to localhost.
import http from "k6/http";
import exec from "k6/execution";
import { check, sleep } from "k6";
import { Trend, Counter } from "k6/metrics";

const BASE = __ENV.BASE_URL || "http://127.0.0.1:8000";
const API = `${BASE}/api/v1`;
const USERS = Number(__ENV.USERS || 6);
const PHASE = Number(__ENV.PHASE_SECONDS || 45);
const PASSWORD = "load-test-password-0123";  // synthetic accounts in a disposable database only
const CSRF = { "X-CSRF-Protection": "1" };
const JSON_HEADERS = { ...CSRF, "Content-Type": "application/json" };
const PDFS = ["01_asha_cbc_lft_2025-11-18.pdf", "04_asha_glycated_haemoglobin_2026-05-13.pdf", "07_asha_prescription_2026-05-14.pdf"]
  .map((name) => ({ name, data: open(`${__ENV.SYNTHETIC_DIR || "../data/synthetic"}/${name}`, "b") }));
const QUESTIONS = ["What was my hemoglobin?", "Is my HbA1c getting worse?", "Which medication was prescribed?", "What was my albumin?"];

const processingTime = new Trend("document_processing_ms", true);
const processingFailures = new Counter("document_processing_failures");

const phase = (index, executor) => ({ ...executor, startTime: `${index * (PHASE + 5)}s`, gracefulStop: "10s" });
export const options = {
  setupTimeout: "300s",
  noCookiesReset: true,  // keep each VU logged in across iterations (k6 resets cookies by default)
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max", "count"],
  scenarios: {
    reads: phase(0, { executor: "constant-vus", vus: USERS, duration: `${PHASE}s`, exec: "reads" }),
    ask: phase(1, { executor: "constant-vus", vus: 3, duration: `${PHASE}s`, exec: "ask" }),
    login: phase(2, { executor: "constant-vus", vus: 2, duration: `${PHASE}s`, exec: "loginLoop" }),
    upload: phase(3, { executor: "constant-vus", vus: 1, duration: `${PHASE}s`, exec: "upload" }),
    share: phase(4, { executor: "constant-vus", vus: 2, duration: `${PHASE}s`, exec: "share" }),
  },
  // One threshold per scenario makes k6 report per-workflow latency; error-rate gates are real.
  thresholds: Object.fromEntries(
    ["reads", "ask", "login", "upload", "share"].flatMap((s) => [
      [`http_req_duration{scenario:${s}}`, ["p(95)>=0"]],
      [`http_req_failed{scenario:${s}}`, ["rate<0.01"]],
    ]),
  ),
};

// Emails come from setup(): init code runs once per VU, so anything time-based there differs.
function login(address) {
  const res = http.post(`${API}/auth/login`, JSON.stringify({ email: address, password: PASSWORD }), { headers: JSON_HEADERS });
  check(res, { "login 200": (r) => r.status === 200 });
}

let uploads = 0;
function withNonce(data) {
  uploads += 1;
  // Unique bytes after %%EOF so per-patient dedup does not short-circuit the upload.
  const text = `\n% load-test nonce ${exec.vu.idInTest}-${uploads}-${Date.now()}\n`;
  const nonce = new Uint8Array(text.length);  // ASCII only (k6 has no TextEncoder)
  for (let i = 0; i < text.length; i += 1) nonce[i] = text.charCodeAt(i);
  const bytes = new Uint8Array(data.byteLength + nonce.byteLength);
  bytes.set(new Uint8Array(data), 0);
  bytes.set(nonce, data.byteLength);
  return bytes.buffer;
}

function uploadAndWait(pdf) {
  const started = Date.now();
  const res = http.post(`${API}/patient/documents`, { file: http.file(withNonce(pdf.data), pdf.name, "application/pdf") }, { headers: CSRF });
  if (!check(res, { "upload 202": (r) => r.status === 202 })) return null;
  const id = res.json("id");
  for (let i = 0; i < 120; i += 1) {
    const status = http.get(`${API}/patient/documents/${id}`, { tags: { name: "poll" } }).json("status");
    if (status === "ready") { processingTime.add(Date.now() - started); return id; }
    if (status === "failed") { processingFailures.add(1); return null; }
    sleep(0.25);
  }
  processingFailures.add(1);
  return null;
}

export function setup() {
  const run = Date.now();
  const emails = Array.from({ length: USERS }, (_, i) => `load.${run}.${i}@example.com`);
  const shares = [];
  for (const address of emails) {
    http.post(`${API}/auth/register`, JSON.stringify({ email: address, password: PASSWORD }), { headers: JSON_HEADERS });
    login(address);
    const version = http.get(`${API}/patient/consent`).json("notice_version");
    http.post(`${API}/patient/consent`, JSON.stringify({ notice_version: version }), { headers: JSON_HEADERS });
    PDFS.forEach(uploadAndWait);
    const snapshot = http.post(`${API}/patient/snapshots`, null, { headers: CSRF }).json("id");
    http.post(`${API}/patient/snapshots/${snapshot}/approve`, null, { headers: CSRF });
    const share = http.post(`${API}/patient/shares`, JSON.stringify({ snapshot_id: snapshot, scope: "full_records", expires_in_minutes: 60 }), { headers: JSON_HEADERS });
    shares.push({ token: share.json("token"), pin: share.json("pin") });
    http.post(`${API}/auth/logout`, null, { headers: CSRF });
  }
  return { emails, shares };
}

const myEmail = (data) => data.emails[(exec.vu.idInTest - 1) % data.emails.length];

function ensureLoggedIn(data) {
  if (exec.vu.iterationInScenario === 0) login(myEmail(data));
}

export function reads(data) {
  ensureLoggedIn(data);
  for (const path of ["/patient/documents", "/patient/labs", "/patient/labs/trends", "/patient/medications"]) {
    check(http.get(`${API}${path}`, { tags: { name: path } }), { "read 200": (r) => r.status === 200 });
  }
}

export function ask(data) {
  ensureLoggedIn(data);
  const question = QUESTIONS[exec.scenario.iterationInTest % QUESTIONS.length];
  const res = http.post(`${API}/patient/ask`, JSON.stringify({ question }), { headers: JSON_HEADERS, tags: { name: "/patient/ask" } });
  check(res, { "ask 200": (r) => r.status === 200, "ask grounded": (r) => !r.json("found") || r.json("citations").length > 0 });
}

export function loginLoop(data) {
  login(myEmail(data));
}

export function upload(data) {
  ensureLoggedIn(data);
  const id = uploadAndWait(PDFS[exec.scenario.iterationInTest % PDFS.length]);
  if (id) check(http.del(`${API}/patient/documents/${id}`, null, { headers: CSRF }), { "delete 204": (r) => r.status === 204 });
}

export function share(data) {
  const { token, pin } = data.shares[(exec.vu.idInTest - 1) % data.shares.length];
  if (exec.vu.iterationInScenario === 0) {
    const res = http.post(`${API}/share/sessions`, JSON.stringify({ token, pin, declared_name: "Load Test (Synthetic)" }), { headers: JSON_HEADERS, tags: { name: "/share/sessions" } });
    check(res, { "share session 200": (r) => r.status === 200 });
  }
  check(http.get(`${API}/share/view`, { tags: { name: "/share/view" } }), { "share view 200": (r) => r.status === 200 });
}

export function handleSummary(data) {
  const out = __ENV.SUMMARY_FILE || "../load-results/k6-summary.json";
  return { [out]: JSON.stringify(data, null, 2), stdout: "" };
}
