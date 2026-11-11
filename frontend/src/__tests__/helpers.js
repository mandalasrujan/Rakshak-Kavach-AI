import { vi } from "vitest";

// Route table for a stubbed fetch: { "GET /patient/me": [status, body] | (init) => [status, body] }.
export function stubApi(routes) {
  const calls = [];
  const fetchMock = vi.fn(async (url, init = {}) => {
    const method = init.method ?? "GET";
    const path = url.replace("/api/v1", "").split("?")[0];
    calls.push({ method, path, init });
    const entry = routes[`${method} ${path}`];
    const [status, body] = typeof entry === "function" ? entry(init) : entry ?? [404, { error: { code: "not_found", message: "Not Found" } }];
    return { ok: status < 400, status, json: async () => body };
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}
