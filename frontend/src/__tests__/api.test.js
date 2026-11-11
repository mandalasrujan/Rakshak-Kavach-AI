import { describe, expect, it } from "vitest";
import { ApiError, api, sourceUrl } from "../api.js";
import { stubApi } from "./helpers.js";

describe("api client", () => {
  it("adds the CSRF header to every unsafe method and never to GET", async () => {
    const calls = stubApi({
      "GET /x": [200, {}], "POST /x": [200, {}], "PUT /x": [200, {}], "PATCH /x": [200, {}], "DELETE /x": [204, null],
    });
    for (const method of ["GET", "POST", "PUT", "PATCH", "DELETE"]) await api("/x", { method });
    for (const call of calls) {
      expect(call.init.credentials).toBe("same-origin");
      expect(call.init.headers["X-CSRF-Protection"]).toBe(call.method === "GET" ? undefined : "1");
    }
  });

  it("sends JSON and surfaces the API error schema", async () => {
    const calls = stubApi({ "POST /auth/login": [401, { error: { code: "invalid_credentials", message: "Invalid email or password." } }] });
    const error = await api("/auth/login", { method: "POST", json: { email: "a@b.c", password: "p" } }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect([error.status, error.code, error.message]).toEqual([401, "invalid_credentials", "Invalid email or password."]);
    expect(calls[0].init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(calls[0].init.body)).toEqual({ email: "a@b.c", password: "p" });
  });

  it("links sources to the exact PDF page", () => {
    expect(sourceUrl("abc", 2)).toBe("/api/v1/patient/documents/abc/file#page=2");
  });
});
