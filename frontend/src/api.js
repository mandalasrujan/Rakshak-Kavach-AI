// Same-origin calls (via the dev proxy). The session lives in an httpOnly cookie that
// JavaScript cannot read; unsafe methods send the CSRF header the API requires.
export async function api(path, { method = "GET", json, form } = {}) {
  const headers = {};
  if (method !== "GET") headers["X-CSRF-Protection"] = "1";
  if (json) headers["Content-Type"] = "application/json";
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: json ? JSON.stringify(json) : form,
  });
  const body = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.error?.message ?? `Request failed (${response.status})`);
  }
  return body;
}
