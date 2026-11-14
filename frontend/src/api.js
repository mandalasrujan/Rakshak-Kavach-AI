// Same-origin API client. Sessions live in httpOnly cookies that JavaScript cannot read;
// every unsafe request carries the CSRF header the API requires. Nothing is ever written to
// localStorage or sessionStorage.
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function api(path, { method = "GET", json, form } = {}) {
  const headers = {};
  if (UNSAFE.has(method)) headers["X-CSRF-Protection"] = "1";
  if (json !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: json !== undefined ? JSON.stringify(json) : form,
  });
  if (response.status === 204) return null;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      response.status,
      body?.error?.code ?? "http_error",
      body?.error?.message ?? `Request failed (${response.status}).`,
    );
  }
  return body;
}

export const sourceUrl = (documentId, page) =>
  `/api/v1/patient/documents/${documentId}/file#page=${page}`;

export const shortId = (id) => String(id).slice(0, 8);
