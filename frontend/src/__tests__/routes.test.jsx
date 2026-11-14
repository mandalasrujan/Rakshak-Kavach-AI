import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AuthProvider } from "../auth.jsx";
import { AppRoutes, ROUTER_FUTURE } from "../main.jsx";
import { stubApi } from "./helpers.js";

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]} future={ROUTER_FUTURE}>
      <AuthProvider><AppRoutes /></AuthProvider>
    </MemoryRouter>,
  );
}

describe("protected routes", () => {
  it("send anonymous visitors to the login page", async () => {
    stubApi({ "GET /patient/me": [401, { error: { code: "not_authenticated", message: "Authentication required." } }] });
    renderAt("/labs");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("show the dashboard with a consent prompt when not yet consented", async () => {
    stubApi({
      "GET /patient/me": [200, { id: "p1", email: "asha@example.com", created_at: "2026-01-01T00:00:00Z" }],
      "GET /patient/consent": [200, { granted: false, notice_version: "v1", notice_text: "Notice", granted_at: null, revoked_at: null }],
      "GET /patient/documents": [200, { items: [], total: 0, limit: 100, offset: 0 }],
    });
    renderAt("/");
    expect(await screen.findByRole("navigation", { name: "Dashboard" })).toBeInTheDocument();
    expect(await screen.findByText(/paused until you give consent/)).toBeInTheDocument();
    expect(await screen.findByText("No documents yet.")).toBeInTheDocument();
  });
});
